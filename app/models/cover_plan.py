"""Cover plan catalog - the products offered to new signups.

A `CoverPlan` row maps one cell of the (category x cover_type) grid in
the funeral-cover wizard to a flat monthly premium and a member cap.
The signup endpoint copies `monthly_premium` onto the resulting
`Policy.premium_amount` so changing a plan price later doesn't
retroactively repriced existing customers.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, Numeric, Boolean

from app.database import Base


class CoverCategory(str, enum.Enum):
    """Top-level categories shown in the wizard dropdown.

    The first four mirror the original funeral-cash-cover product line.
    `livestock_benefits` was added later for non-cash add-ons (a cow at
    the funeral, an animal slaughtered in December, etc.). Livestock
    plans have no covered members/beneficiaries - they're a savings
    pot the customer pays into.
    """
    me = "me"
    me_and_family = "me_and_family"
    parents_and_inlaws = "parents_and_inlaws"
    extended_family = "extended_family"
    livestock_benefits = "livestock_benefits"


class CoverPlan(Base):
    __tablename__ = "cover_plans"

    id = Column(Integer, primary_key=True)
    # The two-level dropdown structure from the mockup:
    #   Category (1 of 4)  ->  Cover Type (a label specific to that category)
    category = Column(Enum(CoverCategory), nullable=False, index=True)
    cover_type = Column(String(80), nullable=False)
    # Flat monthly premium for this plan, regardless of how many of the
    # allowed dependents the customer actually adds. (See README.)
    monthly_premium = Column(Numeric(12, 2), nullable=False)
    # Hard ceiling on how many `Member` rows can be attached to a policy
    # created from this plan. `1` means main member only (no dependents).
    max_dependents = Column(Integer, nullable=False, default=0)
    # Free-text shown in the UI ("Covers main + 4 dependents.").
    description = Column(String(500), nullable=True)
    # Soft-disable a plan without deleting it (keeps existing policies intact).
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
