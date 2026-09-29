"""Price/content extraction from fetched HTML.

Combines a few approaches so a single monitor config can cover most
sites without needing a paid "smart detection" tier:

- CSS selector (like Distill.io's element picker)
- Regex applied to a selector's text, or to the whole page as a fallback
- "auto" mode that scans common price-bearing attributes/classes
  (itemprop=price, data-price, .price, meta[property=product:price:amount], etc.)
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

# Matches things like $1,299.99 / €19,90 / 1.234,56 kr / 19.99
PRICE_RE = re.compile(
    r"(?P<currency>[$€£¥₹]|USD|EUR|GBP|CAD|AUD)?\s?"
    r"(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s?(?P<currency2>[$€£¥₹]|USD|EUR|GBP|CAD|AUD)?",
    re.IGNORECASE,
)

AUTO_PRICE_SELECTORS = [
    '[itemprop="price"]',
    'meta[property="product:price:amount"]',
    'meta[property="og:price:amount"]',
    "[data-price]",
    "[data-product-price]",
    ".price .amount",
    ".price-current",
    ".product-price",
    ".a-price .a-offscreen",  # amazon
    ".a-price-whole",
    ".price",
]


@dataclass
class ExtractResult:
    raw_text: Optional[str]
    price: Optional[float]
    content_hash: str
    matched_selector: Optional[str] = None


def _normalize_amount(amount: str) -> Optional[float]:
    amount = amount.strip()
    if not amount:
        return None
    # Handle "1.234,56" (EU) vs "1,234.56" (US) vs "1234.56"
    if "," in amount and "." in amount:
        if amount.rfind(",") > amount.rfind("."):
            amount = amount.replace(".", "").replace(",", ".")
        else:
            amount = amount.replace(",", "")
    elif "," in amount:
        # Could be thousands sep or decimal comma
        parts = amount.split(",")
        if len(parts[-1]) == 2:
            amount = amount.replace(",", ".")
        else:
            amount = amount.replace(",", "")
    try:
        return float(amount)
    except ValueError:
        return None


def extract_price_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    m = PRICE_RE.search(text)
    if not m:
        return None
    return _normalize_amount(m.group("amount"))


def _text_of(el) -> str:
    if el is None:
        return ""
    if el.name == "meta":
        return el.get("content", "") or ""
    if el.has_attr("data-price"):
        return el["data-price"]
    if el.has_attr("data-product-price"):
        return el["data-product-price"]
    return el.get_text(" ", strip=True)


def extract(
    html: str,
    selector: Optional[str],
    selector_type: str = "css",
    extra_regex: Optional[str] = None,
) -> ExtractResult:
    soup = BeautifulSoup(html, "lxml")

    matched_selector = None
    raw_text: Optional[str] = None

    if selector_type == "regex" and selector:
        m = re.search(selector, html)
        raw_text = m.group(0) if m else None
        matched_selector = "regex"
    elif selector_type == "css" and selector:
        el = soup.select_one(selector)
        if el is not None:
            raw_text = _text_of(el)
            matched_selector = selector
    else:
        # auto mode: try common price selectors in priority order
        for sel in AUTO_PRICE_SELECTORS:
            el = soup.select_one(sel)
            if el is not None:
                txt = _text_of(el)
                if txt and PRICE_RE.search(txt):
                    raw_text = txt
                    matched_selector = sel
                    break

    price = None
    if raw_text:
        if extra_regex:
            m = re.search(extra_regex, raw_text)
            if m:
                raw_text = m.group(1) if m.groups() else m.group(0)
        price = extract_price_from_text(raw_text)

    # Fallback: if nothing found via selector/auto, try scanning whole visible text
    if price is None and not selector:
        body_text = soup.get_text(" ", strip=True)
        price = extract_price_from_text(body_text)
        if price is not None:
            raw_text = raw_text or body_text[:200]

    basis = raw_text if raw_text is not None else soup.get_text(" ", strip=True)
    content_hash = hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()

    return ExtractResult(
        raw_text=raw_text,
        price=price,
        content_hash=content_hash,
        matched_selector=matched_selector,
    )
