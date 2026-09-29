from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from apscheduler.triggers.interval import IntervalTrigger

from . import rfd_jobs
from .checker import run_check
from .db import engine, init_db, get_session, SCREENSHOT_DIR
from .models import Monitor, NotificationChannel, RfdDeal, RfdRelatedDeal, Snapshot
from .notify import send_notification
from .scheduler import load_all_and_start, schedule_monitor, unschedule_monitor, run_monitor_job, scheduler

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PriceWatch", description="Self-hosted price & page change monitor")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/screenshots", StaticFiles(directory=SCREENSHOT_DIR), name="screenshots")


@app.on_event("startup")
def on_startup():
    init_db()
    load_all_and_start()

    # RFD Hot Deals feed: poll for new threads, and separately recheck
    # unread deals for AI-summary/price updates - both on their own
    # schedule, independent of PriceWatch's per-monitor intervals.
    scheduler.add_job(
        rfd_jobs.run_feed_poll_job,
        trigger=IntervalTrigger(minutes=rfd_jobs.FEED_POLL_INTERVAL_MINUTES),
        id="rfd-feed-poll",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        # Fire the first poll almost immediately (in the background, off
        # the request thread) rather than waiting a full interval, so the
        # Deals tab isn't empty on a fresh install - but don't block
        # startup itself doing it, since ingesting dozens of new threads
        # each does 2-3 outbound HTTP requests.
        next_run_time=dt.datetime.now(),
    )
    scheduler.add_job(
        rfd_jobs.run_summary_refresh_job,
        trigger=IntervalTrigger(minutes=rfd_jobs.SUMMARY_REFRESH_INTERVAL_MINUTES),
        id="rfd-summary-refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


# ---------------------------------------------------------------- helpers

def _bool(v) -> bool:
    return v in ("on", "true", "1", True, 1)


def _monitor_from_form(form: dict, existing: Optional[Monitor] = None) -> Monitor:
    m = existing or Monitor(name="", url="")
    m.name = form.get("name") or form.get("url", "")
    m.url = form["url"]
    m.selector = form.get("selector") or None
    m.selector_type = form.get("selector_type") or "auto"
    m.extra_regex = form.get("extra_regex") or None
    m.render_js = _bool(form.get("render_js"))
    m.wait_for_selector = form.get("wait_for_selector") or None
    m.interval_minutes = int(form.get("interval_minutes") or 60)
    m.enabled = _bool(form.get("enabled", "on"))
    m.notify_on_any_change = _bool(form.get("notify_on_any_change"))
    m.notify_on_price_drop = _bool(form.get("notify_on_price_drop"))
    m.notify_on_price_rise = _bool(form.get("notify_on_price_rise"))
    m.min_change_percent = float(form.get("min_change_percent") or 0)
    m.min_change_absolute = float(form.get("min_change_absolute") or 0)
    tp = form.get("target_price")
    m.target_price = float(tp) if tp not in (None, "") else None
    m.capture_screenshot = _bool(form.get("capture_screenshot"))
    return m


# ---------------------------------------------------------------- UI routes

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with Session(engine) as session:
        monitors = session.exec(select(Monitor).order_by(Monitor.created_at.desc())).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "monitors": monitors})


@app.get("/monitors/new", response_class=HTMLResponse)
def new_monitor_form(request: Request):
    return templates.TemplateResponse("monitor_form.html", {"request": request, "monitor": None})


@app.post("/monitors")
async def create_monitor(request: Request):
    form = dict(await request.form())
    with Session(engine) as session:
        m = _monitor_from_form(form)
        session.add(m)
        session.commit()
        session.refresh(m)
        schedule_monitor(m)
        run_monitor_job(m.id)  # check immediately so the dashboard isn't empty
    return RedirectResponse(f"/monitors/{m.id}", status_code=303)


@app.get("/monitors/{monitor_id}", response_class=HTMLResponse)
def monitor_detail(request: Request, monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if not monitor:
            raise HTTPException(404)
        snapshots = session.exec(
            select(Snapshot)
            .where(Snapshot.monitor_id == monitor_id)
            .order_by(Snapshot.checked_at.desc())
            .limit(200)
        ).all()
    history = [
        {"t": s.checked_at.isoformat(), "price": s.price}
        for s in reversed(snapshots)
        if s.price is not None
    ]
    return templates.TemplateResponse(
        "monitor_detail.html",
        {"request": request, "monitor": monitor, "snapshots": snapshots, "history_json": json.dumps(history)},
    )


@app.get("/monitors/{monitor_id}/edit", response_class=HTMLResponse)
def edit_monitor_form(request: Request, monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if not monitor:
            raise HTTPException(404)
    return templates.TemplateResponse("monitor_form.html", {"request": request, "monitor": monitor})


@app.post("/monitors/{monitor_id}/edit")
async def update_monitor(request: Request, monitor_id: int):
    form = dict(await request.form())
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if not monitor:
            raise HTTPException(404)
        m = _monitor_from_form(form, existing=monitor)
        session.add(m)
        session.commit()
        session.refresh(m)
        schedule_monitor(m)
    return RedirectResponse(f"/monitors/{monitor_id}", status_code=303)


@app.post("/monitors/{monitor_id}/delete")
def delete_monitor(monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if monitor:
            unschedule_monitor(monitor_id)
            snaps = session.exec(select(Snapshot).where(Snapshot.monitor_id == monitor_id)).all()
            for s in snaps:
                session.delete(s)
            session.delete(monitor)
            session.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/monitors/{monitor_id}/check-now")
def check_now(monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if not monitor:
            raise HTTPException(404)
        run_check(session, monitor)
    return RedirectResponse(f"/monitors/{monitor_id}", status_code=303)


@app.post("/monitors/{monitor_id}/toggle")
def toggle_monitor(monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if not monitor:
            raise HTTPException(404)
        monitor.enabled = not monitor.enabled
        session.add(monitor)
        session.commit()
        session.refresh(monitor)
        schedule_monitor(monitor)
    return RedirectResponse(request_referer_fallback(monitor_id), status_code=303)


def request_referer_fallback(monitor_id: int) -> str:
    return f"/monitors/{monitor_id}"


# ------------------------------------------------------------------ deals UI
# RedFlagDeals Hot Deals feed: unread/read/favourited tabs, a detail page
# with the AI summary + outbound links, and mark-read/favourite actions.

VALID_TABS = ("unread", "read", "favourited")


@app.get("/deals", response_class=HTMLResponse)
def deals_list(request: Request, tab: str = "unread"):
    if tab not in VALID_TABS:
        tab = "unread"
    with Session(engine) as session:
        stmt = select(RfdDeal)
        if tab == "unread":
            stmt = stmt.where(RfdDeal.read == False)  # noqa: E712
        elif tab == "read":
            stmt = stmt.where(RfdDeal.read == True)  # noqa: E712
        else:  # favourited
            stmt = stmt.where(RfdDeal.favourited == True)  # noqa: E712
        stmt = stmt.order_by(RfdDeal.first_seen_at.desc())
        deals = session.exec(stmt).all()
        counts = {
            "unread": len(session.exec(select(RfdDeal).where(RfdDeal.read == False)).all()),  # noqa: E712
            "read": len(session.exec(select(RfdDeal).where(RfdDeal.read == True)).all()),  # noqa: E712
            "favourited": len(session.exec(select(RfdDeal).where(RfdDeal.favourited == True)).all()),  # noqa: E712
        }
    return templates.TemplateResponse(
        "deals_list.html",
        {"request": request, "deals": deals, "tab": tab, "counts": counts},
    )


@app.post("/deals/mark-all-read")
def deals_mark_all_read(tab: str = "unread"):
    with Session(engine) as session:
        deals = session.exec(select(RfdDeal).where(RfdDeal.read == False)).all()  # noqa: E712
        for d in deals:
            d.read = True
            session.add(d)
        session.commit()
    return RedirectResponse(f"/deals?tab={tab}", status_code=303)


@app.get("/deals/{deal_id}", response_class=HTMLResponse)
def deal_detail(request: Request, deal_id: int):
    with Session(engine) as session:
        deal = session.get(RfdDeal, deal_id)
        if not deal:
            raise HTTPException(404)

        # "Check back every refresh for updates to any unread deal's AI
        # summary": do a live re-fetch right here, synchronously, whenever
        # an unread deal's page is opened - on top of the background
        # refresh job that covers deals nobody is actively viewing.
        if not deal.read:
            deal = rfd_jobs.refresh_deal_detail(session, deal)

        related = session.exec(
            select(RfdRelatedDeal)
            .where(RfdRelatedDeal.rfd_deal_id == deal_id)
            .order_by(RfdRelatedDeal.found_at.desc())
        ).all()

        monitor = session.get(Monitor, deal.monitor_id) if deal.monitor_id else None
        history_json = "[]"
        if monitor is not None:
            snaps = session.exec(
                select(Snapshot)
                .where(Snapshot.monitor_id == monitor.id, Snapshot.price != None)  # noqa: E711
                .order_by(Snapshot.checked_at.asc())
                .limit(200)
            ).all()
            history_json = json.dumps([{"t": s.checked_at.isoformat(), "price": s.price} for s in snaps])

    price_links = rfd_jobs.price_history_links(deal.merchant_url, deal.title)

    return templates.TemplateResponse(
        "deal_detail.html",
        {
            "request": request,
            "deal": deal,
            "related": related,
            "monitor": monitor,
            "history_json": history_json,
            "price_links": price_links,
        },
    )


@app.post("/deals/{deal_id}/read")
def deal_mark_read(deal_id: int, read: bool = True, tab: str = "unread"):
    with Session(engine) as session:
        deal = session.get(RfdDeal, deal_id)
        if not deal:
            raise HTTPException(404)
        deal.read = read
        session.add(deal)
        session.commit()
    return RedirectResponse(f"/deals?tab={tab}", status_code=303)


@app.post("/deals/{deal_id}/favourite")
def deal_toggle_favourite(deal_id: int, tab: str = "unread"):
    with Session(engine) as session:
        deal = session.get(RfdDeal, deal_id)
        if not deal:
            raise HTTPException(404)
        deal.favourited = not deal.favourited
        session.add(deal)
        session.commit()
    return RedirectResponse(f"/deals?tab={tab}", status_code=303)


@app.post("/deals/{deal_id}/refresh")
def deal_refresh(deal_id: int):
    """Manually force a re-check of a single deal's price/AI summary."""
    with Session(engine) as session:
        deal = session.get(RfdDeal, deal_id)
        if not deal:
            raise HTTPException(404)
        rfd_jobs.refresh_deal_detail(session, deal)
    return RedirectResponse(f"/deals/{deal_id}", status_code=303)


# API - mirrors the monitor API's "no paid tier needed" approach.

@app.get("/api/deals")
def api_list_deals(tab: str = "unread"):
    with Session(engine) as session:
        stmt = select(RfdDeal)
        if tab == "unread":
            stmt = stmt.where(RfdDeal.read == False)  # noqa: E712
        elif tab == "read":
            stmt = stmt.where(RfdDeal.read == True)  # noqa: E712
        elif tab == "favourited":
            stmt = stmt.where(RfdDeal.favourited == True)  # noqa: E712
        return session.exec(stmt.order_by(RfdDeal.first_seen_at.desc())).all()


@app.get("/api/deals/{deal_id}")
def api_get_deal(deal_id: int):
    with Session(engine) as session:
        deal = session.get(RfdDeal, deal_id)
        if not deal:
            raise HTTPException(404)
        return deal


@app.post("/api/deals/poll")
def api_poll_deals():
    """Trigger an immediate feed poll (normally runs on its own schedule)."""
    with Session(engine) as session:
        created = rfd_jobs.ingest_new_deals(session)
    return JSONResponse({"created": created})


# ------------------------------------------------------------ channels UI

@app.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request):
    with Session(engine) as session:
        channels = session.exec(select(NotificationChannel)).all()
    return templates.TemplateResponse("channels.html", {"request": request, "channels": channels})


@app.post("/channels")
async def create_channel(request: Request):
    form = dict(await request.form())
    with Session(engine) as session:
        c = NotificationChannel(
            name=form.get("name") or form["apprise_url"],
            apprise_url=form["apprise_url"],
            enabled=_bool(form.get("enabled", "on")),
        )
        session.add(c)
        session.commit()
    return RedirectResponse("/channels", status_code=303)


@app.post("/channels/{channel_id}/delete")
def delete_channel(channel_id: int):
    with Session(engine) as session:
        c = session.get(NotificationChannel, channel_id)
        if c:
            session.delete(c)
            session.commit()
    return RedirectResponse("/channels", status_code=303)


@app.post("/channels/{channel_id}/test")
def test_channel(channel_id: int):
    with Session(engine) as session:
        c = session.get(NotificationChannel, channel_id)
        if not c:
            raise HTTPException(404)
        send_notification([c.apprise_url], "PriceWatch test", "This is a test notification from PriceWatch.")
    return RedirectResponse("/channels", status_code=303)


# --------------------------------------------------------------- JSON API
# Full CRUD + history over HTTP, unlike the SaaS tools that gate API
# access behind a paid tier.

@app.get("/api/monitors")
def api_list_monitors():
    with Session(engine) as session:
        monitors = session.exec(select(Monitor)).all()
        return monitors


@app.get("/api/monitors/{monitor_id}")
def api_get_monitor(monitor_id: int):
    with Session(engine) as session:
        m = session.get(Monitor, monitor_id)
        if not m:
            raise HTTPException(404)
        return m


@app.post("/api/monitors")
async def api_create_monitor(request: Request):
    body = await request.json()
    with Session(engine) as session:
        m = _monitor_from_form(body)
        session.add(m)
        session.commit()
        session.refresh(m)
        schedule_monitor(m)
        return m


@app.get("/api/monitors/{monitor_id}/history")
def api_history(monitor_id: int, limit: int = 500):
    with Session(engine) as session:
        snaps = session.exec(
            select(Snapshot)
            .where(Snapshot.monitor_id == monitor_id)
            .order_by(Snapshot.checked_at.desc())
            .limit(limit)
        ).all()
        return list(reversed(snaps))


@app.post("/api/monitors/{monitor_id}/check")
def api_check_now(monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if not monitor:
            raise HTTPException(404)
        snap = run_check(session, monitor)
        return snap


@app.delete("/api/monitors/{monitor_id}")
def api_delete_monitor(monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if monitor:
            unschedule_monitor(monitor_id)
            for s in session.exec(select(Snapshot).where(Snapshot.monitor_id == monitor_id)).all():
                session.delete(s)
            session.delete(monitor)
            session.commit()
    return JSONResponse({"deleted": True})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
