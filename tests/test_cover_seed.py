"""Verify the cover-plan seed declares the correct scheme_type for every row."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cover_plan import CoverCategory, CoverPlan, SchemeType
from app.services.cover_seed import seed_cover_plans


# (category, cover_type) -> expected scheme_type. Mirrors the backfill
# table in the design spec § 4.3.
_EXPECTED: dict[tuple[CoverCategory, str], SchemeType] = {
    (CoverCategory.me, "Me"): SchemeType.funeral,
    (CoverCategory.me_and_family, "Me"): SchemeType.funeral,
    (CoverCategory.me_and_family, "Me and My Family"): SchemeType.funeral,
    (CoverCategory.me_and_family, "Me and My Children"): SchemeType.funeral,
    (CoverCategory.parents_and_inlaws, "Parent"): SchemeType.funeral,
    (CoverCategory.parents_and_inlaws, "Mother"): SchemeType.funeral,
    (CoverCategory.parents_and_inlaws, "Father"): SchemeType.funeral,
    (CoverCategory.parents_and_inlaws, "Parents and In-laws"): SchemeType.funeral,
    (CoverCategory.extended_family, "Extended Family"): SchemeType.funeral,
    (CoverCategory.livestock_benefits, "Cattle during funeral"): SchemeType.funeral,
    (CoverCategory.livestock_benefits, "Cattle in December"): SchemeType.purchase,
    (CoverCategory.livestock_benefits, "Sheep in December"): SchemeType.purchase,
    (CoverCategory.livestock_benefits, "Goat in December"): SchemeType.goat_purchase,
}


def test_seed_assigns_correct_scheme_type():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, future=True)
    db = Session()

    seed_cover_plans(db)

    rows = db.query(CoverPlan).all()
    actual = {(r.category, r.cover_type): r.scheme_type for r in rows}
    assert actual == _EXPECTED, (
        f"seed mismatch.\nExpected:\n{_EXPECTED}\nActual:\n{actual}"
    )
    # Every row must have a scheme_type (non-null).
    assert all(r.scheme_type is not None for r in rows)
