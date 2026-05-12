"""Playwright-driven black-box review of the live API.

Boots the FastAPI app in a background uvicorn process and hits it via
Playwright's APIRequestContext (HTTP-only - no browsers needed). The goal
is to exercise the whole stack end-to-end and surface integration bugs
that pure-Python TestClient runs may miss.

Run on its own (separate from the rest of the suite)::

    .venv/Scripts/python -m pytest tests/test_playwright_api.py -q
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright, APIRequestContext


ROOT = Path(__file__).resolve().parents[1]
DB_FILE = ROOT / "playwright_mandlzi.db"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_server(base_url: str, timeout: float = 20.0) -> None:
    import urllib.request, urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"Server at {base_url} did not become ready in {timeout}s")


@pytest.fixture(scope="module")
def server():
    """Spawn uvicorn against an isolated SQLite DB and yield its base URL."""
    if DB_FILE.exists():
        DB_FILE.unlink()
    port = _free_port()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
    env["JWT_SECRET"] = "playwright-secret"
    env["GRACE_PERIOD_DAYS"] = "30"
    env["LAPSE_THRESHOLD_MONTHS"] = "3"
    env["SCHEDULER_ENABLED"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if DB_FILE.exists():
            try:
                DB_FILE.unlink()
            except PermissionError:
                pass


@pytest.fixture(scope="module")
def pw():
    """Single Playwright instance shared by all tests in the module."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
def anon(pw, server) -> APIRequestContext:
    """Unauthenticated request context."""
    ctx = pw.request.new_context(base_url=server)
    yield ctx
    ctx.dispose()


@pytest.fixture(scope="module")
def api(pw, server, anon) -> APIRequestContext:
    """Authenticated Playwright APIRequestContext bound to the live server."""
    # Register first user (becomes admin) and login. Tolerate prior runs.
    r = anon.post("/auth/register", data={
        "email": "pw@example.com", "password": "pwpw1234", "full_name": "PW",
    })
    assert r.status in (201, 400), f"register failed: {r.status} {r.text()}"
    r = anon.post("/auth/login", form={"username": "pw@example.com", "password": "pwpw1234"})
    assert r.status == 200, f"login failed: {r.status} {r.text()}"
    token = r.json()["access_token"]

    ctx = pw.request.new_context(
        base_url=server,
        extra_http_headers={"Authorization": f"Bearer {token}"},
    )
    yield ctx
    ctx.dispose()


# ---------- Auth / smoke ----------


def test_health(anon: APIRequestContext):
    r = anon.get("/health")
    assert r.status == 200
    assert r.json() == {"status": "ok"}


def test_unauthenticated_endpoints_return_401(anon: APIRequestContext):
    for path in ["/customers", "/dashboard", "/audit-logs",
                 "/customers/1/payment-status", "/policies/1", "/payments/1"]:
        r = anon.get(path)
        assert r.status == 401, f"{path} should require auth (got {r.status})"


def test_register_duplicate_rejected(api: APIRequestContext, anon: APIRequestContext):
    # `api` fixture guarantees pw@example.com is already registered.
    r = anon.post("/auth/register", data={
        "email": "pw@example.com", "password": "pwpw1234", "full_name": "Dup",
    })
    assert r.status == 400


def test_login_bad_password_rejected(api: APIRequestContext, anon: APIRequestContext):
    r = anon.post("/auth/login", form={"username": "pw@example.com", "password": "wrong"})
    assert r.status == 400


def test_me_endpoint(api: APIRequestContext):
    r = api.get("/auth/me")
    assert r.status == 200
    body = r.json()
    assert body["email"] == "pw@example.com"
    assert body["is_admin"] is True  # first user becomes admin


# ---------- Customers CRUD ----------


def test_customer_crud_and_validation(api: APIRequestContext):
    # Bad payload: missing required fields
    r = api.post("/customers", data={"full_name": "X"})
    assert r.status == 422

    # Bad email format
    r = api.post("/customers", data={
        "full_name": "Bad Email", "id_number": "1111111111111", "email": "not-an-email",
    })
    assert r.status == 422

    # Create OK
    r = api.post("/customers", data={
        "full_name": "Alice", "id_number": "9001010001234",
        "phone": "+27821111111", "email": "alice@example.com",
    })
    assert r.status == 201, r.text()
    alice = r.json()
    assert alice["status"] == "active"

    # Duplicate id_number
    r = api.post("/customers", data={
        "full_name": "Alice Dup", "id_number": "9001010001234",
    })
    assert r.status == 400

    # GET
    r = api.get(f"/customers/{alice['id']}")
    assert r.status == 200

    # PATCH
    r = api.patch(f"/customers/{alice['id']}", data={"phone": "+27822222222"})
    assert r.status == 200
    assert r.json()["phone"] == "+27822222222"

    # 404 on missing
    r = api.get("/customers/9999999")
    assert r.status == 404

    # DELETE
    r = api.delete(f"/customers/{alice['id']}")
    assert r.status == 204
    r = api.get(f"/customers/{alice['id']}")
    assert r.status == 404


# ---------- Policy / Payment integrity ----------


def _new_customer(api: APIRequestContext, idn: str) -> dict:
    r = api.post("/customers", data={
        "full_name": f"Cust {idn}", "id_number": idn,
    })
    assert r.status == 201, r.text()
    return r.json()


def _new_policy(api: APIRequestContext, customer_id: int, **extra) -> dict:
    body = {
        "customer_id": customer_id, "policy_type": "individual",
        "premium_amount": "100.00", "billing_cycle": "monthly",
        "start_date": (date.today() - relativedelta(months=4)).isoformat(),
    }
    body.update(extra)
    r = api.post("/policies", data=body)
    assert r.status == 201, r.text()
    return r.json()


def test_policy_requires_existing_customer(api: APIRequestContext):
    r = api.post("/policies", data={
        "customer_id": 9999999, "policy_type": "individual",
        "premium_amount": "100.00", "billing_cycle": "monthly",
    })
    assert r.status == 404


def test_policy_premium_must_be_positive(api: APIRequestContext):
    cust = _new_customer(api, "1100000000001")
    r = api.post("/policies", data={
        "customer_id": cust["id"], "policy_type": "individual",
        "premium_amount": "0", "billing_cycle": "monthly",
    })
    assert r.status == 422


def test_payment_must_belong_to_customer_policy(api: APIRequestContext):
    c1 = _new_customer(api, "1100000000002")
    c2 = _new_customer(api, "1100000000003")
    p1 = _new_policy(api, c1["id"])

    # Payment for c2 against c1's policy -> should be rejected
    r = api.post("/payments", data={
        "customer_id": c2["id"], "policy_id": p1["id"],
        "amount_paid": "100.00", "payment_method": "cash", "status": "paid",
    })
    assert r.status == 400


def test_payment_negative_amount_rejected(api: APIRequestContext):
    cust = _new_customer(api, "1100000000004")
    pol = _new_policy(api, cust["id"])
    r = api.post("/payments", data={
        "customer_id": cust["id"], "policy_id": pol["id"],
        "amount_paid": "-50", "payment_method": "cash", "status": "paid",
    })
    assert r.status == 422


# ---------- End-to-end payment status ----------


def test_fully_paid_customer_payment_status(api: APIRequestContext):
    cust = _new_customer(api, "1100000000010")
    pol = _new_policy(api, cust["id"], start_date=(date.today() - relativedelta(months=3)).isoformat())
    cur = date.today() - relativedelta(months=3)
    while cur <= date.today():
        r = api.post("/payments", data={
            "customer_id": cust["id"], "policy_id": pol["id"],
            "amount_paid": "100.00", "payment_date": cur.isoformat(),
            "payment_method": "cash", "status": "paid",
        })
        assert r.status == 201
        cur = cur + relativedelta(months=1)
    r = api.get(f"/customers/{cust['id']}/payment-status")
    assert r.status == 200
    body = r.json()
    assert body["overall_status"] == "PAID"
    assert body["policies"][0]["months_in_arrears"] == 0
    assert float(body["policies"][0]["total_outstanding"]) == 0.0


def test_overdue_customer_auto_lapses(api: APIRequestContext):
    cust = _new_customer(api, "1100000000011")
    pol = _new_policy(api, cust["id"],
                      start_date=(date.today() - relativedelta(months=6)).isoformat(),
                      lapse_threshold_months=2, grace_period_days=15)
    # No payments at all
    r = api.get(f"/customers/{cust['id']}/payment-status")
    assert r.status == 200, r.text()
    body = r.json()
    assert body["overall_status"] == "OVERDUE"
    assert body["policies"][0]["status"] == "lapsed"
    assert body["policies"][0]["months_in_arrears"] >= 2

    # Customer with all-lapsed policies should be lapsed too.
    r = api.get(f"/customers/{cust['id']}")
    assert r.status == 200
    assert r.json()["status"] == "lapsed"

    # Notification + audit entry should exist.
    r = api.get("/notifications")
    assert r.status == 200
    notes = r.json()
    assert any(n["type"] == "POLICY_LAPSED" and n["policy_id"] == pol["id"] for n in notes)

    r = api.get("/audit-logs")
    assert r.status == 200
    assert any(l["action"] == "LAPSE_POLICY" and l["entity_id"] == str(pol["id"]) for l in r.json())


def test_payment_status_invalid_month_param(api: APIRequestContext):
    cust = _new_customer(api, "1100000000012")
    _new_policy(api, cust["id"])
    r = api.get(f"/customers/{cust['id']}/payment-status", params={"month": "not-a-month"})
    assert r.status == 400


def test_payment_status_month_filter_returns_single_month(api: APIRequestContext):
    cust = _new_customer(api, "1100000000013")
    pol = _new_policy(api, cust["id"], start_date=(date.today() - relativedelta(months=3)).isoformat())
    paid_month = date.today() - relativedelta(months=1)
    r = api.post("/payments", data={
        "customer_id": cust["id"], "policy_id": pol["id"],
        "amount_paid": "100.00", "payment_date": paid_month.isoformat(),
        "payment_method": "cash", "status": "paid",
    })
    assert r.status == 201
    mk = f"{paid_month.year:04d}-{paid_month.month:02d}"
    r = api.get(f"/customers/{cust['id']}/payment-status", params={"month": mk})
    body = r.json()
    months = body["policies"][0]["months"]
    assert len(months) == 1
    assert months[0]["status"] == "PAID"


# ---------- Group scheme ----------


def test_group_scheme_member_status(api: APIRequestContext):
    cust = _new_customer(api, "1100000000020")
    pol = _new_policy(api, cust["id"], policy_type="group_scheme",
                      premium_amount="300.00",
                      start_date=(date.today() - relativedelta(months=3)).isoformat())
    members = []
    for name in ["Alpha", "Beta", "Gamma"]:
        r = api.post("/members", data={
            "policy_id": pol["id"], "full_name": name, "contribution_amount": "100.00",
        })
        assert r.status == 201, r.text()
        members.append(r.json())

    # Only Alpha pays every month
    cur = date.today() - relativedelta(months=3)
    while cur <= date.today():
        api.post("/payments", data={
            "customer_id": cust["id"], "policy_id": pol["id"], "member_id": members[0]["id"],
            "amount_paid": "100.00", "payment_date": cur.isoformat(),
            "payment_method": "cash", "status": "paid",
        })
        cur = cur + relativedelta(months=1)

    r = api.get(f"/members/policy/{pol['id']}/payment-status")
    assert r.status == 200, r.text()
    by_name = {m["full_name"]: m for m in r.json()}
    assert by_name["Alpha"]["status"] == "PAID"
    assert by_name["Beta"]["status"] in ("OVERDUE", "NOT_PAID")
    assert by_name["Gamma"]["status"] in ("OVERDUE", "NOT_PAID")


def test_member_payment_rejected_if_wrong_policy(api: APIRequestContext):
    c1 = _new_customer(api, "1100000000021")
    c2 = _new_customer(api, "1100000000022")
    p1 = _new_policy(api, c1["id"])
    p2 = _new_policy(api, c2["id"])
    r = api.post("/members", data={"policy_id": p1["id"], "full_name": "X"})
    assert r.status == 201
    m_id = r.json()["id"]
    # Try to attach payment to p2 with member from p1
    r = api.post("/payments", data={
        "customer_id": c2["id"], "policy_id": p2["id"], "member_id": m_id,
        "amount_paid": "10.00", "payment_method": "cash", "status": "paid",
    })
    assert r.status == 400


# ---------- Dashboard ----------


def test_dashboard_returns_aggregates(api: APIRequestContext):
    r = api.get("/dashboard")
    assert r.status == 200, r.text()
    body = r.json()
    for key in [
        "total_customers", "active_customers", "lapsed_customers", "cancelled_customers",
        "total_policies", "active_policies", "lapsed_policies",
        "paid_this_month", "unpaid_this_month", "overdue_this_month",
        "revenue_this_month", "expected_revenue_this_month",
    ]:
        assert key in body, f"missing dashboard key: {key}"
    assert body["total_customers"] >= 1
