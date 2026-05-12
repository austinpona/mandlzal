"""Group-scheme member endpoints + per-member payment status."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_writer
from app.core.audit import log_action
from app.database import get_db
from app.models.member import Member
from app.models.payment import Payment
from app.models.policy import Policy
from app.models.user import User
from app.schemas.member import MemberCreate, MemberOut, MemberPaymentStatus, MemberUpdate
from app.services import billing


router = APIRouter(prefix="/members", tags=["members"])


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: MemberCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_writer),
) -> Member:
    policy = db.get(Policy, payload.policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    member = Member(**payload.model_dump())
    db.add(member)
    db.flush()
    log_action(db, actor=current.email, action="CREATE_MEMBER",
               entity_type="member", entity_id=member.id, details=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(member)
    return member


@router.get("/policy/{policy_id}", response_model=list[MemberOut])
def list_members_for_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Member]:
    return db.query(Member).filter(Member.policy_id == policy_id).all()


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_writer),
) -> Member:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    updates = payload.model_dump(exclude_unset=True)
    for f, v in updates.items():
        setattr(member, f, v)
    log_action(db, actor=current.email, action="UPDATE_MEMBER",
               entity_type="member", entity_id=member.id, details=updates)
    db.commit()
    db.refresh(member)
    return member


@router.get("/policy/{policy_id}/payment-status", response_model=list[MemberPaymentStatus])
def members_payment_status(
    policy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[MemberPaymentStatus]:
    """Per-member payment status for a group scheme.

    Treats each member's `contribution_amount` (falling back to the
    policy premium) as the expected amount per month, against only the
    payments linked to that member.
    """
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    members = db.query(Member).filter(Member.policy_id == policy_id).all()

    out: list[MemberPaymentStatus] = []
    today = date.today()
    for m in members:
        expected_per_month = Decimal(m.contribution_amount) if m.contribution_amount is not None else Decimal(policy.premium_amount)
        # Build a temporary policy-like shadow by overriding premium for calc
        shadow = Policy(
            customer_id=policy.customer_id,
            policy_type=policy.policy_type,
            premium_amount=expected_per_month,
            billing_cycle=policy.billing_cycle,
            start_date=policy.start_date,
            status=policy.status,
            grace_period_days=policy.grace_period_days,
            lapse_threshold_months=policy.lapse_threshold_months,
        )
        payments = db.query(Payment).filter(Payment.member_id == m.id).all()
        months, arrears, outstanding = billing.compute_policy_status(shadow, payments, as_of=today)
        # Member-level status summary
        if any(ms.status == billing.STATUS_OVERDUE for ms in months):
            status_label = billing.STATUS_OVERDUE
        elif any(ms.status in (billing.STATUS_NOT_PAID, billing.STATUS_PARTIAL) for ms in months):
            status_label = billing.STATUS_NOT_PAID
        else:
            status_label = billing.STATUS_PAID
        out.append(MemberPaymentStatus(
            member_id=m.id,
            full_name=m.full_name,
            status=status_label,
            months_in_arrears=arrears,
            total_outstanding=outstanding,
        ))
    return out
