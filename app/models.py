"""Database models for PriceWatch.

No artificial limits are placed on the number of monitors, checks, or
history entries anywhere in this schema or the code that uses it -
that is the whole point of self-hosting this instead of paying for a
SaaS plan that caps you at N pages or N checks/month.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


class Monitor(SQLModel, table=True):
    """A single URL being watched for price/content changes."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    url: str
    # How to find the price/content on the page.
    selector: Optional[str] = None          # CSS selector (Distill-style)
    selector_type: str = "css"              # "css" | "jsonpath" | "regex" | "auto"
    extra_regex: Optional[str] = None       # optional regex applied to selector's text
    # Fetch behavior
    render_js: bool = False                 # use headless browser (Playwright)
    wait_for_selector: Optional[str] = None
    user_agent: Optional[str] = None
    headers_json: Optional[str] = None      # JSON-encoded extra headers
    cookies_json: Optional[str] = None      # JSON-encoded cookies

    # Scheduling
    interval_minutes: int = 60
    enabled: bool = True

    # Alerting rules (Prisync-style conditions, evaluated on every check)
    notify_on_any_change: bool = True
    notify_on_price_drop: bool = True
    notify_on_price_rise: bool = False
    min_change_percent: float = 0.0         # only notify if abs(% change) >= this
    min_change_absolute: float = 0.0        # only notify if abs($ change) >= this
    target_price: Optional[float] = None    # notify when price <= this (drop-below alert)

    # Visual / screenshot monitoring (Visualping-style), only when render_js
    capture_screenshot: bool = False

    currency: Optional[str] = None

    created_at: dt.datetime = Field(default_factory=utcnow)
    updated_at: dt.datetime = Field(default_factory=utcnow)

    # Cached latest state, kept denormalized for fast dashboard rendering.
    last_checked_at: Optional[dt.datetime] = None
    last_status: Optional[str] = None       # "ok" | "error" | "unchanged" | "changed"
    last_error: Optional[str] = None
    last_price: Optional[float] = None
    last_raw_text: Optional[str] = None
    last_content_hash: Optional[str] = None


class Snapshot(SQLModel, table=True):
    """One historical check result for a monitor. Unlimited retention."""

    id: Optional[int] = Field(default=None, primary_key=True)
    monitor_id: int = Field(foreign_key="monitor.id", index=True)
    checked_at: dt.datetime = Field(default_factory=utcnow, index=True)
    status: str                              # "ok" | "error"
    price: Optional[float] = None
    raw_text: Optional[str] = None
    content_hash: Optional[str] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    changed: bool = False
    notified: bool = False


class NotificationChannel(SQLModel, table=True):
    """An Apprise notification target (email, Slack, Discord, webhook, ...)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    apprise_url: str
    enabled: bool = True
    created_at: dt.datetime = Field(default_factory=utcnow)


class RfdDeal(SQLModel, table=True):
    """A RedFlagDeals Hot Deals forum thread, ingested from their Atom feed
    and enriched from the thread page (price fields, AI summary, merchant
    link). No cap on how many are kept - same philosophy as everything
    else in this app.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: int = Field(index=True, unique=True)
    title: str
    retailer: Optional[str] = None          # parsed from the "[Retailer]" title prefix
    price: Optional[float] = None
    original_price: Optional[float] = None
    savings_text: Optional[str] = None      # e.g. "Save 23%"
    expiry_text: Optional[str] = None
    rfd_url: str                            # canonical thread URL on RFD
    merchant_url: Optional[str] = None      # "Deal Link" target on the retailer's site
    thumbnail_url: Optional[str] = None
    author: Optional[str] = None
    vote_score: Optional[int] = None
    reply_count: Optional[int] = None

    posted_at: Optional[dt.datetime] = None
    first_seen_at: dt.datetime = Field(default_factory=utcnow)
    last_polled_at: Optional[dt.datetime] = None
    detail_fetched_at: Optional[dt.datetime] = None

    # AI-generated thread summary (RFD's own feature). Re-checked on every
    # refresh for unread deals so an initially-missing or stale summary
    # catches up without the user having to do anything.
    ai_summary: Optional[str] = None
    ai_summary_label: Optional[str] = None   # RFD's own "AI-generated summary - <date>" string
    ai_summary_hash: Optional[str] = None    # to detect when the summary text changes

    read: bool = False
    favourited: bool = False

    # Set once a PriceWatch Monitor is auto-created for this deal's merchant_url.
    monitor_id: Optional[int] = Field(default=None, foreign_key="monitor.id")


class RfdRelatedDeal(SQLModel, table=True):
    """A previous (often expired) RFD thread that looks like it's for the
    same/similar product, found via RFD's own search. Cached at ingest time
    so the detail page doesn't re-search on every view.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    rfd_deal_id: int = Field(foreign_key="rfddeal.id", index=True)
    title: str
    url: str
    forum: Optional[str] = None             # e.g. "Expired Hot Deals"
    posted_at_text: Optional[str] = None    # RFD's own rendered date string, kept as-is
    found_at: dt.datetime = Field(default_factory=utcnow)
