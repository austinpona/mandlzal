"""APScheduler wiring.

Spins up a background scheduler in the FastAPI process that runs the
daily billing sweep at a configurable UTC time. The scheduler is created
inside the app lifespan so it shares the process and stops cleanly on
shutdown.

For multi-replica deployments use a shared lock (e.g. database advisory
lock or Redis) or move the sweep to a dedicated worker process to avoid
running the job N times. The simplest production toggle is
``SCHEDULER_ENABLED=0`` on all replicas except one.
"""
from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.services.billing_sweep import run_billing_sweep
from app.services.notification_dispatcher import dispatch_pending_notifications


log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _do_sweep() -> None:
    """Job body: open a session, run the sweep, log the report."""
    db = SessionLocal()
    try:
        report = run_billing_sweep(db)
        log.info("Billing sweep complete: %s", report.to_dict())
    except Exception:  # noqa: BLE001
        log.exception("Billing sweep failed")
    finally:
        db.close()


def _do_dispatch() -> None:
    """Job body: send any unsent notifications via the configured provider."""
    db = SessionLocal()
    try:
        report = dispatch_pending_notifications(db)
        if report.scanned:
            log.info("Notification dispatch: %s", report.to_dict())
    except Exception:  # noqa: BLE001
        log.exception("Notification dispatch failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    """Start the daily sweep job. Idempotent; returns the running scheduler."""
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        log.info("Scheduler disabled via SCHEDULER_ENABLED=0")
        return None
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _do_sweep,
        trigger=CronTrigger(
            hour=settings.SWEEP_HOUR_UTC,
            minute=settings.SWEEP_MINUTE_UTC,
            timezone="UTC",
        ),
        id="daily_billing_sweep",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    _scheduler.add_job(
        _do_dispatch,
        trigger=IntervalTrigger(
            minutes=max(1, settings.NOTIFICATION_DISPATCH_INTERVAL_MINUTES),
        ),
        id="notification_dispatch",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    _scheduler.start()
    log.info(
        "Scheduler started: sweep @ %02d:%02d UTC, dispatch every %d min (provider=%s)",
        settings.SWEEP_HOUR_UTC, settings.SWEEP_MINUTE_UTC,
        settings.NOTIFICATION_DISPATCH_INTERVAL_MINUTES,
        settings.NOTIFICATION_PROVIDER,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
    _scheduler = None
