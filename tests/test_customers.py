"""Tests for GET /customers endpoint."""
from datetime import date
from decimal import Decimal

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


def test_list_customers_filtered_by_scheme_type(client, admin_token, db, _seed_plans):
    """A customer with a funeral policy appears under ?scheme_type=funeral,
    not under ?scheme_type=purchase."""
    fcust = Customer(full_name="Funeral Holder", id_number="9001011234567",
                     status=CustomerStatus.active)
    pcust = Customer(full_name="Purchase Holder", id_number="9002021234567",
                     status=CustomerStatus.active)
    db.add_all([fcust, pcust])
    db.flush()

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
    """Scheme with no customers returns empty list."""
    r = client.get("/customers?scheme_type=stokvel",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_customers_unknown_scheme_422(client, admin_token):
    """Unknown scheme enum value returns 422."""
    r = client.get("/customers?scheme_type=not_a_real_scheme",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 422
