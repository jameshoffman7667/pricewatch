"""RedFlagDeals Hot Deals integration.

Data sources, all confirmed against the live site:

- Atom feed at ``https://forums.redflagdeals.com/feed/forum/<forum_id>``
  for new-thread discovery (Hot Deals = forum 9, Expired Hot Deals = 68).
- The thread page itself (``viewtopic.php?t=<id>``) for the structured
  deal fields RFD renders as plain labelled text: "Deal Link:", "Price:",
  "Original Price:", "Savings:", "Expiry:" - and, when present, RFD's own
  "Thread Summary" / "AI-generated summary - <date>" block.
- RFD's own search (``search.php?keywords=...&sf=titleonly``) to find
  prior threads for the same/similar product, filtered to the Expired Hot
  Deals forum.

Parsing here matches on stable, user-facing label text rather than CSS
class names, since RFD's markup/theme can change under us but the labels
("Deal Link:", "AI-generated summary") are part of the product and change
far less often.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

BASE = "https://forums.redflagdeals.com"
HOT_DEALS_FORUM_ID = 9
EXPIRED_HOT_DEALS_FORUM_ID = 68
FEED_URL = f"{BASE}/feed/forum/{HOT_DEALS_FORUM_ID}"

USER_AGENT = "PriceWatch/1.0 (+self-hosted deal tracker; polite polling)"

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

TITLE_PREFIX_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(.*)$")

# RFD thread URLs come in two shapes we need to handle:
#   1. https://forums.redflagdeals.com/viewtopic.php?t=2827328&p=...   (feed links)
#   2. https://forums.redflagdeals.com/costco-level-ground-...-2827259/  (SEO slug,
#      what the site actually renders as its own canonical/search-result links)
THREAD_ID_QUERY_RE = re.compile(r"[?&]t=(\d+)")
THREAD_ID_SLUG_RE = re.compile(r"-(\d{5,})/?(?:[?#]|$)")  # RFD thread ids run 6-7 digits; guards against matching page/forum numbers
# Kept for external callers that only care about the feed's query-param form.
THREAD_ID_RE = THREAD_ID_QUERY_RE


def extract_thread_id(url: str) -> Optional[int]:
    """Pull the numeric thread id out of either RFD URL shape."""
    m = THREAD_ID_QUERY_RE.search(url)
    if m:
        return int(m.group(1))
    m = THREAD_ID_SLUG_RE.search(url)
    if m:
        return int(m.group(1))
    return None


def _client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )


@dataclass
class FeedEntry:
    thread_id: int
    title: str
    retailer: Optional[str]
    rfd_url: str
    author: Optional[str]
    published: Optional[str]   # ISO string as given by the feed
    thumbnail_url: Optional[str]


def _split_retailer(raw_title: str) -> tuple[Optional[str], str]:
    m = TITLE_PREFIX_RE.match(raw_title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, raw_title.strip()


def fetch_feed() -> list[FeedEntry]:
    """Fetch and parse the Hot Deals Atom feed into new-thread entries."""
    with _client() as client:
        resp = client.get(FEED_URL)
        resp.raise_for_status()
        xml_bytes = resp.content
    return parse_feed(xml_bytes)


def parse_feed(xml_bytes: bytes) -> list[FeedEntry]:
    """Parse Atom feed bytes into entries. Split out from fetch_feed() so
    it can be unit-tested against a saved fixture without network access.
    """
    root = ET.fromstring(xml_bytes)
    entries: list[FeedEntry] = []
    for entry in root.findall("a:entry", _ATOM_NS):
        link_el = entry.find("a:link", _ATOM_NS)
        rfd_url = link_el.get("href") if link_el is not None else None
        if not rfd_url:
            continue

        thread_id = extract_thread_id(rfd_url)
        if thread_id is None:
            continue

        title_el = entry.find("a:title", _ATOM_NS)
        raw_title = (title_el.text or "").strip() if title_el is not None else ""
        retailer, title = _split_retailer(raw_title)

        author_el = entry.find("a:author/a:name", _ATOM_NS)
        author = author_el.text.strip() if author_el is not None and author_el.text else None

        published_el = entry.find("a:published", _ATOM_NS)
        published = published_el.text.strip() if published_el is not None and published_el.text else None

        # media:thumbnail is in a separate XML namespace not registered
        # above; find it by local tag name instead of building a qname.
        thumb_url = None
        for child in entry:
            if child.tag.endswith("}thumbnail"):
                thumb_url = child.get("url")
                break

        # Canonicalize to the thread's own permalink (without the #p fragment)
        # so re-polling the feed doesn't create duplicate rows per new reply.
        canonical_url = f"{BASE}/viewtopic.php?t={thread_id}"

        entries.append(
            FeedEntry(
                thread_id=thread_id,
                title=title,
                retailer=retailer,
                rfd_url=canonical_url,
                author=author,
                published=published,
                thumbnail_url=thumb_url,
            )
        )
    return entries


PRICE_RE = re.compile(r"\$?\s*([\d,]+\.\d{2}|\d+)")


def _parse_money(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    m = PRICE_RE.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _label_value(soup: BeautifulSoup, label: str) -> Optional[str]:
    """Find a `<label>:` text node and return the text immediately after it."""
    node = soup.find(string=re.compile(re.escape(label)))
    if node is None:
        return None
    # The value is usually the remaining text in the same element, or the
    # next sibling's text if the label is its own element.
    parent = node.parent
    full = parent.get_text(" ", strip=True) if parent else str(node)
    after = full.split(label, 1)
    if len(after) == 2 and after[1].strip():
        return after[1].strip()
    nxt = parent.find_next(string=True) if parent else None
    return nxt.strip() if nxt else None


def _label_link(soup: BeautifulSoup, label: str) -> Optional[str]:
    """Find a `<label>:` text node and return the href of the next link."""
    node = soup.find(string=re.compile(re.escape(label)))
    if node is None:
        return None
    parent = node.parent
    a = parent.find_next("a", href=True) if parent else None
    return a["href"] if a else None


@dataclass
class ThreadDetail:
    price: Optional[float] = None
    original_price: Optional[float] = None
    savings_text: Optional[str] = None
    expiry_text: Optional[str] = None
    merchant_url: Optional[str] = None
    ai_summary_points: list[str] = field(default_factory=list)
    ai_summary_label: Optional[str] = None


def fetch_thread_detail(rfd_url: str) -> ThreadDetail:
    """Scrape the structured deal fields and AI summary (if any) off a
    thread page. Robust to markup/CSS changes: matches on RFD's own
    user-facing label text rather than class names.
    """
    with _client() as client:
        resp = client.get(rfd_url)
        resp.raise_for_status()
        html = resp.text
    return parse_thread_detail(html)


def parse_thread_detail(html: str) -> ThreadDetail:
    """Parse a thread page's HTML into a ThreadDetail. Split out from
    fetch_thread_detail() so it's unit-testable against a saved fixture.
    """
    soup = BeautifulSoup(html, "lxml")

    price = _parse_money(_label_value(soup, "Price:"))
    original_price = _parse_money(_label_value(soup, "Original Price:"))
    savings_text = _label_value(soup, "Savings:")
    expiry_text = _label_value(soup, "Expiry:")
    merchant_url = _label_link(soup, "Deal Link:")

    ai_points: list[str] = []
    ai_label: Optional[str] = None
    summary_heading = soup.find(string=re.compile(r"Thread Summary"))
    if summary_heading is not None:
        # Bulleted summary points sit between the "Thread Summary" heading
        # and the "AI-generated summary - <date>" attribution line.
        label_node = soup.find(string=re.compile(r"AI-generated summary"))
        if label_node is not None:
            ai_label = label_node.strip()
        container = summary_heading.parent
        if container is not None:
            for li in container.find_all_next(["li", "p"]):
                text = li.get_text(" ", strip=True)
                if not text:
                    continue
                if text.startswith("AI-generated summary"):
                    break
                ai_points.append(text)
                if len(ai_points) >= 12:  # safety cap, not a real limit case
                    break

    return ThreadDetail(
        price=price,
        original_price=original_price,
        savings_text=savings_text,
        expiry_text=expiry_text,
        merchant_url=merchant_url,
        ai_summary_points=ai_points,
        ai_summary_label=ai_label,
    )


def summary_hash(points: list[str]) -> str:
    basis = "\n".join(points)
    return hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()


@dataclass
class RelatedResult:
    title: str
    url: str
    forum: Optional[str]
    posted_at_text: Optional[str]


def _normalize_search_terms(title: str) -> str:
    """Strip price/promo noise out of a deal title to get better search
    recall on RFD's own search, e.g. turn
    '[Costco] Level Ground Coffee $48.99 after $15 off' into
    'Level Ground Coffee'.
    """
    text = re.sub(r"\$[\d,.]+", " ", title)
    text = re.sub(r"\b\d+%\b", " ", text)
    noise = r"\b(after|off|save|clearance|now|only|for|sale|deal|ymmv|w/|with)\b"
    text = re.sub(noise, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^\w\s]", " ", text)
    words = [w for w in text.split() if len(w) > 1]
    return " ".join(words[:6])  # keep it short - RFD search does best with a few keywords


def find_related_deals(title: str, exclude_thread_id: Optional[int] = None, limit: int = 5) -> list[RelatedResult]:
    """Search RFD for prior threads about the same/similar product, scoped
    to the Expired Hot Deals forum.
    """
    keywords = _normalize_search_terms(title)
    if not keywords:
        return []

    url = f"{BASE}/search.php?keywords={quote_plus(keywords)}&sf=titleonly"
    with _client() as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text

    return parse_search_results(html, exclude_thread_id=exclude_thread_id, limit=limit)


def parse_search_results(
    html: str, exclude_thread_id: Optional[int] = None, limit: int = 5
) -> list[RelatedResult]:
    """Parse an RFD search-results page, keeping only Expired Hot Deals
    hits. Split out from find_related_deals() so it's unit-testable
    against a saved fixture.
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[RelatedResult] = []
    seen_thread_ids: set[int] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        thread_id = extract_thread_id(href)
        if thread_id is None:
            continue
        if exclude_thread_id is not None and thread_id == exclude_thread_id:
            continue
        if thread_id in seen_thread_ids:
            continue  # a thread can appear more than once per result row (title + snippet links)

        result_title = link.get_text(" ", strip=True)
        if not result_title:
            continue

        # The forum name ("Hot Deals" / "Expired Hot Deals") is rendered
        # near each result row; walk up to the row container and look for it.
        row = link.find_parent(["li", "div", "tr"])
        forum_name = None
        if row is not None:
            row_text = row.get_text(" ", strip=True)
            fm = re.search(r"(Expired Hot Deals|Hot Deals)", row_text)
            if fm:
                forum_name = fm.group(1)

        if forum_name != "Expired Hot Deals":
            continue  # only interested in prior *expired* threads for this feature

        full_url = href if href.startswith("http") else f"{BASE}{href}"
        seen_thread_ids.add(thread_id)
        results.append(
            RelatedResult(
                title=result_title,
                url=full_url.split("#")[0],
                forum=forum_name,
                posted_at_text=None,
            )
        )
        if len(results) >= limit:
            break

    return results
