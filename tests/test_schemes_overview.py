"""Tests for GET /schemes/{scheme_type}/overview."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.cover_plan import CoverPlan, SchemeType
from app.models.customer import Customer, CustomerStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
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
