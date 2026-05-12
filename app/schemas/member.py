"""Member (group scheme) schemas."""
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.member import MemberStatus


class MemberCreate(BaseModel):
    policy_id: int
    full_name: str = Field(..., min_length=1, max_length=255)
    id_number: str | None = None
    relationship_to_holder: str | None = None
    contribution_amount: Decimal | None = None


class MemberUpdate(BaseModel):
    full_name: str | None = None
    relationship_to_holder: str | None = None
    contribution_amount: Decimal | None = None
    status: MemberStatus | None = None


class MemberOut(BaseModel):
    id: int
    policy_id: int
    full_name: str
    id_number: str | None
    relationship_to_holder: str | None
    contribution_amount: Decimal | None
    status: MemberStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberPaymentStatus(BaseModel):
    member_id: int
    full_name: str
    status: str  # PAID | NOT_PAID | OVERDUE
    months_in_arrears: int
    total_outstanding: Decimal
