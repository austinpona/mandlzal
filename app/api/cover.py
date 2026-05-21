"""Funeral-cover wizard endpoints.

* `GET /cover-plans` - drives the category + cover-type dropdowns on
  step 1 of the wizard. Public (no auth) so anonymous signup pages can
  load the catalog.
* `POST /cover-signup` - submits the wizard. Public for self-service;
  an admin doing on-behalf-of signup can call the same endpoint while
  logged in (in which case the audit log records their user id).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.database import get_db
from app.models.cover_plan import CoverCategory, CoverPlan, SchemeType
from app.models.user import User
from app.schemas.cover import (
    CoverPlanOut,
    CoverSignupRequest,
    CoverSignupResponse,
)
from app.services.cover_signup import perform_cover_signup


router = APIRouter(tags=["cover"])


@router.get("/cover-plans", response_model=List[CoverPlanOut])
def list_cover_plans(
    category: CoverCategory | None = Query(None, description="Filter to one category"),
    scheme_type: SchemeType | None = Query(None, description="Filter to one scheme tab"),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
) -> List[CoverPlan]:
    """Return the cover plan catalog, optionally filtered by category or scheme type."""
    q = db.query(CoverPlan)
    if category is not None:
        q = q.filter(CoverPlan.category == category)
    if scheme_type is not None:
        q = q.filter(CoverPlan.scheme_type == scheme_type)
    if not include_inactive:
        q = q.filter(CoverPlan.is_active.is_(True))
    return q.order_by(CoverPlan.category, CoverPlan.monthly_premium).all()


@router.post("/cover-signup", response_model=CoverSignupResponse, status_code=201)
def submit_cover_signup(
    payload: CoverSignupRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> CoverSignupResponse:
    """Atomically create customer + policy + members + beneficiaries.

    Anonymous callers are allowed (public self-service). When a logged-in
    user submits this (e.g. an agent doing assisted signup), the actor
    recorded in the audit log is their email instead of `system`.
    """
    actor = current_user.email if current_user is not None else "system"
    return perform_cover_signup(db, payload, actor=actor)
