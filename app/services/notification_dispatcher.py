"""Dispatch pending notifications via the configured provider.

The dispatcher is provider-agnostic; it only knows how to:
  - find unsent notifications
  - call ``provider.send(notification)``
  - update delivery state (sent_at / delivery_attempts / last_error)
  - cap retries at ``settings.NOTIFICATION_MAX_ATTEMPTS``

Failures are tolerated per-row: one bad notification never blocks the
others.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.notification import Notification
from app.services.notification_providers import NotificationProvider, build_provider


@dataclass
class DispatchReport:
    scanned: int = 0
    sent: int = 0
    failed: int = 0
    skipped_max_attempts: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def dispatch_pending_notifications(
    db: Session,
    provider: NotificationProvider | None = None,
    limit: int = 200,
) -> DispatchReport:
    """Deliver all unsent notifications (up to `limit`).

    Notifications that have already failed `NOTIFICATION_MAX_ATTEMPTS`
    times are skipped so a single broken row can't burn retries forever;
    operators can inspect them via ``GET /notifications`` and clear
    ``last_error`` / ``delivery_attempts`` to retry manually.
    """
    if provider is None:
        provider = build_provider()
    max_attempts = settings.NOTIFICATION_MAX_ATTEMPTS

    pending = (
        db.query(Notification)
        .filter(Notification.is_sent.is_(False))
        .order_by(Notification.created_at.asc())
        .limit(limit)
        .all()
    )
    report = DispatchReport()

    for n in pending:
        report.scanned += 1
        if n.delivery_attempts >= max_attempts:
            report.skipped_max_attempts += 1
            continue
        try:
            provider.send(n)
        except Exception as exc:  # noqa: BLE001 - provider may raise anything
            n.delivery_attempts = (n.delivery_attempts or 0) + 1
            n.last_error = str(exc)[:1000]
            report.failed += 1
            db.add(n)
            continue
        n.is_sent = True
        n.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)  # store naive UTC
        n.delivery_attempts = (n.delivery_attempts or 0) + 1
        n.last_error = None
        report.sent += 1
        db.add(n)

    db.commit()
    return report
