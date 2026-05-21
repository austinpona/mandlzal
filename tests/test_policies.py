"""Tests for GET /policies endpoint."""
from datetime import date

import pytest

from app.models.cover_plan import CoverPlan, SchemeType
from app.models.customer import Customer, CustomerStatus
from app.models.policy import Policy, PolicyStatus, PolicyType
from app.services.cover_seed import seed_cover_plans


def _register(client, email: str):
    """Helper: register user and return the response."""
    return client.post("/auth/register", json={
        "email": email,
        "password": "secret123",
        "full_name": "Test User",
    }).json()


def _login(client, email: str) -> str:
    """Helper: login user and return the access token."""
    resp = client.post(
        "/auth/login",
        data={"username": email, "password": "secret123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def admin_token(client):
    """Create an admin user and return their access token."""
    _register(client, "admin@example.com")
    return _login(client, "admin@example.com")


@pytest.fixture
def _seed_plans(db):
    """Seed the default cover-plan catalog before each test that needs it."""
    seed_cover_plans(db)


def test_list_policies_filtered_by_scheme_type(client, admin_token, db, _seed_plans):
    """Policies can be filtered by scheme_type via ?scheme_type=<type>."""
    cust = Customer(full_name="Holder", id_number="9101011234567",
                    status=CustomerStatus.active)
    db.add(cust)
    db.flush()

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
    """Policies can be filtered by customer_id via ?customer_id=<id>."""
    a = Customer(full_name="A", id_number="9201011234567", status=CustomerStatus.active)
    b = Customer(full_name="B", id_number="9202021234567", status=CustomerStatus.active)
    db.add_all([a, b])
    db.flush()
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
