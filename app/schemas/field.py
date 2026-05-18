"""Pydantic schemas for the field-capture backend API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.cover_plan import CoverCategory
from app.models.payment import PaymentMethod


class FieldEnrollRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=16)
    name: str = Field(..., min_length=1, max_length=80)


class FieldEnrollResponse(BaseModel):
    device_id: int
    name: str
    device_jwt: str


class FieldCoverPlanOut(BaseModel):
    id: int
    category: CoverCategory
    cover_type: str
    monthly_premium: Decimal
    max_dependents: int
    description: str | None

    model_config = ConfigDict(from_attributes=True)


class FieldCoverPlansResponse(BaseModel):
    plans: list[FieldCoverPlanOut]


class FieldPhotoUploadResponse(BaseModel):
    id_photo_id: str
    path: str


class FieldPersonIn(BaseModel):
    title: str = Field(..., max_length=8)
    first_names: str = Field(..., min_length=1, max_length=120)
    surname: str = Field(..., min_length=1, max_length=120)
    gender: str | None = Field(None, max_length=16)
    date_of_birth: date | None = None
    nationality: str | None = Field(None, max_length=80)
    email: EmailStr | None = None
    cellphone: str | None = Field(None, max_length=32)
    country_of_birth: str | None = Field(None, max_length=80)
    id_number: str | None = Field(None, max_length=64)


class FieldHolderIn(FieldPersonIn):
    id_number: str = Field(..., min_length=1, max_length=64)


class FieldDependentIn(FieldPersonIn):
    relationship_to_holder: str = Field(..., min_length=1, max_length=64)


class FieldBeneficiaryIn(BaseModel):
    relationship_to_holder: str = Field(..., min_length=1, max_length=64)
    title: str | None = Field(None, max_length=8)
    first_name: str = Field(..., min_length=1, max_length=120)
    surname: str = Field(..., min_length=1, max_length=120)
    gender: str | None = Field(None, max_length=16)
    date_of_birth: date | None = None
    nationality: str | None = Field(None, max_length=80)
    email: EmailStr | None = None
    cellphone: str | None = Field(None, max_length=32)
    country_of_birth: str | None = Field(None, max_length=80)
    share_pct: Decimal = Field(..., gt=0, le=100)


class FieldFirstPaymentIn(BaseModel):
    amount: Decimal = Field(..., gt=0)
    method: PaymentMethod = PaymentMethod.cash
    reference: str | None = Field(None, max_length=128)
    payment_date: date | None = None


class FieldSignupIn(BaseModel):
    local_id: str = Field(..., min_length=1, max_length=80)
    cover_plan_id: int
    holder: FieldHolderIn
    id_photo_id: str | None = Field(None, max_length=255)
    dependents: list[FieldDependentIn] = Field(default_factory=list)
    beneficiaries: list[FieldBeneficiaryIn] = Field(default_factory=list)
    first_payment: FieldFirstPaymentIn | None = None
    email_receipt_requested: bool = False


class FieldSubmissionRequest(BaseModel):
    client_uuid: str = Field(..., min_length=1, max_length=36)
    signups: list[FieldSignupIn] = Field(..., min_length=1)


class FieldSubmissionResult(BaseModel):
    local_id: str
    status: Literal["ok", "error"]
    customer_id: int | None = None
    policy_id: int | None = None
    payment_id: int | None = None
    error: str | None = None


class FieldSubmissionResponse(BaseModel):
    field_submission_id: int
    results: list[FieldSubmissionResult]


class EnrollmentCodeOut(BaseModel):
    code: str
    expires_at: datetime


class DeviceOut(BaseModel):
    id: int
    name: str
    status: str
    enrolled_at: datetime
    last_seen_at: datetime | None


class DevicesResponse(BaseModel):
    devices: list[DeviceOut]
