"""End-to-end API tests covering auto-lapse and status endpoints."""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta


def _create_customer(client, **overrides):
    payload = {
        "full_name": "John Doe",
        "id_number": "8001010001234",
        "phone": "+27820000000",
        "email": "john@example.com",
    }
    payload.update(overrides)
    r = client.post("/customers", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_policy(client, customer_id: int, premium: str = "100.00", start_offset_months: int = 6, **extra):
    start = (date.today() - relativedelta(months=start_offset_months)).isoformat()
    body = {
        "customer_id": customer_id,
        "policy_type": "individual",
        "premium_amount": premium,
        "billing_cycle": "monthly",
        "start_date": start,
    }
    body.update(extra)
    r = client.post("/policies", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _create_payment(client, customer_id: int, policy_id: int, amount: str, on_date: date):
    r = client.post("/payments", json={
        "customer_id": customer_id,
        "policy_id": policy_id,
        "amount_paid": amount,
        "payment_date": on_date.isoformat(),
        "payment_method": "cash",
        "status": "paid",
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_auth_required(client):
    r = client.get("/customers/1/payment-status")
    assert r.status_code == 401


def test_customer_fully_paid(auth_client):
    customer = _create_customer(auth_client)
    policy = _create_policy(auth_client, customer["id"], premium="100.00", start_offset_months=3)
    # Pay every month from start to today
    cur = date.today() - relativedelta(months=3)
    while cur <= date.today():
        _create_payment(auth_client, customer["id"], policy["id"], "100.00", cur)
        cur = cur + relativedelta(months=1)
    r = auth_client.get(f"/customers/{customer['id']}/payment-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall_status"] == "PAID"
    assert body["policies"][0]["months_in_arrears"] == 0


def test_customer_overdue_and_auto_lapse(auth_client):
    customer = _create_customer(auth_client, id_number="9001010001234", email="late@example.com")
    # Start 6 months ago, threshold=2 => lapses easily
    policy = _create_policy(auth_client, customer["id"], premium="100.00",
                            start_offset_months=6, lapse_threshold_months=2, grace_period_days=15)
    # No payments at all
    r = auth_client.get(f"/customers/{customer['id']}/payment-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall_status"] == "OVERDUE"
    assert body["policies"][0]["months_in_arrears"] >= 2
    # Side effect: policy should have been lapsed
    assert body["policies"][0]["status"] == "lapsed"


def test_payment_status_month_filter(auth_client):
    customer = _create_customer(auth_client, id_number="7001010001234", email="filt@example.com")
    policy = _create_policy(auth_client, customer["id"], premium="100.00", start_offset_months=3)
    paid_month = date.today() - relativedelta(months=1)
    _create_payment(auth_client, customer["id"], policy["id"], "100.00", paid_month)
    month_key = f"{paid_month.year:04d}-{paid_month.month:02d}"
    r = auth_client.get(f"/customers/{customer['id']}/payment-status", params={"month": month_key})
    body = r.json()
    assert len(body["policies"][0]["months"]) == 1
    assert body["policies"][0]["months"][0]["status"] == "PAID"


def test_group_scheme_member_status(auth_client):
    customer = _create_customer(auth_client, id_number="6001010001234", email="grp@example.com")
    policy = _create_policy(auth_client, customer["id"], premium="300.00",
                            start_offset_months=3, policy_type="group_scheme")
    # Add 2 members
    r1 = auth_client.post("/members", json={
        "policy_id": policy["id"], "full_name": "Member A", "contribution_amount": "100.00",
    })
    r2 = auth_client.post("/members", json={
        "policy_id": policy["id"], "full_name": "Member B", "contribution_amount": "100.00",
    })
    m_a = r1.json()
    m_b = r2.json()
    # Member A pays every month, Member B never
    cur = date.today() - relativedelta(months=3)
    while cur <= date.today():
        auth_client.post("/payments", json={
            "customer_id": customer["id"], "policy_id": policy["id"], "member_id": m_a["id"],
            "amount_paid": "100.00", "payment_date": cur.isoformat(),
            "payment_method": "cash", "status": "paid",
        })
        cur = cur + relativedelta(months=1)
    r = auth_client.get(f"/members/policy/{policy['id']}/payment-status")
    body = r.json()
    by_name = {m["full_name"]: m for m in body}
    assert by_name["Member A"]["status"] == "PAID"
    assert by_name["Member B"]["status"] in ("OVERDUE", "NOT_PAID")
