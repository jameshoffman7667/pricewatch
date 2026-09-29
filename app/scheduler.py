from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session, select

from .checker import run_check
from .db import engine
from .models import Monitor

logger = logging.getLogger("pricewatch.scheduler")

scheduler = BackgroundScheduler()


def _job_id(monitor_id: int) -> str:
    return f"monitor-{monitor_id}"


def run_monitor_job(monitor_id: int):
    with Session(engine) as session:
        monitor = session.get(Monitor, monitor_id)
        if monitor is None or not monitor.enabled:
            return
        run_check(session, monitor)


def schedule_monitor(monitor: Monitor):
    job_id = _job_id(monitor.id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if not monitor.enabled:
        return
    scheduler.add_job(
        run_monitor_job,
        trigger=IntervalTrigger(minutes=max(1, monitor.interval_minutes)),
        args=[monitor.id],
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,  # first run scheduled after one interval; use run_now to trigger immediately
    )


def unschedule_monitor(monitor_id: int):
    job_id = _job_id(monitor_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def load_all_and_start():
    if not scheduler.running:
        scheduler.start()
    with Session(engine) as session:
        monitors = session.exec(select(Monitor)).all()
        for m in monitors:
            schedule_monitor(m)
    logger.info("Scheduler started with %d monitors", len(list(scheduler.get_jobs())))
