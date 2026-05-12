"""Admin endpoints: manual triggers + scheduler introspection.

All routes here require an authenticated admin user.
"""
from __future__ import annotations

from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.scheduler import _scheduler  # type: ignore[attr-defined]
from app.services.billing_sweep import run_billing_sweep
from app.services.notification_dispatcher import dispatch_pending_notifications


router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


@router.post("/run-billing-sweep")
def trigger_billing_sweep(
    as_of: str | None = Query(None, description="Optional YYYY-MM-DD (defaults to today, UTC)"),
    db: Session = Depends(get_db),
    _: User = Depends(_require_admin),
):
    """Run the daily billing sweep on demand. Returns the same report
    structure the scheduler logs after each scheduled run."""
    as_of_date: date | None = None
    if as_of:
        try:
            as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD")
    report = run_billing_sweep(db, as_of=as_of_date)
    return report.to_dict()


@router.post("/dispatch-notifications")
def trigger_dispatch_notifications(
    db: Session = Depends(get_db),
    _: User = Depends(_require_admin),
):
    """Drain pending notifications through the configured provider on demand."""
    report = dispatch_pending_notifications(db)
    return report.to_dict()


@router.get("/scheduler")
def scheduler_status(_: User = Depends(_require_admin)):
    """Show whether the scheduler is running and when each job next fires."""
    if _scheduler is None or not _scheduler.running:
        return {"running": False, "jobs": []}
    jobs = []
    for j in _scheduler.get_jobs():
        jobs.append({
            "id": j.id,
            "name": j.name,
            "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    return {"running": True, "jobs": jobs}
