"""Daily billing sweep.

Walks every active policy, re-evaluates payment status, auto-lapses
policies that have crossed the configured arrears threshold, and emits
notifications + audit-log entries for missed payments and lapses.

The function is intentionally synchronous and DB-session-driven so it
can be:
  - Triggered on a schedule (APScheduler - see `app.scheduler`)
  - Triggered manually via an admin endpoint
  - Called directly from tests
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.customer import Customer, CustomerStatus
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.policy import Policy, PolicyStatus
from app.services import billing
from app.services.notifications import notify_missed_payment, notify_policy_lapsed


@dataclass
class SweepReport:
    """Summary of work performed by a single sweep run."""
    as_of: str
    policies_scanned: int = 0
    policies_lapsed: int = 0
    customers_lapsed: int = 0
    missed_payment_notifications: int = 0
    total_outstanding: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_outstanding"] = str(self.total_outstanding)
        return d


def _has_recent_missed_notification(db: Session, policy_id: int, month_key: str) -> bool:
    """Idempotency guard - avoid producing duplicate MISSED_PAYMENT rows
    for the same (policy, month) when the sweep is re-run."""
    needle = f"in {month_key}"
    return (
        db.query(Notification.id)
        .filter(
            Notification.policy_id == policy_id,
            Notification.type == "MISSED_PAYMENT",
            Notification.message.contains(needle),
        )
        .first()
        is not None
    )


def run_billing_sweep(db: Session, as_of: date | None = None) -> SweepReport:
    """Re-evaluate every active policy.

    Side effects:
      - active policies whose arrears >= threshold are marked `lapsed`
        (with an audit entry + POLICY_LAPSED notification)
      - For each month currently OVERDUE, emit a MISSED_PAYMENT
        notification - **once** per (policy, month) thanks to the
        idempotency guard
      - Active customers whose policies are ALL lapsed are marked
        `lapsed` themselves

    Returns a :class:`SweepReport` so callers (admin endpoint, log,
    metrics) can see what happened.
    """
    if as_of is None:
        as_of = date.today()
    report = SweepReport(as_of=as_of.isoformat())

    active_policies = db.query(Policy).filter(Policy.status == PolicyStatus.active).all()
    for policy in active_policies:
        report.policies_scanned += 1
        payments = db.query(Payment).filter(Payment.policy_id == policy.id).all()
        months, arrears, outstanding = billing.compute_policy_status(policy, payments, as_of=as_of)
        report.total_outstanding += outstanding

        # Emit (idempotent) missed-payment notifications for every overdue month.
        for m in months:
            if m.status != billing.STATUS_OVERDUE:
                continue
            key = billing.month_key(m.month_start)
            if _has_recent_missed_notification(db, policy.id, key):
                continue
            notify_missed_payment(
                db,
                customer_id=policy.customer_id,
                policy_id=policy.id,
                month=key,
            )
            report.missed_payment_notifications += 1

        # Lapse the policy if arrears exceed the threshold.
        if billing.should_lapse(policy, arrears):
            policy.status = PolicyStatus.lapsed
            notify_policy_lapsed(db, customer_id=policy.customer_id, policy_id=policy.id)
            log_action(
                db, actor="system", action="LAPSE_POLICY",
                entity_type="policy", entity_id=policy.id,
                details={"arrears": arrears, "as_of": as_of.isoformat()},
            )
            report.policies_lapsed += 1

    # Customer-level lapse propagation: any customer whose policies are all lapsed.
    active_customers = db.query(Customer).filter(Customer.status == CustomerStatus.active).all()
    for customer in active_customers:
        ps = db.query(Policy).filter(Policy.customer_id == customer.id).all()
        if ps and all(p.status == PolicyStatus.lapsed for p in ps):
            customer.status = CustomerStatus.lapsed
            log_action(
                db, actor="system", action="LAPSE_CUSTOMER",
                entity_type="customer", entity_id=customer.id,
            )
            report.customers_lapsed += 1

    db.commit()

    # Refresh business-level Prometheus gauges. Imported lazily so the
    # billing module stays usable when `prometheus-fastapi-instrumentator`
    # isn't installed (e.g. a slim worker image).
    try:
        from sqlalchemy import func
        from app.core.observability import active_policies_gauge, lapsed_policies_gauge
        active = db.query(func.count(Policy.id)).filter(Policy.status == PolicyStatus.active).scalar() or 0
        lapsed = db.query(func.count(Policy.id)).filter(Policy.status == PolicyStatus.lapsed).scalar() or 0
        active_policies_gauge.set(active)
        lapsed_policies_gauge.set(lapsed)
    except Exception:  # noqa: BLE001 - never let a metric blip break the sweep
        pass

    return report
