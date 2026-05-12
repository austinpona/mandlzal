"""Trivial in-DB notification creation for missed payments.

In production this would dispatch SMS/email; here we just persist a row.
"""
from sqlalchemy.orm import Session

from app.models.notification import Notification


def notify_missed_payment(db: Session, *, customer_id: int, policy_id: int, month: str) -> Notification:
    n = Notification(
        customer_id=customer_id,
        policy_id=policy_id,
        type="MISSED_PAYMENT",
        message=f"Missed payment for policy {policy_id} in {month}",
    )
    db.add(n)
    return n


def notify_policy_lapsed(db: Session, *, customer_id: int, policy_id: int) -> Notification:
    n = Notification(
        customer_id=customer_id,
        policy_id=policy_id,
        type="POLICY_LAPSED",
        message=f"Policy {policy_id} marked as LAPSED due to missed payments",
    )
    db.add(n)
    return n
