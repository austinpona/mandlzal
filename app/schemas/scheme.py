"""Pydantic schemas for the /schemes endpoints."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_serializer

from app.models.cover_plan import SchemeType


# Display labels for each scheme tab. Used in API responses and (mirrored)
# in the frontend types module.
_LABELS: dict[SchemeType, str] = {
    SchemeType.funeral: "Funeral",
    SchemeType.stokvel: "Stokvel",
    SchemeType.purchase: "Purchase",
    SchemeType.goat_purchase: "Goat purchase",
    SchemeType.wedding: "Wedding",
    SchemeType.party: "Party",
    SchemeType.breeding: "Breeding",
    SchemeType.farming: "Farming",
}


def scheme_label(scheme: SchemeType) -> str:
    return _LABELS[scheme]


class SchemeOverviewResponse(BaseModel):
    scheme_type: SchemeType
    label: str
    active_customers: int
    lapsed_customers: int
    active_policies: int
    lapsed_policies: int
    paid_this_month: int
    unpaid_this_month: int
    overdue_this_month: int
    revenue_this_month: Decimal
    expected_revenue_this_month: Decimal
    plan_count: int

    @field_serializer("revenue_this_month", "expected_revenue_this_month")
    def serialize_decimal(self, value: Decimal) -> str:
        return f"{value:.2f}"
