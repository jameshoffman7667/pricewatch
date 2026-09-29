"""Business logic for the RFD Hot Deals feed: ingesting new threads,
refreshing detail/AI-summary data, finding related expired threads, and
handing a deal's merchant link off to PriceWatch's own monitor for
ongoing price history.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Optional
from urllib.parse import quote_plus, urlparse

from sqlmodel import Session, select

from . import rfd
from .db import engine
from .models import Monitor, RfdDeal, RfdRelatedDeal
from .scheduler import schedule_monitor

logger = logging.getLogger("pricewatch.rfd")

FEED_POLL_INTERVAL_MINUTES = 5
SUMMARY_REFRESH_INTERVAL_MINUTES = 10


def run_feed_poll_job():
    """APScheduler entry point: ingest any new Hot Deals threads."""
    with Session(engine) as session:
        created = ingest_new_deals(session)
        if created:
            logger.info("RFD feed poll: ingested %d new deal(s)", created)


def run_summary_refresh_job():
    """APScheduler entry point: recheck unread deals for AI-summary/price updates."""
    with Session(engine) as session:
        refresh_unread_summaries(session)


def ingest_new_deals(session: Session) -> int:
    """Poll the Hot Deals feed and insert any threads we haven't seen yet.
    Returns the number of new deals created.
    """
    try:
        entries = rfd.fetch_feed()
    except Exception:
        logger.exception("Failed to fetch RFD feed")
        return 0

    created = 0
    for entry in entries:
        existing = session.exec(
            select(RfdDeal).where(RfdDeal.thread_id == entry.thread_id)
        ).first()
        if existing is not None:
            continue

        deal = RfdDeal(
            thread_id=entry.thread_id,
            title=entry.title,
            retailer=entry.retailer,
            rfd_url=entry.rfd_url,
            author=entry.author,
            thumbnail_url=entry.thumbnail_url,
            posted_at=_parse_iso(entry.published),
        )
        session.add(deal)
        session.commit()
        session.refresh(deal)
        created += 1

        # Fetch structured detail (price fields, merchant link, AI summary)
        # right away so a brand-new deal isn't missing everything until the
        # next poll cycle.
        refresh_deal_detail(session, deal)
        find_and_store_related(session, deal)

    return created


def _parse_iso(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def refresh_deal_detail(session: Session, deal: RfdDeal) -> RfdDeal:
    """(Re-)fetch a deal's thread page and update price/summary fields.
    Safe to call repeatedly - only writes when something actually changed,
    and always updates last_polled_at so staleness is visible.
    """
    now = dt.datetime.utcnow()
    try:
        detail = rfd.fetch_thread_detail(deal.rfd_url)
    except Exception:
        logger.exception("Failed to fetch RFD thread detail for %s", deal.rfd_url)
        deal.last_polled_at = now
        session.add(deal)
        session.commit()
        return deal

    if detail.price is not None:
        deal.price = detail.price
    if detail.original_price is not None:
        deal.original_price = detail.original_price
    if detail.savings_text:
        deal.savings_text = detail.savings_text
    if detail.expiry_text:
        deal.expiry_text = detail.expiry_text
    if detail.merchant_url:
        deal.merchant_url = detail.merchant_url

    if detail.ai_summary_points:
        new_hash = rfd.summary_hash(detail.ai_summary_points)
        if new_hash != deal.ai_summary_hash:
            deal.ai_summary = "\n".join(f"- {p}" for p in detail.ai_summary_points)
            deal.ai_summary_hash = new_hash
            deal.ai_summary_label = detail.ai_summary_label

    deal.last_polled_at = now
    deal.detail_fetched_at = now
    session.add(deal)
    session.commit()
    session.refresh(deal)

    maybe_auto_monitor(session, deal)
    return deal


def refresh_unread_summaries(session: Session, limit: int = 25) -> int:
    """Re-check AI summaries (and other detail fields) for unread deals.
    Run on a schedule so deals nobody is actively viewing still catch up
    once RFD generates/updates a summary; also called synchronously from
    the detail-page route so viewing an unread deal always checks fresh.
    """
    deals = session.exec(
        select(RfdDeal).where(RfdDeal.read == False).limit(limit)  # noqa: E712
    ).all()
    for deal in deals:
        refresh_deal_detail(session, deal)
    return len(deals)


def find_and_store_related(session: Session, deal: RfdDeal) -> list[RfdRelatedDeal]:
    """Search RFD for prior expired threads on the same/similar product and
    cache the results so the detail page doesn't re-search on every view.
    """
    try:
        found = rfd.find_related_deals(deal.title, exclude_thread_id=deal.thread_id)
    except Exception:
        logger.exception("Failed to search RFD related deals for %s", deal.title)
        return []

    existing_urls = {
        r.url
        for r in session.exec(
            select(RfdRelatedDeal).where(RfdRelatedDeal.rfd_deal_id == deal.id)
        ).all()
    }

    created = []
    for r in found:
        if r.url in existing_urls:
            continue
        row = RfdRelatedDeal(
            rfd_deal_id=deal.id,
            title=r.title,
            url=r.url,
            forum=r.forum,
        )
        session.add(row)
        created.append(row)

    if created:
        session.commit()
    return created


# ------------------------------------------------------ price history helpers

_AMAZON_HOST_RE = re.compile(r"amazon\.(ca|com)$", re.IGNORECASE)


def price_history_links(merchant_url: Optional[str], title: str) -> list[dict]:
    """Outbound "view price history" links for a deal. No paid price-history
    API is used (Keepa etc.) - these are plain deep/search links to
    third-party trackers, per the "outbound links only" decision.
    """
    links: list[dict] = []
    if not merchant_url:
        return links

    host = (urlparse(merchant_url).hostname or "").lower()
    query = quote_plus(title)

    if _AMAZON_HOST_RE.search(host):
        links.append({"name": "CamelCamelCamel", "url": f"https://camelcamelcamel.com/search?sq={query}"})
        links.append({"name": "Keepa", "url": f"https://keepa.com/#!search/{query}"})
    else:
        links.append({"name": "RetailRadar.ca", "url": f"https://retailradar.ca/search?q={query}"})
        links.append({"name": "PriceDropper.ca", "url": f"https://www.pricedropper.ca/search?q={query}"})

    return links


# ------------------------------------------------------ auto-monitor hook

def maybe_auto_monitor(session: Session, deal: RfdDeal) -> Optional[Monitor]:
    """Create a PriceWatch Monitor on the deal's merchant link the first
    time we see one, so our own free/unlimited price history starts
    accumulating from day one. Idempotent - does nothing if a monitor
    already exists for this deal or the deal has no merchant link yet.
    """
    if deal.monitor_id is not None or not deal.merchant_url:
        return None

    monitor = Monitor(
        name=f"[RFD] {deal.title}"[:200],
        url=deal.merchant_url,
        selector_type="auto",
        interval_minutes=180,  # deal prices don't need minute-level polling
        notify_on_any_change=False,
        notify_on_price_drop=True,
    )
    session.add(monitor)
    session.commit()
    session.refresh(monitor)

    deal.monitor_id = monitor.id
    session.add(deal)
    session.commit()

    schedule_monitor(monitor)
    return monitor
