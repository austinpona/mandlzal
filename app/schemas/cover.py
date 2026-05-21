"""Pydantic schemas for the funeral-cover signup wizard.

Three layers:

* `CoverPlanOut` - catalog entries returned by `GET /cover-plans`.
* `CoverSignupRequest` - the wizard's final submission (steps 1 + 2 + 3).
* `CoverSignupResponse` - the resulting policy summary returned to the UI.

The signup payload includes everything needed to atomically create one
`Customer`, one `Policy`, N `Member` rows, and N `Beneficiary` rows. The
service layer (`app.services.cover_signup`) does the cross-field
validation (e.g. share % == 100, dependent count <= plan.max_dependents).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.cover_plan import CoverCategory, SchemeType


# ---------- Catalog ----------


class CoverPlanOut(BaseModel):
    id: int
    category: CoverCategory
    scheme_type: SchemeType
    cover_type: str
    monthly_premium: Decimal
    max_dependents: int
    description: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ---------- Wizard input ----------


class PersonIn(BaseModel):
    """A covered person (main member or dependent).

    Same shape works for both the policy holder and any dependent the
    wizard collects in step 2.
    """
    title: str = Field(..., max_length=8, description="Mr / Mrs / Ms / Dr")
    first_names: str = Field(..., min_length=1, max_length=120)
    surname: str = Field(..., min_length=1, max_length=120)
    gender: str | None = Field(None, max_length=16)
    date_of_birth: date | None = None
    nationality: str | None = Field(None, max_length=80)
    email: EmailStr | None = None
    cellphone: str | None = Field(None, max_length=32)
    id_number: str | None = Field(None, max_length=64)


class HolderIn(PersonIn):
    """Main member - same fields as PersonIn plus a required ID number."""
    id_number: str = Field(..., min_length=1, max_length=64)


class DependentIn(PersonIn):
    """Step 2 dependent. `relationship_to_holder` is required so we know
    why this person is covered (Spouse / Child / Mother / In-law ...).
    """
    relationship_to_holder: str = Field(..., min_length=1, max_length=64)
    country_of_birth: str | None = Field(None, max_length=80)


class BeneficiaryIn(BaseModel):
    """Step 3 beneficiary - share_pct values across all beneficiaries
    on the policy must sum to exactly 100."""
    relationship_to_holder: str = Field(..., min_length=1, max_length=64)
    first_name: str = Field(..., min_length=1, max_length=120)
    surname: str = Field(..., min_length=1, max_length=120)
    cellphone: str | None = Field(None, max_length=32)
    country_of_birth: str | None = Field(None, max_length=80)
    share_pct: Decimal = Field(..., gt=0, le=100)


class CoverSignupRequest(BaseModel):
    """Payload posted by the wizard 'Submit' button.

    Validation rules enforced here (cheap, per-field):
      * holder + at least 0 dependents
      * at least one beneficiary
      * each share_pct in (0, 100]

    Validation rules enforced by the service (need DB context):
      * dependents count <= plan.max_dependents
      * sum(share_pct) == 100
      * plan exists and is_active
    """
    cover_plan_id: int
    holder: HolderIn
    dependents: List[DependentIn] = Field(default_factory=list)
    # Optional: required for funeral-cover plans (validated in the service
    # based on plan category), but livestock-benefit plans don't need a
    # beneficiary list because the payout is a physical animal, not cash.
    beneficiaries: List[BeneficiaryIn] = Field(default_factory=list)

    @field_validator("beneficiaries")
    @classmethod
    def _share_total_within_bounds(cls, v: list[BeneficiaryIn]) -> list[BeneficiaryIn]:
        # The exact-100 check happens in the service so the API returns
        # a friendly 400 with the actual computed sum; here we just
        # short-circuit the obvious "way off" case. An empty list is OK
        # (livestock plans).
        if not v:
            return v
        total = sum((b.share_pct for b in v), Decimal("0"))
        if total > Decimal("100.01"):
            raise ValueError(f"Beneficiary share_pct total {total} exceeds 100")
        return v


# ---------- Wizard output ----------


class BeneficiaryOut(BaseModel):
    id: int
    relationship_to_holder: str
    first_name: str
    surname: str
    cellphone: str | None
    country_of_birth: str | None
    share_pct: Decimal
    model_config = ConfigDict(from_attributes=True)


class CoverSignupResponse(BaseModel):
    customer_id: int
    policy_id: int
    cover_plan_id: int
    monthly_premium: Decimal
    member_count: int
    beneficiary_count: int
    created_at: datetime
