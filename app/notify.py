"""Notification fan-out via Apprise.

Apprise supports 80+ services (email, Slack, Discord, Telegram, ntfy,
Pushover, generic webhooks, ...) under one free, self-hosted library -
no per-notification-channel paywall like the SaaS tools have.
"""
from __future__ import annotations

from typing import Iterable

import apprise


def send_notification(urls: Iterable[str], title: str, body: str) -> tuple[int, int]:
    """Send to every given Apprise URL. Returns (success_count, total)."""
    urls = [u for u in urls if u]
    if not urls:
        return (0, 0)
    ap = apprise.Apprise()
    for u in urls:
        ap.add(u)
    ok = ap.notify(title=title, body=body)
    return (len(urls) if ok else 0, len(urls))
