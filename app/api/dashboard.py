"""Dashboard + audit endpoints."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.audit import AuditLog
from app.models.customer import Customer, CustomerStatus
from app.models.payment import Payment, PaymentStatus
from app.models.policy import Policy, PolicyStatus
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services import billing


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DashboardSummary:
    today = date.today()
    month_start = billing.first_of_month(today)

    total_customers = db.query(func.count(Customer.id)).scalar() or 0
    active_customers = db.query(func.count(Customer.id)).filter(Customer.status == CustomerStatus.active).scalar() or 0
    lapsed_customers = db.query(func.count(Customer.id)).filter(Customer.status == CustomerStatus.lapsed).scalar() or 0
    cancelled_customers = db.query(func.count(Customer.id)).filter(Customer.status == CustomerStatus.cancelled).scalar() or 0

    total_policies = db.query(func.count(Policy.id)).scalar() or 0
    active_policies = db.query(func.count(Policy.id)).filter(Policy.status == PolicyStatus.active).scalar() or 0
    lapsed_policies = db.query(func.count(Policy.id)).filter(Policy.status == PolicyStatus.lapsed).scalar() or 0

    # Revenue for current month (only paid)
    revenue = db.query(func.coalesce(func.sum(Payment.amount_paid), 0)).filter(
        Payment.status == PaymentStatus.paid,
        Payment.payment_date >= month_start,
    ).scalar() or 0

    # Per-policy classification for the current month
    paid = 0
    unpaid = 0
    overdue = 0
    expected_total = Decimal("0")
    for policy in db.query(Policy).filter(Policy.status == PolicyStatus.active).all():
        expected_total += Decimal(policy.premium_amount)
        payments = db.query(Payment).filter(Payment.policy_id == policy.id).all()
        status_label = billing.get_payment_status_for_month(policy, payments, month_start, as_of=today)
        if status_label == billing.STATUS_PAID:
            paid += 1
        elif status_label == billing.STATUS_OVERDUE:
            overdue += 1
        else:
            unpaid += 1

    return DashboardSummary(
        total_customers=total_customers,
        active_customers=active_customers,
        lapsed_customers=lapsed_customers,
        cancelled_customers=cancelled_customers,
        total_policies=total_policies,
        active_policies=active_policies,
        lapsed_policies=lapsed_policies,
        paid_this_month=paid,
        unpaid_this_month=unpaid,
        overdue_this_month=overdue,
        revenue_this_month=Decimal(revenue),
        expected_revenue_this_month=expected_total,
    )


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "actor": r.actor,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "details": r.details,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/notifications")
def list_notifications(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models.notification import Notification
    rows = db.query(Notification).order_by(Notification.created_at.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "customer_id": r.customer_id,
            "policy_id": r.policy_id,
            "type": r.type,
            "message": r.message,
            "is_sent": r.is_sent,
            "sent_at": r.sent_at,
            "delivery_attempts": r.delivery_attempts,
            "last_error": r.last_error,
            "created_at": r.created_at,
        }
        for r in rows
    ]
