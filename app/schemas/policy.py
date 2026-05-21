"""Policy Pydantic schemas."""
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.models.policy import PolicyType, PolicyStatus, BillingCycle


class PolicyBase(BaseModel):
    customer_id: int
    policy_type: PolicyType = PolicyType.individual
    premium_amount: Decimal = Field(..., gt=0)
    billing_cycle: BillingCycle = BillingCycle.monthly
    start_date: date | None = None
    grace_period_days: int | None = None
    lapse_threshold_months: int | None = None


class PolicyCreate(PolicyBase):
    pass


class PolicyUpdate(BaseModel):
    premium_amount: Decimal | None = None
    status: PolicyStatus | None = None
    grace_period_days: int | None = None
    lapse_threshold_months: int | None = None


class PolicyOut(BaseModel):
    id: int
    customer_id: int
    policy_type: PolicyType
    premium_amount: Decimal
    billing_cycle: BillingCycle
    start_date: date
    status: PolicyStatus
    grace_period_days: int | None
    lapse_threshold_months: int | None
    cover_plan_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
