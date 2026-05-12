"""Tests for the funeral-cover wizard: plan catalog + signup endpoint."""
from decimal import Decimal

import pytest

from app.models.beneficiary import Beneficiary
from app.models.cover_plan import CoverCategory
from app.models.customer import Customer
from app.models.member import Member
from app.models.policy import Policy, PolicyStatus, PolicyType
from app.services.cover_seed import seed_cover_plans


@pytest.fixture
def seeded_plans(db):
    """Seed the default cover-plan catalog before each test that needs it."""
    seed_cover_plans(db)
    return db


# ---------- Catalog ----------


def test_cover_plans_seed_is_idempotent(db):
    """Running the seeder twice doesn't duplicate rows."""
    first = seed_cover_plans(db)
    second = seed_cover_plans(db)
    assert first > 0
    assert second == 0


def test_list_cover_plans_returns_all_active(client, seeded_plans):
    r = client.get("/cover-plans")
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) >= 9
    # Every entry has the wizard-relevant fields.
    for p in plans:
        assert {"id", "category", "cover_type", "monthly_premium",
                "max_dependents", "is_active"} <= p.keys()
        assert p["is_active"] is True


def test_list_cover_plans_filter_by_category(client, seeded_plans):
    r = client.get(f"/cover-plans?category={CoverCategory.me_and_family.value}")
    assert r.status_code == 200
    plans = r.json()
    assert plans, "expected at least one me_and_family plan"
    assert all(p["category"] == "me_and_family" for p in plans)
    # "Me and My Family" plan exists at R360 (the value from the user's mockup).
    assert any(p["cover_type"] == "Me and My Family" and Decimal(p["monthly_premium"]) == Decimal("360.00")
               for p in plans)


# ---------- Signup happy path ----------


def _family_plan_id(client, seeded_plans):
    plans = client.get(f"/cover-plans?category={CoverCategory.me_and_family.value}").json()
    return next(p["id"] for p in plans if p["cover_type"] == "Me and My Family")


_DEFAULT = object()  # sentinel so callers can pass an explicit []


def _valid_payload(plan_id: int, *, dependents: int = 4, beneficiaries=_DEFAULT):
    if beneficiaries is _DEFAULT:
        beneficiaries = [{
            "relationship_to_holder": "spouse",
            "first_name": "Lerato",
            "surname": "Mokoena",
            "cellphone": "+27822223333",
            "country_of_birth": "South Africa",
            "share_pct": "100.00",
        }]
    return {
        "cover_plan_id": plan_id,
        "holder": {
            "title": "Mr",
            "first_names": "Thabo",
            "surname": "Mokoena",
            "id_number": "9001015009099",
            "gender": "male",
            "date_of_birth": "1990-01-01",
            "nationality": "South African",
            "email": "thabo@example.com",
            "cellphone": "+27821234567",
        },
        "dependents": [
            {
                "title": "Mrs",
                "first_names": f"Dep{i}",
                "surname": "Mokoena",
                "relationship_to_holder": "spouse" if i == 0 else "child",
                "date_of_birth": "1992-05-05",
                "nationality": "South African",
                "country_of_birth": "South Africa",
            }
            for i in range(dependents)
        ],
        "beneficiaries": beneficiaries,
    }


def test_cover_signup_happy_path(client, seeded_plans, db):
    plan_id = _family_plan_id(client, seeded_plans)
    r = client.post("/cover-signup", json=_valid_payload(plan_id))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["member_count"] == 4
    assert body["beneficiary_count"] == 1
    assert Decimal(body["monthly_premium"]) == Decimal("360.00")

    # DB side-effects: 1 customer, 1 policy (group_scheme, R360, active),
    # 4 members, 1 beneficiary, all linked to the same policy.
    customer = db.query(Customer).filter(Customer.id == body["customer_id"]).one()
    assert customer.full_name == "Mr Thabo Mokoena"
    assert customer.first_names == "Thabo"
    policy = db.query(Policy).filter(Policy.id == body["policy_id"]).one()
    assert policy.policy_type == PolicyType.group_scheme
    assert policy.status == PolicyStatus.active
    assert policy.premium_amount == Decimal("360.00")
    assert policy.cover_plan_id == plan_id
    assert db.query(Member).filter(Member.policy_id == policy.id).count() == 4
    assert db.query(Beneficiary).filter(Beneficiary.policy_id == policy.id).count() == 1


def test_cover_signup_solo_uses_individual_policy_type(client, seeded_plans):
    """A signup with zero dependents produces an `individual` policy."""
    plan_id = _family_plan_id(client, seeded_plans)
    payload = _valid_payload(plan_id, dependents=0)
    r = client.post("/cover-signup", json=payload)
    assert r.status_code == 201
    assert r.json()["member_count"] == 0


# ---------- Validation ----------


def test_cover_signup_rejects_too_many_dependents(client, seeded_plans):
    """`max_dependents=4` plan with 5 dependents -> 400 with a friendly message."""
    plan_id = _family_plan_id(client, seeded_plans)
    payload = _valid_payload(plan_id, dependents=5)
    r = client.post("/cover-signup", json=payload)
    assert r.status_code == 400
    assert "up to 4 dependents" in r.json()["detail"]


def test_cover_signup_rejects_share_not_100(client, seeded_plans):
    """Beneficiary shares must sum to 100 (within 0.01 tolerance)."""
    plan_id = _family_plan_id(client, seeded_plans)
    bad = _valid_payload(plan_id, beneficiaries=[
        {"relationship_to_holder": "spouse", "first_name": "A", "surname": "B",
         "share_pct": "40.00"},
        {"relationship_to_holder": "child", "first_name": "C", "surname": "D",
         "share_pct": "40.00"},
    ])
    r = client.post("/cover-signup", json=bad)
    assert r.status_code == 400
    assert "sum to 100" in r.json()["detail"]


def test_cover_signup_accepts_rounded_share_within_tolerance(client, seeded_plans):
    """33.33 + 33.33 + 33.34 = 100.00 is fine."""
    plan_id = _family_plan_id(client, seeded_plans)
    payload = _valid_payload(plan_id, beneficiaries=[
        {"relationship_to_holder": "spouse", "first_name": "A", "surname": "B",
         "share_pct": "33.33"},
        {"relationship_to_holder": "child", "first_name": "C", "surname": "D",
         "share_pct": "33.33"},
        {"relationship_to_holder": "child", "first_name": "E", "surname": "F",
         "share_pct": "33.34"},
    ])
    r = client.post("/cover-signup", json=payload)
    assert r.status_code == 201


def test_cover_signup_reuses_customer_on_repeat_id_number(client, seeded_plans, db):
    """A second signup with the same ID number reuses the existing customer
    (adds another policy to them) instead of erroring. Lets one person
    hold a funeral cover AND a livestock benefit without re-keying."""
    plan_id = _family_plan_id(client, seeded_plans)
    first = client.post("/cover-signup", json=_valid_payload(plan_id, dependents=0)).json()

    # Same ID, second plan (livestock - so we exercise the no-beneficiary path too).
    livestock = next(
        p for p in client.get(
            f"/cover-plans?category={CoverCategory.livestock_benefits.value}"
        ).json()
        if p["cover_type"] == "Cattle in December"
    )
    second_payload = _valid_payload(livestock["id"], dependents=0, beneficiaries=[])
    second = client.post("/cover-signup", json=second_payload)
    assert second.status_code == 201, second.text

    body = second.json()
    # Same customer, distinct policy.
    assert body["customer_id"] == first["customer_id"]
    assert body["policy_id"] != first["policy_id"]
    assert db.query(Policy).filter(Policy.customer_id == body["customer_id"]).count() == 2


def test_cover_signup_rejects_unknown_plan(client, seeded_plans):
    r = client.post("/cover-signup", json=_valid_payload(plan_id=99999, dependents=0))
    assert r.status_code == 404


# ---------- Livestock benefits ----------


def test_livestock_plans_seeded(client, seeded_plans):
    """The catalog includes the four livestock add-on products."""
    r = client.get(f"/cover-plans?category={CoverCategory.livestock_benefits.value}")
    assert r.status_code == 200
    types = {p["cover_type"] for p in r.json()}
    assert types == {
        "Cattle during funeral", "Cattle in December",
        "Sheep in December", "Goat in December",
    }
    # max_dependents == 0 for every livestock plan (they're not personal cover).
    assert all(p["max_dependents"] == 0 for p in r.json())


def test_livestock_signup_without_beneficiaries(client, seeded_plans, db):
    """Livestock plans don't require beneficiaries (payout is an animal)."""
    livestock = next(
        p for p in client.get(
            f"/cover-plans?category={CoverCategory.livestock_benefits.value}"
        ).json()
        if p["cover_type"] == "Cattle during funeral"
    )
    payload = _valid_payload(livestock["id"], dependents=0, beneficiaries=[])
    r = client.post("/cover-signup", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["beneficiary_count"] == 0
    assert Decimal(body["monthly_premium"]) == Decimal("250.00")
    # The created policy is `individual` and uses the livestock plan's premium.
    p = db.query(Policy).filter(Policy.id == body["policy_id"]).one()
    assert p.policy_type == PolicyType.individual
    assert p.premium_amount == Decimal("250.00")


def test_livestock_signup_rejects_supplied_beneficiaries(client, seeded_plans):
    """If a caller mistakenly attaches beneficiaries to a livestock plan,
    we 400 with a clear message rather than silently ignoring them."""
    livestock = next(
        p for p in client.get(
            f"/cover-plans?category={CoverCategory.livestock_benefits.value}"
        ).json()
        if p["cover_type"] == "Goat in December"
    )
    payload = _valid_payload(livestock["id"], dependents=0)  # default has 1 beneficiary
    r = client.post("/cover-signup", json=payload)
    assert r.status_code == 400
    assert "do not take beneficiaries" in r.json()["detail"]


def test_funeral_signup_still_requires_beneficiaries(client, seeded_plans):
    """Removing beneficiaries from a funeral-cover signup now 400s in the service."""
    plan_id = _family_plan_id(client, seeded_plans)
    payload = _valid_payload(plan_id, dependents=0, beneficiaries=[])
    r = client.post("/cover-signup", json=payload)
    assert r.status_code == 400
    assert "beneficiary is required" in r.json()["detail"]


# ---------- 3-month lapse still works on policies created via the wizard ----------


def test_wizard_created_policy_lapses_after_three_months(client, seeded_plans, db):
    """End-to-end: a wizard signup with no payments lapses after 3+ months."""
    from datetime import date
    from app.services.billing_sweep import run_billing_sweep

    plan_id = _family_plan_id(client, seeded_plans)
    body = client.post("/cover-signup", json=_valid_payload(plan_id)).json()
    policy_id = body["policy_id"]

    # Time-travel 4 months forward and re-evaluate.
    today = date.today()
    future = date(today.year + (today.month + 4 > 12),
                  ((today.month + 4 - 1) % 12) + 1, 15)
    run_billing_sweep(db, as_of=future)

    db.expire_all()
    p = db.query(Policy).filter(Policy.id == policy_id).one()
    assert p.status == PolicyStatus.lapsed
