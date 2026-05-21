"""Scheme-scoped overview endpoint.

`GET /schemes/{scheme_type}/overview` mirrors the global /dashboard
shape but filters by `cover_plan.scheme_type`. Pure read; reuses the
billing helpers; no side effects.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.cover_plan import CoverPlan, SchemeType
from app.models.customer import Customer, CustomerStatus
from app.models.payment import Payment, PaymentStatus
from app.models.policy import Policy, PolicyStatus
from app.models.user import User
from app.schemas.scheme import SchemeOverviewResponse, scheme_label
from app.services import billing


router = APIRouter(prefix="/schemes", tags=["schemes"])


@router.get("/{scheme_type}/overview", response_model=SchemeOverviewResponse)
def scheme_overview(
    scheme_type: SchemeType,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SchemeOverviewResponse:
    today = date.today()
    month_start = billing.first_of_month(today)

    policies_in_scheme = (
        db.query(Policy)
          .join(CoverPlan, Policy.cover_plan_id == CoverPlan.id)
          .filter(CoverPlan.scheme_type == scheme_type)
    )

    active_policies = policies_in_scheme.filter(
        Policy.status == PolicyStatus.active
    ).count()
    lapsed_policies = policies_in_scheme.filter(
        Policy.status == PolicyStatus.lapsed
    ).count()

    customer_ids = [cid for (cid,) in policies_in_scheme.with_entities(
        Policy.customer_id
    ).distinct()]
    if customer_ids:
        active_customers = db.query(func.count(Customer.id)).filter(
            Customer.id.in_(customer_ids),
            Customer.status == CustomerStatus.active,
        ).scalar() or 0
        lapsed_customers = db.query(func.count(Customer.id)).filter(
            Customer.id.in_(customer_ids),
            Customer.status == CustomerStatus.lapsed,
        ).scalar() or 0
    else:
        active_customers = 0
        lapsed_customers = 0

    plan_count = db.query(func.count(CoverPlan.id)).filter(
        CoverPlan.scheme_type == scheme_type,
        CoverPlan.is_active.is_(True),
    ).scalar() or 0

    # Per-policy month classification (mirrors /dashboard).
    paid = unpaid = overdue = 0
    expected_total = Decimal("0")
    for policy in policies_in_scheme.filter(Policy.status == PolicyStatus.active).all():
        expected_total += Decimal(policy.premium_amount)
        payments = db.query(Payment).filter(Payment.policy_id == policy.id).all()
        label = billing.get_payment_status_for_month(policy, payments, month_start, as_of=today)
        if label == billing.STATUS_PAID:
            paid += 1
        elif label == billing.STATUS_OVERDUE:
            overdue += 1
        else:
            unpaid += 1

    # Revenue this month (only Payments tied to in-scheme policies).
    revenue = Decimal("0")
    if customer_ids:
        rev_scalar = (
            db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
              .join(Policy, Payment.policy_id == Policy.id)
              .join(CoverPlan, Policy.cover_plan_id == CoverPlan.id)
              .filter(
                  CoverPlan.scheme_type == scheme_type,
                  Payment.status == PaymentStatus.paid,
                  Payment.payment_date >= month_start,
              )
              .scalar()
        )
        revenue = Decimal(rev_scalar or 0)

    return SchemeOverviewResponse(
        scheme_type=scheme_type,
        label=scheme_label(scheme_type),
        active_customers=active_customers,
        lapsed_customers=lapsed_customers,
        active_policies=active_policies,
        lapsed_policies=lapsed_policies,
        paid_this_month=paid,
        unpaid_this_month=unpaid,
        overdue_this_month=overdue,
        revenue_this_month=revenue,
        expected_revenue_this_month=expected_total,
        plan_count=plan_count,
    )
