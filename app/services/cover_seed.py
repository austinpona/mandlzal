"""Seed the funeral-cover plan catalog.

Idempotent: skip any row whose (category, cover_type) pair already
exists. Run on startup or from a CLI for both dev and prod.

The catalog mirrors the wizard mockup:

  - Me (main member only)
  - Me & Family (direct)             -> 3 cover types
  - My Parents & In-laws             -> 4 cover types
  - My Extended Family               -> 1 catch-all

Prices are placeholders; tweak per business sign-off.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Tuple

from sqlalchemy.orm import Session

from app.models.cover_plan import CoverCategory, CoverPlan, SchemeType


# (category, cover_type, scheme_type, premium, max_dependents, description)
_DEFAULT_PLANS: Iterable[Tuple[CoverCategory, str, SchemeType, Decimal, int, str]] = (
    (CoverCategory.me, "Me", SchemeType.funeral, Decimal("120.00"), 0,
     "Cover for the main member only."),

    (CoverCategory.me_and_family, "Me", SchemeType.funeral, Decimal("120.00"), 0,
     "Cover for the main member only (priced as a family plan)."),
    (CoverCategory.me_and_family, "Me and My Family", SchemeType.funeral, Decimal("360.00"), 4,
     "Main member + spouse + up to 4 children."),
    (CoverCategory.me_and_family, "Me and My Children", SchemeType.funeral, Decimal("250.00"), 4,
     "Main member + up to 4 children."),

    (CoverCategory.parents_and_inlaws, "Parent", SchemeType.funeral, Decimal("180.00"), 1,
     "Main member + one parent."),
    (CoverCategory.parents_and_inlaws, "Mother", SchemeType.funeral, Decimal("160.00"), 1,
     "Main member + mother."),
    (CoverCategory.parents_and_inlaws, "Father", SchemeType.funeral, Decimal("160.00"), 1,
     "Main member + father."),
    (CoverCategory.parents_and_inlaws, "Parents and In-laws", SchemeType.funeral, Decimal("420.00"), 4,
     "Main member + both parents + both parents-in-law."),

    (CoverCategory.extended_family, "Extended Family", SchemeType.funeral, Decimal("550.00"), 10,
     "Main member + up to 10 extended-family members."),

    (CoverCategory.livestock_benefits, "Cattle during funeral", SchemeType.funeral, Decimal("250.00"), 0,
     "Provides a cow for the family's funeral when a covered death occurs."),
    (CoverCategory.livestock_benefits, "Cattle in December", SchemeType.purchase, Decimal("200.00"), 0,
     "An annual cow slaughtered at the December family gathering."),
    (CoverCategory.livestock_benefits, "Sheep in December", SchemeType.purchase, Decimal("120.00"), 0,
     "An annual sheep slaughtered at the December family gathering."),
    (CoverCategory.livestock_benefits, "Goat in December", SchemeType.goat_purchase, Decimal("90.00"), 0,
     "An annual goat slaughtered at the December family gathering."),
)


def seed_cover_plans(db: Session) -> int:
    """Insert any missing default plans. Returns the count inserted."""
    inserted = 0
    for category, cover_type, scheme_type, premium, max_dep, desc in _DEFAULT_PLANS:
        existing = (
            db.query(CoverPlan)
            .filter(CoverPlan.category == category, CoverPlan.cover_type == cover_type)
            .first()
        )
        if existing is not None:
            continue
        db.add(CoverPlan(
            category=category,
            cover_type=cover_type,
            scheme_type=scheme_type,
            monthly_premium=premium,
            max_dependents=max_dep,
            description=desc,
            is_active=True,
        ))
        inserted += 1
    if inserted:
        db.commit()
    return inserted
