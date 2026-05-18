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
from email.message import EmailMessage
import logging
import smtplib

from sqlalchemy.orm import Session

from app.config import settings
from app.models.customer import Customer
from app.models.notification import Notification
from app.models.payment import Payment
from app.services.notification_providers import NotificationProvider, build_provider


log = logging.getLogger(__name__)


@dataclass
class DispatchReport:
    scanned: int = 0
    sent: int = 0
    failed: int = 0
    skipped_max_attempts: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    attachments: list[dict] | None = None,
) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = to
    msg["From"] = settings.NOTIFICATION_EMAIL_FROM
    msg.set_content(body)
    for att in attachments or []:
        mime = att.get("mime", "application/octet-stream")
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(
            att["content"],
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att["filename"],
        )

    provider = (settings.NOTIFICATION_EMAIL_PROVIDER or "log").lower()
    if provider == "log":
        log.info("EMAIL to=%s subject=%s attachments=%s", to, subject, len(attachments or []))
        return True
    if provider != "smtp":
        raise RuntimeError(f"Unknown NOTIFICATION_EMAIL_PROVIDER: {provider!r}")

    with smtplib.SMTP(settings.NOTIFICATION_SMTP_HOST, settings.NOTIFICATION_SMTP_PORT) as smtp:
        if settings.NOTIFICATION_SMTP_STARTTLS:
            smtp.starttls()
        if settings.NOTIFICATION_SMTP_USERNAME:
            smtp.login(settings.NOTIFICATION_SMTP_USERNAME, settings.NOTIFICATION_SMTP_PASSWORD)
        smtp.send_message(msg)
    return True


def _send_email_receipt(db: Session, notification: Notification) -> None:
    from app.services.receipt_pdf import build_receipt_data, render_receipt_pdf

    if notification.policy_id is None:
        raise RuntimeError("EMAIL_RECEIPT notification has no policy_id")
    payment = (
        db.query(Payment)
        .filter(Payment.policy_id == notification.policy_id)
        .order_by(Payment.created_at.desc())
        .first()
    )
    if payment is None:
        raise RuntimeError("No payment found for EMAIL_RECEIPT notification")
    customer = db.get(Customer, notification.customer_id)
    if customer is None or not customer.email:
        raise RuntimeError("Customer has no email address for receipt")

    data = build_receipt_data(db, payment_id=payment.id)
    pdf = render_receipt_pdf(data)
    ok = send_email(
        to=customer.email,
        subject=f"Your Mandlzi funeral cover receipt ({data['reference']})",
        body=(
            "Thank you for joining Mandlzi. Your receipt is attached.\n"
            f"Reference: {data['reference']}"
        ),
        attachments=[{
            "filename": f"{data['reference']}.pdf",
            "content": pdf,
            "mime": "application/pdf",
        }],
    )
    if not ok:
        raise RuntimeError("Email provider returned false")


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
            if n.type == "EMAIL_RECEIPT":
                _send_email_receipt(db, n)
            else:
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


dispatch_pending = dispatch_pending_notifications
