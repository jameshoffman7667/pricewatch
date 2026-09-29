"""Page fetching: fast httpx path, with a headless-browser (Playwright)
path for JS-rendered sites - the thing paid tools charge extra for.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 PriceWatch/1.0"
)


@dataclass
class FetchResult:
    html: str
    status_code: int
    screenshot_path: Optional[str] = None


def fetch_static(
    url: str,
    user_agent: Optional[str] = None,
    headers: Optional[dict] = None,
    cookies: Optional[dict] = None,
    timeout: float = 20.0,
) -> FetchResult:
    hdrs = {"User-Agent": user_agent or DEFAULT_UA}
    if headers:
        hdrs.update(headers)
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=hdrs, cookies=cookies) as client:
        resp = client.get(url)
        return FetchResult(html=resp.text, status_code=resp.status_code)


def fetch_rendered(
    url: str,
    wait_for_selector: Optional[str] = None,
    user_agent: Optional[str] = None,
    cookies: Optional[dict] = None,
    screenshot_dir: Optional[str] = None,
    capture_screenshot: bool = False,
    timeout_ms: int = 30000,
) -> FetchResult:
    """Render the page in headless Chromium via Playwright.

    Imported lazily so the base httpx-only path works even if the
    browser isn't installed yet (and so unit tests don't need it).
    """
    from playwright.sync_api import sync_playwright

    screenshot_path = None
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(user_agent=user_agent or DEFAULT_UA)
            if cookies:
                context.add_cookies(
                    [
                        {"name": k, "value": v, "url": url}
                        for k, v in cookies.items()
                    ]
                )
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
                except Exception:
                    pass
            html = page.content()
            if capture_screenshot and screenshot_dir:
                os.makedirs(screenshot_dir, exist_ok=True)
                fname = f"{uuid.uuid4().hex}.png"
                screenshot_path = os.path.join(screenshot_dir, fname)
                page.screenshot(path=screenshot_path, full_page=True)
            return FetchResult(html=html, status_code=200, screenshot_path=screenshot_path)
        finally:
            browser.close()


def fetch(monitor, screenshot_dir: Optional[str] = None) -> FetchResult:
    headers = json.loads(monitor.headers_json) if monitor.headers_json else None
    cookies = json.loads(monitor.cookies_json) if monitor.cookies_json else None

    if monitor.render_js:
        return fetch_rendered(
            monitor.url,
            wait_for_selector=monitor.wait_for_selector,
            user_agent=monitor.user_agent,
            cookies=cookies,
            screenshot_dir=screenshot_dir,
            capture_screenshot=monitor.capture_screenshot,
        )
    return fetch_static(
        monitor.url,
        user_agent=monitor.user_agent,
        headers=headers,
        cookies=cookies,
    )
