"""Tests for the daily billing sweep + admin trigger endpoint."""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.models.customer import Customer, CustomerStatus
from app.models.notification import Notification
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy, PolicyStatus, PolicyType, BillingCycle
from app.services.billing_sweep import run_billing_sweep


def _seed_policy(db, *, premium="100.00", start_offset_months=6,
                 lapse_threshold=3, grace_days=30, status=PolicyStatus.active,
                 id_number="9001010001234"):
    customer = Customer(
        full_name="Sweep Tester", id_number=id_number,
        status=CustomerStatus.active,
    )
    db.add(customer)
    db.flush()
    policy = Policy(
        customer_id=customer.id, policy_type=PolicyType.individual,
        premium_amount=Decimal(premium), billing_cycle=BillingCycle.monthly,
        start_date=date.today() - relativedelta(months=start_offset_months),
        status=status, grace_period_days=grace_days,
        lapse_threshold_months=lapse_threshold,
    )
    db.add(policy)
    db.flush()
    return customer, policy


def _pay(db, customer_id, policy_id, when, amount="100.00"):
    db.add(Payment(
        customer_id=customer_id, policy_id=policy_id,
        amount_paid=Decimal(amount), payment_date=when,
        payment_method=PaymentMethod.cash, status=PaymentStatus.paid,
    ))


# ---------- Pure sweep logic ----------


def test_sweep_lapses_overdue_policy(db):
    customer, policy = _seed_policy(
        db, start_offset_months=6, lapse_threshold=2, grace_days=15,
        id_number="9001010000001",
    )
    db.commit()

    report = run_billing_sweep(db)

    assert report.policies_scanned == 1
    assert report.policies_lapsed == 1
    db.refresh(policy)
    db.refresh(customer)
    assert policy.status == PolicyStatus.lapsed
    assert customer.status == CustomerStatus.lapsed  # only policy is lapsed → customer follows


def test_sweep_emits_missed_payment_notifications(db):
    _, policy = _seed_policy(
        db, start_offset_months=4, lapse_threshold=99, grace_days=15,
        id_number="9001010000002",
    )
    db.commit()

    report = run_billing_sweep(db)

    # 4 months of arrears expected (none paid + past grace)
    assert report.missed_payment_notifications >= 3
    notes = db.query(Notification).filter(Notification.policy_id == policy.id,
                                          Notification.type == "MISSED_PAYMENT").all()
    assert len(notes) == report.missed_payment_notifications


def test_sweep_is_idempotent_for_notifications(db):
    _, policy = _seed_policy(
        db, start_offset_months=3, lapse_threshold=99, grace_days=15,
        id_number="9001010000003",
    )
    db.commit()

    first = run_billing_sweep(db)
    assert first.missed_payment_notifications > 0

    second = run_billing_sweep(db)
    # No new notifications on the second run for the same (policy, month) pairs.
    assert second.missed_payment_notifications == 0
    # Total stored notifications still equals what the first run produced.
    total = db.query(Notification).filter(Notification.policy_id == policy.id,
                                          Notification.type == "MISSED_PAYMENT").count()
    assert total == first.missed_payment_notifications


def test_sweep_skips_already_paid_policy(db):
    customer, policy = _seed_policy(
        db, start_offset_months=3, lapse_threshold=2, grace_days=15,
        id_number="9001010000004",
    )
    cur = date.today() - relativedelta(months=3)
    while cur <= date.today():
        _pay(db, customer.id, policy.id, cur)
        cur = cur + relativedelta(months=1)
    db.commit()

    report = run_billing_sweep(db)
    assert report.policies_lapsed == 0
    assert report.missed_payment_notifications == 0
    db.refresh(policy)
    assert policy.status == PolicyStatus.active


def test_sweep_skips_already_lapsed_policy(db):
    _, policy = _seed_policy(
        db, start_offset_months=12, lapse_threshold=1, grace_days=0,
        status=PolicyStatus.lapsed,
        id_number="9001010000005",
    )
    db.commit()

    report = run_billing_sweep(db)
    assert report.policies_scanned == 0  # only active policies are scanned
    assert report.policies_lapsed == 0


# ---------- Admin endpoint ----------


def test_admin_endpoint_runs_sweep(auth_client):
    # The first registered user is automatically admin.
    r = auth_client.post("/admin/run-billing-sweep")
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("as_of", "policies_scanned", "policies_lapsed",
              "customers_lapsed", "missed_payment_notifications",
              "total_outstanding"):
        assert k in body


def test_admin_endpoint_rejects_invalid_as_of(auth_client):
    r = auth_client.post("/admin/run-billing-sweep", params={"as_of": "not-a-date"})
    assert r.status_code == 400


def test_admin_endpoint_requires_admin(client):
    # Register a SECOND user (not admin, because the first user already exists).
    client.post("/auth/register", json={
        "email": "first-admin@example.com", "password": "secret123",
    })
    client.post("/auth/register", json={
        "email": "non-admin@example.com", "password": "secret123",
    })
    r = client.post("/auth/login",
                    data={"username": "non-admin@example.com", "password": "secret123"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = r.json()["access_token"]
    r = client.post("/admin/run-billing-sweep",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_endpoint_unauthenticated_is_401(client):
    r = client.post("/admin/run-billing-sweep")
    assert r.status_code == 401
