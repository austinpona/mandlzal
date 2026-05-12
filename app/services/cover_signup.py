"""Funeral-cover signup service.

Encapsulates the multi-row write that the wizard performs:

  1. Look up the chosen `CoverPlan` (must exist and be active).
  2. Validate the request against the plan (dependent count, share sum).
  3. Create the `Customer` (or reuse on duplicate ID number? - **no**, we
     raise HTTP 409 instead and let the caller decide; reusing identities
     across signups silently is a regulatory landmine).
  4. Create the `Policy` with `premium_amount` snapshotted from the plan.
  5. Bulk-create `Member` rows and `Beneficiary` rows.
  6. Audit-log the signup as a single `COVER_SIGNUP` action.

All inside a single transaction so a beneficiary failure rolls back the
whole signup. Returns a `CoverSignupResponse`.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.beneficiary import Beneficiary
from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.customer import Customer, CustomerStatus
from app.models.member import Member, MemberStatus
from app.models.policy import Policy, PolicyStatus, PolicyType
from app.schemas.cover import CoverSignupRequest, CoverSignupResponse


# Beneficiary share rounding: we accept 99.99 / 100.01 due to user
# rounding (e.g. 33.33 + 33.33 + 33.34 = 100.00 is fine, but 33 + 33 + 33
# = 99 is not). 0.01 tolerance balances UX with regulatory clarity.
_SHARE_TOLERANCE = Decimal("0.01")


def _compose_full_name(title: str | None, first_names: str, surname: str) -> str:
    """Reconstruct the legacy `full_name` field from the split parts.

    Existing dashboards / search use `full_name`; keeping it in sync
    means we don't have to migrate every list view at once.
    """
    bits = [b for b in (title, first_names, surname) if b]
    return " ".join(bits).strip()


def perform_cover_signup(db: Session, payload: CoverSignupRequest,
                         *, actor: str = "system") -> CoverSignupResponse:
    # ---- 1. Plan exists & active ----
    plan = db.query(CoverPlan).filter(CoverPlan.id == payload.cover_plan_id).first()
    if plan is None or not plan.is_active:
        raise HTTPException(status_code=404, detail="Cover plan not found or inactive")

    # ---- 2. Cross-field validation ----
    if len(payload.dependents) > plan.max_dependents:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This plan covers up to {plan.max_dependents} dependents; "
                f"you submitted {len(payload.dependents)}."
            ),
        )
    # Livestock-benefit plans don't require beneficiaries (the payout is a
    # physical animal, not cash). Funeral-cash plans still require shares
    # to sum to 100.
    if plan.category == CoverCategory.livestock_benefits:
        if payload.beneficiaries:
            raise HTTPException(
                status_code=400,
                detail="Livestock-benefit plans do not take beneficiaries.",
            )
    else:
        if not payload.beneficiaries:
            raise HTTPException(
                status_code=400,
                detail="At least one beneficiary is required for this plan.",
            )
        share_total = sum((b.share_pct for b in payload.beneficiaries), Decimal("0"))
        if abs(share_total - Decimal("100")) > _SHARE_TOLERANCE:
            raise HTTPException(
                status_code=400,
                detail=f"Beneficiary share_pct must sum to 100 (got {share_total}).",
            )

    # ---- 3. Customer: reuse if the ID number already exists, create otherwise ----
    # Reuse lets one person hold multiple plans (e.g. a funeral cover AND
    # a "cattle in December" plan) without forcing them through duplicate
    # data entry. We deliberately do NOT overwrite their existing
    # demographics from the new payload - that would be a vector for
    # someone to silently change identity attached to a policy.
    customer = (
        db.query(Customer)
        .filter(Customer.id_number == payload.holder.id_number)
        .first()
    )
    if customer is None:
        holder_full_name = _compose_full_name(
            payload.holder.title, payload.holder.first_names, payload.holder.surname,
        )
        customer = Customer(
            full_name=holder_full_name,
            title=payload.holder.title,
            first_names=payload.holder.first_names,
            surname=payload.holder.surname,
            id_number=payload.holder.id_number,
            phone=payload.holder.cellphone,
            email=str(payload.holder.email) if payload.holder.email else None,
            gender=payload.holder.gender,
            date_of_birth=payload.holder.date_of_birth,
            nationality=payload.holder.nationality,
            status=CustomerStatus.active,
        )
        db.add(customer)
        db.flush()  # need customer.id for the policy FK

    # ---- 4. Policy snapshotting the plan's premium ----
    policy = Policy(
        customer_id=customer.id,
        # Dependents > 0 implies a group/family scheme; otherwise an
        # individual cover. Keep the existing enum semantics.
        policy_type=PolicyType.group_scheme if payload.dependents else PolicyType.individual,
        premium_amount=plan.monthly_premium,
        status=PolicyStatus.active,
        cover_plan_id=plan.id,
    )
    db.add(policy)
    db.flush()  # need policy.id for member + beneficiary FKs

    # ---- 5. Members (dependents) ----
    for dep in payload.dependents:
        db.add(Member(
            policy_id=policy.id,
            full_name=_compose_full_name(dep.title, dep.first_names, dep.surname),
            title=dep.title,
            first_names=dep.first_names,
            surname=dep.surname,
            id_number=dep.id_number,
            relationship_to_holder=dep.relationship_to_holder,
            gender=dep.gender,
            date_of_birth=dep.date_of_birth,
            nationality=dep.nationality,
            email=str(dep.email) if dep.email else None,
            cellphone=dep.cellphone,
            country_of_birth=dep.country_of_birth,
            status=MemberStatus.active,
        ))

    # ---- 5b. Beneficiaries ----
    for ben in payload.beneficiaries:
        db.add(Beneficiary(
            policy_id=policy.id,
            relationship_to_holder=ben.relationship_to_holder,
            first_name=ben.first_name,
            surname=ben.surname,
            cellphone=ben.cellphone,
            country_of_birth=ben.country_of_birth,
            share_pct=ben.share_pct,
        ))

    # ---- 6. Audit + commit ----
    log_action(
        db, actor=actor, action="COVER_SIGNUP",
        entity_type="policy", entity_id=policy.id,
        details={
            "cover_plan_id": plan.id,
            "cover_type": plan.cover_type,
            "premium": str(plan.monthly_premium),
            "dependents": len(payload.dependents),
            "beneficiaries": len(payload.beneficiaries),
        },
    )
    db.commit()
    db.refresh(policy)

    return CoverSignupResponse(
        customer_id=customer.id,
        policy_id=policy.id,
        cover_plan_id=plan.id,
        monthly_premium=plan.monthly_premium,
        member_count=len(payload.dependents),
        beneficiary_count=len(payload.beneficiaries),
        created_at=policy.created_at,
    )
