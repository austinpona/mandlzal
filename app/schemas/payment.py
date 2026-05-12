"""Payment Pydantic schemas + payment-status response types."""
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentCreate(BaseModel):
    customer_id: int
    policy_id: int
    member_id: int | None = None
    amount_paid: Decimal = Field(..., gt=0)
    payment_date: date | None = None
    payment_method: PaymentMethod = PaymentMethod.debit_order
    status: PaymentStatus = PaymentStatus.paid
    reference: str | None = None


class PaymentOut(BaseModel):
    id: int
    customer_id: int
    policy_id: int
    member_id: int | None
    amount_paid: Decimal
    payment_date: date
    payment_method: PaymentMethod
    status: PaymentStatus
    reference: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonthPaymentStatus(BaseModel):
    """Status of a policy for a single month period (YYYY-MM)."""
    month: str  # YYYY-MM
    expected_amount: Decimal
    paid_amount: Decimal
    status: str  # PAID | NOT_PAID | OVERDUE | PARTIAL


class PolicyPaymentStatus(BaseModel):
    policy_id: int
    status: str  # active | lapsed | cancelled
    months_in_arrears: int
    total_outstanding: Decimal
    months: list[MonthPaymentStatus]


class CustomerPaymentStatusResponse(BaseModel):
    customer_id: int
    overall_status: str  # PAID | NOT_PAID | OVERDUE
    policies: list[PolicyPaymentStatus]
