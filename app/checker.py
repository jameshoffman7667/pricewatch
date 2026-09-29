"""Core check loop: fetch -> extract -> compare vs last snapshot ->
apply alert rules -> notify -> persist. Runs for every monitor on its
own schedule, with no cap on how many monitors or how often they run
(other than what your hardware and target sites tolerate).
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from sqlmodel import Session, select

from .db import SCREENSHOT_DIR
from .extract import extract
from .fetcher import fetch
from .models import Monitor, NotificationChannel, Snapshot
from .notify import send_notification

logger = logging.getLogger("pricewatch.checker")


def _get_last_snapshot(session: Session, monitor_id: int) -> Optional[Snapshot]:
    stmt = (
        select(Snapshot)
        .where(Snapshot.monitor_id == monitor_id, Snapshot.status == "ok")
        .order_by(Snapshot.checked_at.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def _should_notify(monitor: Monitor, prev_price, new_price, content_changed: bool) -> tuple[bool, str]:
    reasons = []

    if prev_price is not None and new_price is not None and prev_price != new_price:
        delta = new_price - prev_price
        pct = (delta / prev_price * 100.0) if prev_price else 0.0

        meets_threshold = abs(pct) >= monitor.min_change_percent and abs(delta) >= monitor.min_change_absolute

        if meets_threshold:
            if delta < 0 and monitor.notify_on_price_drop:
                reasons.append(f"Price dropped {abs(pct):.1f}% (${abs(delta):.2f}): {prev_price:.2f} -> {new_price:.2f}")
            elif delta > 0 and monitor.notify_on_price_rise:
                reasons.append(f"Price rose {abs(pct):.1f}% (${abs(delta):.2f}): {prev_price:.2f} -> {new_price:.2f}")

    if monitor.target_price is not None and new_price is not None and new_price <= monitor.target_price:
        reasons.append(f"Price {new_price:.2f} is at/below your target of {monitor.target_price:.2f}")

    if not reasons and content_changed and monitor.notify_on_any_change and new_price is None:
        reasons.append("Watched content changed")

    if reasons:
        return True, "; ".join(reasons)
    return False, ""


def run_check(session: Session, monitor: Monitor) -> Snapshot:
    now = dt.datetime.utcnow()
    try:
        result = fetch(monitor, screenshot_dir=SCREENSHOT_DIR if monitor.capture_screenshot else None)
        ex = extract(result.html, monitor.selector, monitor.selector_type, monitor.extra_regex)

        prev = _get_last_snapshot(session, monitor.id)
        prev_price = prev.price if prev else None
        content_changed = (prev is None) or (prev.content_hash != ex.content_hash)

        snap = Snapshot(
            monitor_id=monitor.id,
            checked_at=now,
            status="ok",
            price=ex.price,
            raw_text=ex.raw_text,
            content_hash=ex.content_hash,
            screenshot_path=result.screenshot_path,
            changed=content_changed,
        )

        monitor.last_checked_at = now
        monitor.last_status = "changed" if content_changed else "unchanged"
        monitor.last_error = None
        monitor.last_raw_text = ex.raw_text
        monitor.last_content_hash = ex.content_hash
        if ex.price is not None:
            monitor.last_price = ex.price
        monitor.updated_at = now

        should_notify, reason = _should_notify(monitor, prev_price, ex.price, content_changed)
        if should_notify:
            channels = session.exec(
                select(NotificationChannel).where(NotificationChannel.enabled == True)  # noqa: E712
            ).all()
            urls = [c.apprise_url for c in channels]
            title = f"PriceWatch: {monitor.name}"
            body = f"{reason}\n{monitor.url}"
            send_notification(urls, title, body)
            snap.notified = True

        session.add(snap)
        session.add(monitor)
        session.commit()
        session.refresh(snap)
        return snap

    except Exception as e:  # noqa: BLE001
        logger.exception("Check failed for monitor %s (%s)", monitor.id, monitor.url)
        snap = Snapshot(
            monitor_id=monitor.id,
            checked_at=now,
            status="error",
            error=str(e),
        )
        monitor.last_checked_at = now
        monitor.last_status = "error"
        monitor.last_error = str(e)
        monitor.updated_at = now
        session.add(snap)
        session.add(monitor)
        session.commit()
        session.refresh(snap)
        return snap
