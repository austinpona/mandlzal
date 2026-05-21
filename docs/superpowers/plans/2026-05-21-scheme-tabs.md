# Scheme-Tabs UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Segment the Mandlzi UI by scheme — Funeral / Stokvel / Purchase / Goat purchase as active sidebar tabs, Wedding / Party / Breeding / Farming as muted "Coming Soon" entries — backed by a `CoverPlan.scheme_type` enum + per-scheme overview endpoint.

**Architecture:** Add `scheme_type` enum to `CoverPlan` (one column + Alembic migration + backfill). Extend list endpoints with `?scheme_type=` filter. Add a new `GET /schemes/{type}/overview` endpoint that mirrors the global dashboard but scoped. Frontend gets a shared `SchemePage` with four sub-tab routes (Overview / Customers / Policies / Plans) and a `ComingSoonScheme` placeholder.

**Tech Stack:** Python 3 (FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, pytest, httpx, slowapi), React 18 + Vite + TypeScript + Tailwind + React Query + React Router v6. No new dependencies.

**Spec:** [docs/superpowers/specs/2026-05-21-scheme-tabs-design.md](../specs/2026-05-21-scheme-tabs-design.md)

---

## File Structure

### Backend

| Path | Status | Responsibility |
| --- | --- | --- |
| `app/models/cover_plan.py` | **Modify** | Add `SchemeType` enum; add `scheme_type` column to `CoverPlan` |
| `app/services/cover_seed.py` | **Modify** | Add `scheme_type` to each seeded plan (6-tuple instead of 5-tuple) |
| `alembic/versions/<new>_add_scheme_type.py` | **Create** | Migration: add column, backfill, NOT NULL |
| `app/api/customers.py` | **Modify** | Add `?scheme_type=` filter to `GET /customers` |
| `app/api/cover.py` | **Modify** | Add `?scheme_type=` filter to existing `GET /cover-plans` |
| `app/api/policies.py` | **Modify** | Add `GET /policies` list endpoint with `?customer_id=` and `?scheme_type=` filters (note: no list endpoint exists today) |
| `app/api/schemes.py` | **Create** | New router: `GET /schemes/{type}/overview` |
| `app/schemas/scheme.py` | **Create** | `SchemeOverviewResponse` pydantic schema; re-exports `SchemeType` |
| `app/schemas/cover.py` | **Modify** | Add `scheme_type` to `CoverPlanOut` |
| `app/schemas/policy.py` | **Modify (if needed)** | Ensure `PolicyOut` is suitable for list responses (most likely already fine) |
| `app/main.py` | **Modify** | Import + include the new `schemes` router |

### Frontend

| Path | Status | Responsibility |
| --- | --- | --- |
| `frontend/src/types.ts` | **Modify** | Add `SchemeType`, `SchemeOverviewResponse`, and an in-codebase manifest of active vs coming-soon schemes |
| `frontend/src/components/Layout.tsx` | **Modify** | Add the "Schemes" sidebar group with 4 active + 4 muted entries |
| `frontend/src/App.tsx` | **Modify** | Add `/schemes/:schemeType/*` routes |
| `frontend/src/pages/SchemePage.tsx` | **Create** | Shared scheme page (header + sub-tab bar) |
| `frontend/src/pages/scheme/OverviewTab.tsx` | **Create** | Four-card overview |
| `frontend/src/pages/scheme/CustomersTab.tsx` | **Create** | Customers list filtered by scheme |
| `frontend/src/pages/scheme/PoliciesTab.tsx` | **Create** | Policies list filtered by scheme |
| `frontend/src/pages/scheme/PlansTab.tsx` | **Create** | Plans catalog filtered by scheme |
| `frontend/src/pages/scheme/ComingSoonScheme.tsx` | **Create** | Placeholder page for muted scheme entries |

### Tests

| Path | Status | Responsibility |
| --- | --- | --- |
| `tests/test_alembic.py` | **Modify** | Add `cover_plans` to `EXPECTED_TABLES`; `test_metadata_matches_migration` already guards drift |
| `tests/test_cover_seed.py` | **Create** | Verify every seeded row has the expected `scheme_type` |
| `tests/test_customers.py` | **Modify** | Add `?scheme_type=` filter tests |
| `tests/test_policies.py` | **Modify** | Add list-endpoint tests including `?scheme_type=` and `?customer_id=` |
| `tests/test_cover_plans.py` (or extend `tests/test_cover_signup.py`) | **Modify/Create** | Add `?scheme_type=` filter test on `GET /cover-plans` |
| `tests/test_schemes_overview.py` | **Create** | Empty scheme, mixed dataset, auth-required cases |
| `tests/test_playwright_scheme_tabs.py` | **Create** | One happy-path UI test |

---

## Task 1: Add `SchemeType` enum and `scheme_type` column to the model + seed

This task ONLY touches Python — no migration yet. The Alembic test will fail until Task 2 lands, so we expect `pytest tests/test_alembic.py::test_metadata_matches_migration` to be red between Task 1 and Task 2. That's the desired TDD red state.

**Files:**
- Modify: `app/models/cover_plan.py`
- Modify: `app/services/cover_seed.py`
- Modify: `app/schemas/cover.py`
- Create: `tests/test_cover_seed.py`

- [ ] **Step 1: Write the failing seed test**

Create `tests/test_cover_seed.py`:

```python
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
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `pytest tests/test_cover_seed.py -v`

Expected: **FAIL** with `ImportError: cannot import name 'SchemeType' from 'app.models.cover_plan'`.

- [ ] **Step 3: Add the `SchemeType` enum and `scheme_type` column**

Edit `app/models/cover_plan.py`. After the existing `class CoverCategory` block, add:

```python
class SchemeType(str, enum.Enum):
    """Top-level scheme tabs in the UI.

    The first four are active and have seeded plans (or, in Stokvel's
    case, will once the goal-savings engine ships). The remaining four
    are rendered as "Coming Soon" placeholders in the sidebar.
    """
    funeral = "funeral"
    stokvel = "stokvel"
    purchase = "purchase"
    goat_purchase = "goat_purchase"
    wedding = "wedding"
    party = "party"
    breeding = "breeding"
    farming = "farming"
```

In the existing `class CoverPlan(Base)`, add a new column **after `category`**:

```python
    # Which top-level scheme tab this plan belongs to. Set explicitly
    # per plan; backfilled for existing rows by the
    # `<rev>_add_scheme_type` migration.
    scheme_type = Column(Enum(SchemeType), nullable=False, index=True)
```

- [ ] **Step 4: Update the seed**

Edit `app/services/cover_seed.py`. Change the import line:

```python
from app.models.cover_plan import CoverCategory, CoverPlan, SchemeType
```

Change the type alias on `_DEFAULT_PLANS` to a 6-tuple and add `scheme_type` to every row. Replace the entire `_DEFAULT_PLANS` block with:

```python
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
```

Change the `seed_cover_plans` loop body to unpack the new tuple and set `scheme_type`. Replace the existing `for` loop body with:

```python
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
```

- [ ] **Step 5: Extend `CoverPlanOut` so the API returns `scheme_type`**

Edit `app/schemas/cover.py`. Update the import:

```python
from app.models.cover_plan import CoverCategory, SchemeType
```

Add `scheme_type` to `CoverPlanOut`:

```python
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
```

- [ ] **Step 6: Run the seed test and confirm it passes**

Run: `pytest tests/test_cover_seed.py -v`

Expected: **PASS**. 1 passed.

- [ ] **Step 7: Commit**

```bash
git add app/models/cover_plan.py app/services/cover_seed.py app/schemas/cover.py tests/test_cover_seed.py
git commit -m "Add SchemeType enum and CoverPlan.scheme_type column" -m "Adds an 8-value SchemeType enum (funeral, stokvel, purchase, goat_purchase, wedding, party, breeding, farming) and a NOT NULL scheme_type column on CoverPlan. Seed updated so every row declares its scheme_type. CoverPlanOut returns it. No migration yet — test_alembic.test_metadata_matches_migration will be red until the next task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Alembic migration — add column, backfill, NOT NULL

**Files:**
- Create: `alembic/versions/<rev>_add_scheme_type.py`
- Modify: `tests/test_alembic.py`

- [ ] **Step 1: Confirm `test_metadata_matches_migration` is red**

Run: `pytest tests/test_alembic.py::test_metadata_matches_migration -v`

Expected: **FAIL**. The autogenerate diff will list a missing `scheme_type` column on `cover_plans`. This is the red state — Task 1 added the model column, this task adds the migration.

- [ ] **Step 2: Add `cover_plans` to the expected-tables set**

Edit `tests/test_alembic.py`. The migration that introduced `cover_plans` already exists (`a7d1f3b9c2e4_cover_signup`); the expected-tables set just hasn't caught up. Update:

```python
EXPECTED_TABLES = {
    "users", "customers", "policies", "members",
    "payments", "audit_logs", "notifications",
    "cover_plans",
}
```

- [ ] **Step 3: Generate the migration scaffold**

Run from the repo root:

```bash
alembic revision -m "add scheme_type to cover_plans"
```

This creates `alembic/versions/<timestamp>_<hash>_add_scheme_type_to_cover_plans.py`. Open that file.

- [ ] **Step 4: Fill in upgrade and downgrade**

Replace the body of the new migration file with (keep the revision IDs as alembic generated them; leave the existing `revision` / `down_revision` lines untouched):

```python
"""add scheme_type to cover_plans

Revision ID: <auto>
Revises: b2e4a8d1c5f7
Create Date: <auto>
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic — DO NOT EDIT manually.
# (alembic fills these in; the down_revision must be the prior head,
# `b2e4a8d1c5f7`.)
revision: str = ...
down_revision: Union[str, None] = ...
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCHEME_VALUES = (
    "funeral", "stokvel", "purchase", "goat_purchase",
    "wedding", "party", "breeding", "farming",
)

# Backfill mapping. Mirrors design spec § 4.3.
# Each row is (category, cover_type or None for all-in-category, scheme_type).
_BACKFILL: list[tuple[str, str | None, str]] = [
    ("me", None, "funeral"),
    ("me_and_family", None, "funeral"),
    ("parents_and_inlaws", None, "funeral"),
    ("extended_family", None, "funeral"),
    ("livestock_benefits", "Cattle during funeral", "funeral"),
    ("livestock_benefits", "Cattle in December", "purchase"),
    ("livestock_benefits", "Sheep in December", "purchase"),
    ("livestock_benefits", "Goat in December", "goat_purchase"),
]


def upgrade() -> None:
    bind = op.get_bind()
    scheme_enum = sa.Enum(*_SCHEME_VALUES, name="schemetype")

    # On Postgres the ENUM type must exist before the column.
    if bind.dialect.name == "postgresql":
        scheme_enum.create(bind, checkfirst=True)

    # 1. Add the column as nullable so we can backfill before constraining it.
    with op.batch_alter_table("cover_plans", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scheme_type", scheme_enum, nullable=True))

    # 2. Backfill existing rows.
    for category, cover_type, scheme_type in _BACKFILL:
        if cover_type is None:
            op.execute(
                sa.text(
                    "UPDATE cover_plans SET scheme_type = :st WHERE category = :cat"
                ).bindparams(st=scheme_type, cat=category)
            )
        else:
            op.execute(
                sa.text(
                    "UPDATE cover_plans SET scheme_type = :st "
                    "WHERE category = :cat AND cover_type = :ct"
                ).bindparams(st=scheme_type, cat=category, ct=cover_type)
            )

    # 3. Make it NOT NULL + indexed.
    with op.batch_alter_table("cover_plans", schema=None) as batch_op:
        batch_op.alter_column("scheme_type", existing_type=scheme_enum, nullable=False)
        batch_op.create_index("ix_cover_plans_scheme_type", ["scheme_type"])


def downgrade() -> None:
    with op.batch_alter_table("cover_plans", schema=None) as batch_op:
        batch_op.drop_index("ix_cover_plans_scheme_type")
        batch_op.drop_column("scheme_type")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="schemetype").drop(bind, checkfirst=True)
```

Leave `revision: str = ...` and `down_revision: Union[str, None] = ...` as whatever alembic auto-generated. Don't manually edit those.

- [ ] **Step 5: Run the alembic suite**

Run: `pytest tests/test_alembic.py -v`

Expected: **PASS**. All three tests green — `test_upgrade_head_creates_all_tables`, `test_downgrade_base_removes_app_tables`, `test_metadata_matches_migration`.

If `test_metadata_matches_migration` still flags a diff, the most likely cause is the `name="schemetype"` on the Enum not matching the model's default (SQLAlchemy auto-derives from the enum class name → lowercase `schemetype`). Confirm both use the exact same `name=`.

- [ ] **Step 6: Verify backfill on a real seeded DB**

Run a one-shot integration check:

```bash
pytest tests/test_cover_seed.py tests/test_alembic.py -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/ tests/test_alembic.py
git commit -m "Add Alembic migration for CoverPlan.scheme_type" -m "Creates SchemeType enum on Postgres, adds nullable scheme_type column to cover_plans, backfills existing 13 seeded rows per the design spec mapping, then marks the column NOT NULL and indexed. cover_plans added to the alembic expected-tables set.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Extend `GET /customers` and `GET /cover-plans` with `?scheme_type=` filter

**Files:**
- Modify: `app/api/customers.py`
- Modify: `app/api/cover.py`
- Modify: `tests/test_customers.py` (extend)
- Modify or create: `tests/test_cover_plans.py`

- [ ] **Step 1: Write failing tests for the customers filter**

Append to `tests/test_customers.py` (use the existing fixture pattern in that file — TestClient + DB session). Add these tests:

```python
def test_list_customers_filtered_by_scheme_type(client, admin_token, db, _seed_plans):
    """A customer with a funeral policy appears under ?scheme_type=funeral,
    not under ?scheme_type=purchase."""
    from app.models.cover_plan import CoverPlan, SchemeType
    from app.models.customer import Customer, CustomerStatus
    from app.models.policy import Policy, PolicyStatus, PolicyType
    from decimal import Decimal
    from datetime import date

    fcust = Customer(full_name="Funeral Holder", id_number="9001011234567",
                     status=CustomerStatus.active)
    pcust = Customer(full_name="Purchase Holder", id_number="9002021234567",
                     status=CustomerStatus.active)
    db.add_all([fcust, pcust]); db.flush()

    funeral_plan = db.query(CoverPlan).filter(
        CoverPlan.scheme_type == SchemeType.funeral
    ).first()
    purchase_plan = db.query(CoverPlan).filter(
        CoverPlan.scheme_type == SchemeType.purchase
    ).first()

    db.add(Policy(customer_id=fcust.id, policy_type=PolicyType.individual,
                  premium_amount=funeral_plan.monthly_premium,
                  start_date=date(2026, 1, 1), status=PolicyStatus.active,
                  cover_plan_id=funeral_plan.id))
    db.add(Policy(customer_id=pcust.id, policy_type=PolicyType.individual,
                  premium_amount=purchase_plan.monthly_premium,
                  start_date=date(2026, 1, 1), status=PolicyStatus.active,
                  cover_plan_id=purchase_plan.id))
    db.commit()

    r = client.get("/customers?scheme_type=funeral",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    names = [c["full_name"] for c in r.json()]
    assert "Funeral Holder" in names
    assert "Purchase Holder" not in names


def test_list_customers_empty_scheme_returns_empty(client, admin_token, _seed_plans):
    r = client.get("/customers?scheme_type=stokvel",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_customers_unknown_scheme_422(client, admin_token):
    r = client.get("/customers?scheme_type=not_a_real_scheme",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 422
```

If `_seed_plans` or `admin_token` fixtures don't already exist, look at the top of `tests/test_customers.py` for the patterns used; reuse the existing fixtures. If `_seed_plans` doesn't exist, add at module scope:

```python
@pytest.fixture
def _seed_plans(db):
    from app.services.cover_seed import seed_cover_plans
    seed_cover_plans(db)
```

- [ ] **Step 2: Write failing tests for the plans filter**

Create `tests/test_cover_plans.py` (or append to an existing equivalent — `tests/test_cover_signup.py` is the closest sibling; either is fine):

```python
"""Tests for GET /cover-plans (catalog)."""
from fastapi.testclient import TestClient

from app.services.cover_seed import seed_cover_plans


def test_cover_plans_filter_by_scheme_type(client, db):
    seed_cover_plans(db)

    r = client.get("/cover-plans?scheme_type=goat_purchase")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["cover_type"] == "Goat in December"
    assert body[0]["scheme_type"] == "goat_purchase"


def test_cover_plans_unknown_scheme_422(client):
    r = client.get("/cover-plans?scheme_type=does_not_exist")
    assert r.status_code == 422
```

- [ ] **Step 3: Run both test files; confirm they fail**

Run: `pytest tests/test_customers.py tests/test_cover_plans.py -v -k scheme_type`

Expected: **FAIL**. Either with 422 on the *correct* requests (because Pydantic doesn't yet know `scheme_type`), or because the filter isn't applied. Could also be 200 with wrong row counts.

- [ ] **Step 4: Add the filter to `GET /customers`**

Edit `app/api/customers.py`. Update the imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
...
from app.models.cover_plan import CoverPlan, SchemeType
from app.models.policy import Policy, PolicyStatus
```

Replace `list_customers` with:

```python
@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = Query(100, le=500),
    scheme_type: SchemeType | None = Query(None),
) -> list[Customer]:
    q = db.query(Customer)
    if scheme_type is not None:
        q = (
            q.join(Policy, Policy.customer_id == Customer.id)
             .join(CoverPlan, Policy.cover_plan_id == CoverPlan.id)
             .filter(CoverPlan.scheme_type == scheme_type)
             .distinct()
        )
    return q.offset(skip).limit(limit).all()
```

- [ ] **Step 5: Add the filter to `GET /cover-plans`**

Edit `app/api/cover.py`. Update imports:

```python
from app.models.cover_plan import CoverCategory, CoverPlan, SchemeType
```

Replace `list_cover_plans` with:

```python
@router.get("/cover-plans", response_model=List[CoverPlanOut])
def list_cover_plans(
    category: CoverCategory | None = Query(None, description="Filter to one category"),
    scheme_type: SchemeType | None = Query(None, description="Filter to one scheme tab"),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
) -> List[CoverPlan]:
    q = db.query(CoverPlan)
    if category is not None:
        q = q.filter(CoverPlan.category == category)
    if scheme_type is not None:
        q = q.filter(CoverPlan.scheme_type == scheme_type)
    if not include_inactive:
        q = q.filter(CoverPlan.is_active.is_(True))
    return q.order_by(CoverPlan.category, CoverPlan.monthly_premium).all()
```

- [ ] **Step 6: Run the filter tests; confirm they pass**

Run: `pytest tests/test_customers.py tests/test_cover_plans.py -v -k scheme_type`

Expected: **PASS** for all the new tests. Existing tests in those files unchanged → still green.

- [ ] **Step 7: Commit**

```bash
git add app/api/customers.py app/api/cover.py tests/test_customers.py tests/test_cover_plans.py
git commit -m "Add ?scheme_type= filter on /customers and /cover-plans" -m "GET /customers grows a join through Policy + CoverPlan to filter customers by their policies' scheme. GET /cover-plans gains a third optional filter alongside ?category= and ?include_inactive=. Unknown enum values return 422 via existing Pydantic validation.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Add `GET /policies` list endpoint with `?customer_id=` and `?scheme_type=` filters

The codebase currently has **no policies list endpoint** — only `GET /policies/{id}`. We need a list for the Policies sub-tab on each scheme page.

**Files:**
- Modify: `app/api/policies.py`
- Modify: `tests/test_policies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_policies.py` (reuse existing fixtures — find the customer/policy factory pattern at the top of that file):

```python
def test_list_policies_filtered_by_scheme_type(client, admin_token, db, _seed_plans):
    from app.models.cover_plan import CoverPlan, SchemeType
    from app.models.customer import Customer, CustomerStatus
    from app.models.policy import Policy, PolicyStatus, PolicyType
    from datetime import date

    cust = Customer(full_name="Holder", id_number="9101011234567",
                    status=CustomerStatus.active)
    db.add(cust); db.flush()

    fplan = db.query(CoverPlan).filter(
        CoverPlan.scheme_type == SchemeType.funeral
    ).first()
    pplan = db.query(CoverPlan).filter(
        CoverPlan.scheme_type == SchemeType.purchase
    ).first()
    db.add_all([
        Policy(customer_id=cust.id, policy_type=PolicyType.individual,
               premium_amount=fplan.monthly_premium, start_date=date(2026, 1, 1),
               status=PolicyStatus.active, cover_plan_id=fplan.id),
        Policy(customer_id=cust.id, policy_type=PolicyType.individual,
               premium_amount=pplan.monthly_premium, start_date=date(2026, 1, 1),
               status=PolicyStatus.active, cover_plan_id=pplan.id),
    ])
    db.commit()

    r = client.get("/policies?scheme_type=funeral",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["cover_plan_id"] == fplan.id


def test_list_policies_filtered_by_customer_id(client, admin_token, db, _seed_plans):
    from app.models.cover_plan import CoverPlan, SchemeType
    from app.models.customer import Customer, CustomerStatus
    from app.models.policy import Policy, PolicyStatus, PolicyType
    from datetime import date

    a = Customer(full_name="A", id_number="9201011234567", status=CustomerStatus.active)
    b = Customer(full_name="B", id_number="9202021234567", status=CustomerStatus.active)
    db.add_all([a, b]); db.flush()
    plan = db.query(CoverPlan).filter(
        CoverPlan.scheme_type == SchemeType.funeral
    ).first()
    db.add(Policy(customer_id=a.id, policy_type=PolicyType.individual,
                  premium_amount=plan.monthly_premium, start_date=date(2026, 1, 1),
                  status=PolicyStatus.active, cover_plan_id=plan.id))
    db.commit()

    r = client.get(f"/policies?customer_id={a.id}",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get(f"/policies?customer_id={b.id}",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Run; confirm 404 (no list endpoint exists)**

Run: `pytest tests/test_policies.py -v -k list_policies`

Expected: **FAIL** with 404 (FastAPI returns "Method Not Allowed" or 404 — accept either, the point is the endpoint doesn't exist).

- [ ] **Step 3: Add the list endpoint**

Edit `app/api/policies.py`. Update imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
...
from app.models.cover_plan import CoverPlan, SchemeType
```

Add a list endpoint **above** `get_policy` (route order matters; `/{policy_id}` must come last):

```python
@router.get("", response_model=list[PolicyOut])
def list_policies(
    customer_id: int | None = Query(None, description="Filter to one customer"),
    scheme_type: SchemeType | None = Query(None, description="Filter to one scheme tab"),
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Policy]:
    q = db.query(Policy)
    if customer_id is not None:
        q = q.filter(Policy.customer_id == customer_id)
    if scheme_type is not None:
        q = q.join(CoverPlan, Policy.cover_plan_id == CoverPlan.id) \
             .filter(CoverPlan.scheme_type == scheme_type)
    return q.order_by(Policy.id).offset(skip).limit(limit).all()
```

- [ ] **Step 4: Run; confirm both tests pass**

Run: `pytest tests/test_policies.py -v -k list_policies`

Expected: **PASS**. 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/api/policies.py tests/test_policies.py
git commit -m "Add GET /policies list endpoint with customer_id + scheme_type filters" -m "No list endpoint existed before — only /policies/{id}. This adds GET /policies with two optional filters (?customer_id, ?scheme_type) to support the per-scheme Policies sub-tab. Auth-required via get_current_user.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: New `GET /schemes/{scheme_type}/overview` endpoint

**Files:**
- Create: `app/api/schemes.py`
- Create: `app/schemas/scheme.py`
- Modify: `app/main.py`
- Create: `tests/test_schemes_overview.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schemes_overview.py`:

```python
"""Tests for GET /schemes/{scheme_type}/overview."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.cover_plan import CoverPlan, SchemeType
from app.models.customer import Customer, CustomerStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy, PolicyStatus, PolicyType
from app.services.cover_seed import seed_cover_plans


@pytest.fixture
def _seed(db):
    seed_cover_plans(db)


def test_overview_requires_auth(client, _seed):
    r = client.get("/schemes/funeral/overview")
    assert r.status_code == 401


def test_overview_empty_scheme_returns_zeros(client, admin_token, _seed):
    r = client.get("/schemes/stokvel/overview",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["scheme_type"] == "stokvel"
    assert body["active_customers"] == 0
    assert body["active_policies"] == 0
    assert body["lapsed_customers"] == 0
    assert body["plan_count"] == 0
    assert body["revenue_this_month"] == "0.00"


def test_overview_funeral_counts_with_data(client, admin_token, db, _seed):
    plan = db.query(CoverPlan).filter(
        CoverPlan.scheme_type == SchemeType.funeral
    ).first()
    cust = Customer(full_name="A", id_number="9301011234567",
                    status=CustomerStatus.active)
    db.add(cust); db.flush()
    db.add(Policy(customer_id=cust.id, policy_type=PolicyType.individual,
                  premium_amount=plan.monthly_premium,
                  start_date=date(2026, 1, 1),
                  status=PolicyStatus.active, cover_plan_id=plan.id))
    db.commit()

    r = client.get("/schemes/funeral/overview",
                   headers={"Authorization": f"Bearer {admin_token}"})
    body = r.json()
    assert r.status_code == 200
    assert body["scheme_type"] == "funeral"
    assert body["active_customers"] == 1
    assert body["active_policies"] == 1
    assert body["plan_count"] >= 9   # at least the 9 funeral plans we seed


def test_overview_unknown_scheme_returns_422(client, admin_token, _seed):
    r = client.get("/schemes/not_a_scheme/overview",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run; confirm all four fail with 404**

Run: `pytest tests/test_schemes_overview.py -v`

Expected: **FAIL**. Endpoint doesn't exist.

- [ ] **Step 3: Create the response schema**

Create `app/schemas/scheme.py`:

```python
"""Pydantic schemas for the /schemes endpoints."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

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
```

- [ ] **Step 4: Create the schemes router**

Create `app/api/schemes.py`:

```python
"""Scheme-scoped overview endpoint.

`GET /schemes/{scheme_type}/overview` mirrors the global /dashboard
shape but filters by `cover_plan.scheme_type`. Pure read; reuses the
billing helpers; no side effects.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.cover_plan import CoverPlan, SchemeType
from app.models.customer import Customer, CustomerStatus
from app.models.payment import Payment, PaymentStatus
from app.models.policy import Policy, PolicyStatus
from app.models.user import User
from app.schemas.scheme import SchemeOverviewResponse, scheme_label
from app.services import billing


router = APIRouter(prefix="/schemes", tags=["schemes"])


@router.get("/{scheme_type}/overview", response_model=SchemeOverviewResponse)
def scheme_overview(
    scheme_type: SchemeType,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SchemeOverviewResponse:
    today = date.today()
    month_start = billing.first_of_month(today)

    policies_in_scheme = (
        db.query(Policy)
          .join(CoverPlan, Policy.cover_plan_id == CoverPlan.id)
          .filter(CoverPlan.scheme_type == scheme_type)
    )

    active_policies = policies_in_scheme.filter(
        Policy.status == PolicyStatus.active
    ).count()
    lapsed_policies = policies_in_scheme.filter(
        Policy.status == PolicyStatus.lapsed
    ).count()

    customer_ids = [cid for (cid,) in policies_in_scheme.with_entities(
        Policy.customer_id
    ).distinct()]
    if customer_ids:
        active_customers = db.query(func.count(Customer.id)).filter(
            Customer.id.in_(customer_ids),
            Customer.status == CustomerStatus.active,
        ).scalar() or 0
        lapsed_customers = db.query(func.count(Customer.id)).filter(
            Customer.id.in_(customer_ids),
            Customer.status == CustomerStatus.lapsed,
        ).scalar() or 0
    else:
        active_customers = 0
        lapsed_customers = 0

    plan_count = db.query(func.count(CoverPlan.id)).filter(
        CoverPlan.scheme_type == scheme_type,
        CoverPlan.is_active.is_(True),
    ).scalar() or 0

    # Per-policy month classification (mirrors /dashboard).
    paid = unpaid = overdue = 0
    expected_total = Decimal("0")
    for policy in policies_in_scheme.filter(Policy.status == PolicyStatus.active).all():
        expected_total += Decimal(policy.premium_amount)
        payments = db.query(Payment).filter(Payment.policy_id == policy.id).all()
        label = billing.get_payment_status_for_month(policy, payments, month_start, as_of=today)
        if label == billing.STATUS_PAID:
            paid += 1
        elif label == billing.STATUS_OVERDUE:
            overdue += 1
        else:
            unpaid += 1

    # Revenue this month (only Payments tied to in-scheme policies).
    revenue = Decimal("0")
    if customer_ids:
        rev_scalar = (
            db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
              .join(Policy, Payment.policy_id == Policy.id)
              .join(CoverPlan, Policy.cover_plan_id == CoverPlan.id)
              .filter(
                  CoverPlan.scheme_type == scheme_type,
                  Payment.status == PaymentStatus.paid,
                  Payment.payment_date >= month_start,
              )
              .scalar()
        )
        revenue = Decimal(rev_scalar or 0)

    return SchemeOverviewResponse(
        scheme_type=scheme_type,
        label=scheme_label(scheme_type),
        active_customers=active_customers,
        lapsed_customers=lapsed_customers,
        active_policies=active_policies,
        lapsed_policies=lapsed_policies,
        paid_this_month=paid,
        unpaid_this_month=unpaid,
        overdue_this_month=overdue,
        revenue_this_month=revenue,
        expected_revenue_this_month=expected_total,
        plan_count=plan_count,
    )
```

- [ ] **Step 5: Wire the router into the app**

Edit `app/main.py`. Update the import line that brings in routers:

```python
from app.api import (
    admin, auth, cover, customers, dashboard, field, field_admin,
    members, payments, policies, schemes,
)
```

Then find where the other routers are `app.include_router(...)`'d and add:

```python
app.include_router(schemes.router)
```

Position the new include alongside the other domain routers (after `policies.router`).

- [ ] **Step 6: Run the tests; confirm all four pass**

Run: `pytest tests/test_schemes_overview.py -v`

Expected: **PASS**. 4 passed.

- [ ] **Step 7: Commit**

```bash
git add app/api/schemes.py app/schemas/scheme.py app/main.py tests/test_schemes_overview.py
git commit -m "Add GET /schemes/{scheme_type}/overview endpoint" -m "Returns scheme-scoped counts and revenue mirroring the global /dashboard shape. Empty schemes (e.g., stokvel) return zeros without error. Reuses billing.get_payment_status_for_month — no new pure logic introduced.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Frontend — types and sidebar group

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Extend the types module**

Edit `frontend/src/types.ts`. Append:

```typescript
// Mirrors app/models/cover_plan.py SchemeType
export type SchemeType =
  | "funeral"
  | "stokvel"
  | "purchase"
  | "goat_purchase"
  | "wedding"
  | "party"
  | "breeding"
  | "farming";

export interface SchemeManifestEntry {
  type: SchemeType;
  label: string;
  status: "active" | "coming_soon";
}

// Single source of truth for the sidebar and routing.
export const SCHEME_MANIFEST: readonly SchemeManifestEntry[] = [
  { type: "funeral",       label: "Funeral",       status: "active" },
  { type: "stokvel",       label: "Stokvel",       status: "active" },
  { type: "purchase",      label: "Purchase",      status: "active" },
  { type: "goat_purchase", label: "Goat purchase", status: "active" },
  { type: "wedding",       label: "Wedding",       status: "coming_soon" },
  { type: "party",         label: "Party",         status: "coming_soon" },
  { type: "breeding",      label: "Breeding",      status: "coming_soon" },
  { type: "farming",       label: "Farming",       status: "coming_soon" },
] as const;

export interface SchemeOverviewResponse {
  scheme_type: SchemeType;
  label: string;
  active_customers: number;
  lapsed_customers: number;
  active_policies: number;
  lapsed_policies: number;
  paid_this_month: number;
  unpaid_this_month: number;
  overdue_this_month: number;
  revenue_this_month: string;
  expected_revenue_this_month: string;
  plan_count: number;
}
```

Also extend the `CoverPlan` type if it exists (search for `interface CoverPlan` — it may live in this file or elsewhere). If `CoverPlan` is defined here, add `scheme_type: SchemeType` to it. If it's not defined yet but used as `any` elsewhere, leave it for the Plans-tab task.

- [ ] **Step 2: Update the sidebar**

Edit `frontend/src/components/Layout.tsx`. Update the icon import line:

```typescript
import {
  LayoutDashboard, Users, Bell, FileText, Wallet, Smartphone,
  TabletSmartphone, Layers,
} from "lucide-react";
```

Add the `SCHEME_MANIFEST` import:

```typescript
import { SCHEME_MANIFEST } from "../types";
```

Inside the `<nav>` block, after the existing `/notifications` NavLink (or between Customers and Record payment — wherever fits the design spec § 6.1 order), insert the Schemes group. Replace the existing `<nav>...</nav>` content with:

```tsx
        <nav className="flex-1 px-3 py-4 space-y-1">
          <NavLink to="/" end className={linkCls}>
            <LayoutDashboard size={18} /> Dashboard
          </NavLink>
          <NavLink to="/customers" className={linkCls}>
            <Users size={18} /> Customers
          </NavLink>

          <div className="pt-3 pb-1 px-3 text-[10px] uppercase tracking-wider text-slate-500">
            Schemes
          </div>
          {SCHEME_MANIFEST.filter((s) => s.status === "active").map((s) => (
            <NavLink key={s.type} to={`/schemes/${s.type}`} className={linkCls}>
              <Layers size={18} /> {s.label}
            </NavLink>
          ))}
          <div className="my-1 border-t border-slate-800" />
          {SCHEME_MANIFEST.filter((s) => s.status === "coming_soon").map((s) => (
            <NavLink
              key={s.type}
              to={`/schemes/${s.type}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition ${
                  isActive
                    ? "bg-slate-800 text-slate-300"
                    : "text-slate-500 hover:bg-slate-800/60"
                }`
              }
            >
              <Layers size={18} /> {s.label}
              <span className="ml-auto text-[10px] uppercase tracking-wider text-slate-600">
                soon
              </span>
            </NavLink>
          ))}

          <div className="pt-3" />
          <NavLink to="/payments/new" className={linkCls}>
            <Wallet size={18} /> Record payment
          </NavLink>
          <NavLink to="/notifications" className={linkCls}>
            <Bell size={18} /> Notifications
          </NavLink>
          <NavLink to="/audit" className={linkCls}>
            <FileText size={18} /> Audit log
          </NavLink>
          <NavLink to="/field" className={linkCls}>
            <TabletSmartphone size={18} /> Field app
          </NavLink>
          {canAdmin && (
            <NavLink to="/devices" className={linkCls}>
              <Smartphone size={18} /> Field devices
            </NavLink>
          )}
        </nav>
```

- [ ] **Step 3: Build the frontend**

Run from `frontend/`:

```bash
npm run lint && npm run build
```

Expected: PASS. The routes don't exist yet so clicking a sidebar entry will redirect to `/` (the catch-all `<Route path="*" element={<Navigate to="/" replace />} />` in `App.tsx`) — that's fine for this task. Next task wires the routes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/components/Layout.tsx
git commit -m "Add Schemes sidebar group with active + Coming Soon entries" -m "Eight new sidebar links driven by SCHEME_MANIFEST in types.ts: four active (Funeral, Stokvel, Purchase, Goat purchase) and four muted Coming Soon entries (Wedding, Party, Breeding, Farming). Routes wired in the next task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Frontend — routing, SchemePage shell, ComingSoonScheme

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/SchemePage.tsx`
- Create: `frontend/src/pages/scheme/ComingSoonScheme.tsx`

- [ ] **Step 1: Create the Coming-Soon placeholder**

Create `frontend/src/pages/scheme/ComingSoonScheme.tsx`:

```tsx
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

interface Props { label: string; }

export function ComingSoonScheme({ label }: Props) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-slate-500 hover:text-slate-700">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">{label}</h1>
        <span className="text-[10px] uppercase tracking-wider text-slate-500 px-2 py-1 rounded bg-slate-100">
          Coming soon
        </span>
      </div>
      <div className="card p-8 text-slate-600">
        This scheme is not yet active. Check back soon.
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create the SchemePage shell**

Create `frontend/src/pages/SchemePage.tsx`:

```tsx
import { useParams, Navigate, NavLink, Outlet } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { SCHEME_MANIFEST, SchemeType } from "../types";
import { ComingSoonScheme } from "./scheme/ComingSoonScheme";


const SUB_TABS: { to: string; label: string }[] = [
  { to: "",          label: "Overview" },
  { to: "customers", label: "Customers" },
  { to: "policies",  label: "Policies" },
  { to: "plans",     label: "Plans" },
];


export function SchemePage() {
  const { schemeType } = useParams<{ schemeType: string }>();
  const entry = SCHEME_MANIFEST.find((s) => s.type === schemeType);

  if (!entry) {
    return <Navigate to="/" replace />;
  }
  if (entry.status === "coming_soon") {
    return <ComingSoonScheme label={entry.label} />;
  }

  const scheme = entry.type as SchemeType;
  const tabCls = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 text-sm font-medium border-b-2 transition ${
      isActive
        ? "border-brand-600 text-brand-700"
        : "border-transparent text-slate-500 hover:text-slate-700"
    }`;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-slate-500 hover:text-slate-700">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">{entry.label}</h1>
      </div>
      <div className="border-b border-slate-200 flex gap-2">
        {SUB_TABS.map((t) => (
          <NavLink
            key={t.to || "overview"}
            to={t.to ? `/schemes/${scheme}/${t.to}` : `/schemes/${scheme}`}
            end={t.to === ""}
            className={tabCls}
          >
            {t.label}
          </NavLink>
        ))}
      </div>
      <Outlet context={{ scheme }} />
    </div>
  );
}
```

- [ ] **Step 3: Wire the routes**

Edit `frontend/src/App.tsx`. Update imports:

```typescript
import { SchemePage } from "./pages/SchemePage";
```

(Other sub-tab imports added in Task 8.)

Add a placeholder index element for now — the Overview tab is built in Task 8. Inside the protected `<Route element={<ProtectedRoute>...}>` block, add **before** the catch-all redirect:

```tsx
              <Route path="schemes/:schemeType" element={<SchemePage />}>
                <Route index element={<div className="text-slate-500">Overview coming next.</div>} />
                <Route path="customers" element={<div className="text-slate-500">Customers tab coming next.</div>} />
                <Route path="policies" element={<div className="text-slate-500">Policies tab coming next.</div>} />
                <Route path="plans" element={<div className="text-slate-500">Plans tab coming next.</div>} />
              </Route>
```

- [ ] **Step 4: Build the frontend**

Run from `frontend/`:

```bash
npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 5: Smoke-check in the browser (optional but recommended)**

Start the backend (`uvicorn app.main:app`) and frontend dev server (`npm run dev`). Visit:

- `/schemes/funeral` → page header "Funeral", four sub-tabs visible, all show placeholder text. URLs work for each sub-tab.
- `/schemes/wedding` → ComingSoonScheme renders ("This scheme is not yet active. …").
- `/schemes/bogus` → redirects to `/` (no crash).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/SchemePage.tsx frontend/src/pages/scheme/ComingSoonScheme.tsx
git commit -m "Add SchemePage shell and ComingSoonScheme placeholder + routes" -m "/schemes/:schemeType resolves to either the SchemePage (4 sub-tab routes) for active schemes or the ComingSoonScheme placeholder for muted ones. Sub-tab content is stubbed; wired in the next task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Frontend — sub-tab components (Overview, Customers, Policies, Plans)

Four small components. Each fetches via React Query and renders the data. Bundle them in one task and one commit because each is ~30 lines and they share the same shape.

**Files:**
- Create: `frontend/src/pages/scheme/OverviewTab.tsx`
- Create: `frontend/src/pages/scheme/CustomersTab.tsx`
- Create: `frontend/src/pages/scheme/PoliciesTab.tsx`
- Create: `frontend/src/pages/scheme/PlansTab.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Look up the existing API client shape**

Open `frontend/src/api/client.ts` (or wherever `api.get<T>(...)` is defined). Confirm the signature so the new tabs use it correctly. If the existing client uses a different idiom (raw fetch, etc.), match it.

- [ ] **Step 2: Create the Overview tab**

Create `frontend/src/pages/scheme/OverviewTab.tsx`:

```tsx
import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { SchemeOverviewResponse, SchemeType } from "../../types";
import { formatMoney } from "../../utils";


function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-5">
      <div className="text-xs uppercase text-slate-500 font-semibold mb-2">{title}</div>
      {children}
    </div>
  );
}


export function OverviewTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-overview", scheme],
    queryFn: () => api.get<SchemeOverviewResponse>(`/schemes/${scheme}/overview`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load overview.</div>;
  const d = q.data!;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Customers">
          <div className="text-3xl font-semibold">{d.active_customers}</div>
          <div className="text-xs text-slate-500 mt-1">{d.lapsed_customers} lapsed</div>
        </Card>
        <Card title="Policies">
          <div className="text-3xl font-semibold">{d.active_policies}</div>
          <div className="text-xs text-slate-500 mt-1">{d.lapsed_policies} lapsed</div>
        </Card>
        <Card title="This month">
          <div className="flex gap-3 text-sm">
            <span className="text-emerald-600">{d.paid_this_month} paid</span>
            <span className="text-amber-600">{d.unpaid_this_month} unpaid</span>
            <span className="text-rose-600">{d.overdue_this_month} overdue</span>
          </div>
        </Card>
        <Card title="Revenue this month">
          <div className="text-2xl font-semibold">{formatMoney(d.revenue_this_month)}</div>
          <div className="text-xs text-slate-500 mt-1">
            of {formatMoney(d.expected_revenue_this_month)} expected
          </div>
        </Card>
      </div>
      <div className="card p-4 text-sm text-slate-600">
        {d.plan_count === 0
          ? "0 plans configured — add one to begin."
          : `${d.plan_count} plan${d.plan_count === 1 ? "" : "s"} in this scheme.`}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create the Customers tab**

Create `frontend/src/pages/scheme/CustomersTab.tsx`:

```tsx
import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Customer, SchemeType } from "../../types";
import { StatusBadge } from "../../components/StatusBadge";


export function CustomersTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-customers", scheme],
    queryFn: () => api.get<Customer[]>(`/customers?scheme_type=${scheme}`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load customers.</div>;
  const rows = q.data!;
  if (rows.length === 0) {
    return <div className="card p-6 text-slate-500">No customers yet.</div>;
  }

  return (
    <div className="card divide-y">
      {rows.map((c) => (
        <Link
          key={c.id}
          to={`/customers/${c.id}`}
          className="flex items-center justify-between p-4 hover:bg-slate-50"
        >
          <div>
            <div className="font-medium text-slate-800">{c.full_name}</div>
            <div className="text-xs text-slate-500">{c.id_number}</div>
          </div>
          <StatusBadge status={c.status} />
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Create the Policies tab**

Create `frontend/src/pages/scheme/PoliciesTab.tsx`:

```tsx
import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Policy, SchemeType } from "../../types";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate, formatMoney } from "../../utils";


export function PoliciesTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-policies", scheme],
    queryFn: () => api.get<Policy[]>(`/policies?scheme_type=${scheme}`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load policies.</div>;
  const rows = q.data!;
  if (rows.length === 0) {
    return <div className="card p-6 text-slate-500">No policies yet.</div>;
  }

  return (
    <div className="card divide-y">
      {rows.map((p) => (
        <div key={p.id} className="flex items-center justify-between p-4">
          <div>
            <div className="font-medium text-slate-800">Policy #{p.id}</div>
            <div className="text-xs text-slate-500">
              Customer {p.customer_id} · started {formatDate(p.start_date)}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-sm text-slate-700">
              {formatMoney(p.premium_amount)} / mo
            </div>
            <StatusBadge status={p.status} />
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create the Plans tab**

Create `frontend/src/pages/scheme/PlansTab.tsx`:

```tsx
import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { SchemeType } from "../../types";
import { formatMoney } from "../../utils";


interface CoverPlan {
  id: number;
  category: string;
  cover_type: string;
  scheme_type: SchemeType;
  monthly_premium: string;
  max_dependents: number;
  description: string | null;
  is_active: boolean;
}


export function PlansTab() {
  const { scheme } = useOutletContext<{ scheme: SchemeType }>();
  const q = useQuery({
    queryKey: ["scheme-plans", scheme],
    queryFn: () => api.get<CoverPlan[]>(`/cover-plans?scheme_type=${scheme}`),
  });

  if (q.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (q.error) return <div className="text-red-600">Failed to load plans.</div>;
  const rows = q.data!;
  if (rows.length === 0) {
    return <div className="card p-6 text-slate-500">No plans configured for this scheme yet.</div>;
  }

  return (
    <div className="card divide-y">
      {rows.map((p) => (
        <div key={p.id} className="p-4">
          <div className="flex items-center justify-between">
            <div className="font-medium text-slate-800">{p.cover_type}</div>
            <div className="text-sm text-slate-700">{formatMoney(p.monthly_premium)} / mo</div>
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {p.description}
            {p.max_dependents > 0 && ` · up to ${p.max_dependents} dependents`}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Wire the sub-tabs into `App.tsx`**

Edit `frontend/src/App.tsx`. Update imports:

```typescript
import { SchemePage } from "./pages/SchemePage";
import { OverviewTab } from "./pages/scheme/OverviewTab";
import { CustomersTab } from "./pages/scheme/CustomersTab";
import { PoliciesTab } from "./pages/scheme/PoliciesTab";
import { PlansTab } from "./pages/scheme/PlansTab";
```

Replace the placeholder block from Task 7 step 3 with:

```tsx
              <Route path="schemes/:schemeType" element={<SchemePage />}>
                <Route index element={<OverviewTab />} />
                <Route path="customers" element={<CustomersTab />} />
                <Route path="policies" element={<PoliciesTab />} />
                <Route path="plans" element={<PlansTab />} />
              </Route>
```

- [ ] **Step 7: Build the frontend**

```bash
cd frontend && npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 8: Smoke-check (optional)**

Visit `/schemes/funeral` → Overview shows the four cards with real numbers. Click each sub-tab → respective list renders. Visit `/schemes/stokvel` → Overview shows zeros; Customers/Policies/Plans say "No … yet."

- [ ] **Step 9: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/scheme/
git commit -m "Wire scheme sub-tab content (Overview / Customers / Policies / Plans)" -m "Each sub-tab is a thin React Query component that calls one backend endpoint and renders a list or card grid. Empty Stokvel scheme renders consistent zero states.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Playwright happy-path test

**Files:**
- Create: `tests/test_playwright_scheme_tabs.py`

- [ ] **Step 1: Look up the existing Playwright fixture pattern**

Open `tests/test_playwright_ui.py` and note how it sets up the page (login fixture, base URL, page object). Mirror that pattern.

- [ ] **Step 2: Write the happy-path test**

Create `tests/test_playwright_scheme_tabs.py`. Use the same fixtures (`page`, `live_app`, `seed_user`, or whichever names are in `test_playwright_ui.py`):

```python
"""Happy-path UI test for the scheme tabs (single linear flow)."""
import pytest


def test_scheme_tabs_navigate_and_render(page, live_app):
    # Adjust to match the project's login pattern in test_playwright_ui.py.
    page.goto(f"{live_app}/login")
    # … existing login steps (reuse the helper from test_playwright_ui.py) …

    # 1. Funeral (active scheme with seeded data).
    page.get_by_role("link", name="Funeral").click()
    page.wait_for_url("**/schemes/funeral")
    assert page.locator("h1", has_text="Funeral").is_visible()

    # 2. Sub-tabs render.
    for tab in ("Customers", "Policies", "Plans"):
        page.get_by_role("link", name=tab).click()
        page.wait_for_url(f"**/schemes/funeral/{tab.lower()}")
        # Either a list row or the empty-state card; both are acceptable.
        assert (
            page.locator(".card").first.is_visible()
            or page.locator("text=No").first.is_visible()
        )

    # 3. Coming-soon scheme.
    page.get_by_role("link", name="Wedding").click()
    page.wait_for_url("**/schemes/wedding")
    assert page.locator("text=Coming soon").is_visible()
    assert page.locator("text=This scheme is not yet active").is_visible()
```

If `test_playwright_ui.py` uses a different test signature or auth fixture, adapt the imports/fixtures to match. Don't reinvent the auth flow.

- [ ] **Step 3: Run the test**

Run: `pytest tests/test_playwright_scheme_tabs.py -v`

Expected: **PASS** on the first run. If it fails the first time, run twice more; per CLAUDE.md and the spec's flake budget, treat one-out-of-three flake as the existing Playwright instability — NOT as a real failure (but still investigate the selector stability). If it fails 2/3 times, the test or the implementation has a real bug and needs to be fixed (do NOT `xfail`).

- [ ] **Step 4: Commit**

```bash
git add tests/test_playwright_scheme_tabs.py
git commit -m "Add Playwright happy-path test for scheme tabs" -m "One linear flow: log in, navigate to Funeral, exercise the three list sub-tabs, then visit the Wedding coming-soon placeholder. Selectors anchored on visible text and the .card primitive to stay stable.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: Full-suite verification

- [ ] **Step 1: Run the full pytest suite**

Run: `pytest`

Expected: green except for the 5 pre-existing Playwright failures in `tests/test_playwright_ui.py`. The new test from Task 9 should pass.

To make the "what's regression vs pre-existing" question crisp, compare against `fbe28b5` (the commit before any of this branch's work):

```bash
git stash
git checkout fbe28b5 -- .
pytest tests/test_playwright_ui.py 2>&1 | tail -5
git checkout HEAD -- .
```

The 5 failures should appear identically — confirming they're pre-existing.

- [ ] **Step 2: Run frontend gates**

```bash
cd frontend && npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 3: No commit needed**

If everything is green, nothing changed in this task. Plan complete.

If anything new fails, per `CLAUDE.md`:

> Don't add `--no-verify`, skip tests, or mark tests `xfail` to make CI green.

Stop, investigate, fix, and re-run. Do not paper over.

---

## Acceptance criteria (mirrors the spec)

- [ ] `SchemeType` enum exists in `app/models/cover_plan.py` with 8 values.
- [ ] `CoverPlan.scheme_type` column exists, NOT NULL, indexed; existing 13 seeded rows backfilled per the spec mapping.
- [ ] `alembic upgrade head` + `alembic downgrade base` + `test_metadata_matches_migration` all green.
- [ ] `GET /customers?scheme_type=funeral`, `GET /policies?scheme_type=funeral`, `GET /cover-plans?scheme_type=funeral` each return only matching rows; unknown scheme returns 422.
- [ ] `GET /schemes/{scheme_type}/overview` exists, returns the documented shape, requires auth, returns zeros for empty schemes.
- [ ] Sidebar shows 8 scheme links (4 active, 4 "Coming Soon" muted).
- [ ] `/schemes/funeral` renders Overview / Customers / Policies / Plans sub-tabs with real data; `/schemes/stokvel` renders the same shell with empty states; `/schemes/wedding` renders the ComingSoonScheme placeholder.
- [ ] `pytest` (excluding the pre-existing Playwright flakes) is green.
- [ ] `npm run lint` and `npm run build` both pass.
- [ ] No entries added to `requirements.txt` or `package.json`.
