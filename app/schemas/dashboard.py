"""Dashboard summary schemas."""
from decimal import Decimal
from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_customers: int
    active_customers: int
    lapsed_customers: int
    cancelled_customers: int
    total_policies: int
    active_policies: int
    lapsed_policies: int
    paid_this_month: int
    unpaid_this_month: int
    overdue_this_month: int
    revenue_this_month: Decimal
    expected_revenue_this_month: Decimal
