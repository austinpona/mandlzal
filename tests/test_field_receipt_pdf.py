"""Tests for the server-side receipt PDF renderer."""
from datetime import date
from decimal import Decimal

from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.customer import Customer, CustomerStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy, PolicyStatus
from app.services.receipt_pdf import build_receipt_data, render_receipt_pdf


def _seed_signup(db):
    plan = CoverPlan(
        category=CoverCategory.me_and_family,
        cover_type="Family",
        monthly_premium=Decimal("360"),
        max_dependents=4,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    customer = Customer(
        full_name="John Smith",
        first_names="John",
        surname="Smith",
        id_number="ID123",
        email="john@example.com",
        status=CustomerStatus.active,
    )
    db.add(customer)
    db.commit()
    policy = Policy(
        customer_id=customer.id,
        premium_amount=Decimal("360"),
        status=PolicyStatus.active,
        cover_plan_id=plan.id,
    )
    db.add(policy)
    db.commit()
    payment = Payment(
        customer_id=customer.id,
        policy_id=policy.id,
        amount_paid=Decimal("360"),
        payment_date=date.today(),
        payment_method=PaymentMethod.cash,
        status=PaymentStatus.paid,
        reference="MZ-abc123",
    )
    db.add(payment)
    db.commit()
    return customer, policy, payment


def test_build_receipt_data_shape(db):
    _, policy, payment = _seed_signup(db)
    data = build_receipt_data(db, payment_id=payment.id)
    assert data["holder_name"] == "John Smith"
    assert data["plan_name"] == "Family"
    assert data["amount_paid"] == "360.00"
    assert data["reference"] == "MZ-abc123"
    assert data["policy_id"] == policy.id


def test_render_receipt_pdf_returns_pdf_bytes(db):
    _, _, payment = _seed_signup(db)
    data = build_receipt_data(db, payment_id=payment.id)
    pdf_bytes = render_receipt_pdf(data)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000
