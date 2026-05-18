"""EMAIL_RECEIPT notifications render and send the receipt PDF."""
from decimal import Decimal

from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.customer import Customer, CustomerStatus
from app.models.notification import Notification
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy, PolicyStatus
from app.services.notification_dispatcher import dispatch_pending_notifications


def test_email_receipt_renders_pdf_and_calls_provider(db, monkeypatch):
    plan = CoverPlan(
        category=CoverCategory.me,
        cover_type="Me",
        monthly_premium=Decimal("120"),
        max_dependents=0,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    customer = Customer(
        full_name="X Y",
        first_names="X",
        surname="Y",
        id_number="1",
        email="x@example.com",
        status=CustomerStatus.active,
    )
    db.add(customer)
    db.commit()
    policy = Policy(
        customer_id=customer.id,
        premium_amount=Decimal("120"),
        status=PolicyStatus.active,
        cover_plan_id=plan.id,
    )
    db.add(policy)
    db.commit()
    payment = Payment(
        customer_id=customer.id,
        policy_id=policy.id,
        amount_paid=Decimal("120"),
        payment_method=PaymentMethod.cash,
        status=PaymentStatus.paid,
    )
    db.add(payment)
    db.commit()
    notif = Notification(
        customer_id=customer.id,
        policy_id=policy.id,
        type="EMAIL_RECEIPT",
        message=f"Receipt for policy {policy.id}",
    )
    db.add(notif)
    db.commit()

    sent: list[dict] = []

    def fake_send(to, subject, body, *, attachments=None):
        sent.append({
            "to": to,
            "subject": subject,
            "attachments": [a["filename"] for a in (attachments or [])],
        })
        return True

    monkeypatch.setattr("app.services.notification_dispatcher.send_email", fake_send)
    report = dispatch_pending_notifications(db)

    assert report.sent == 1
    assert sent
    assert sent[0]["to"] == "x@example.com"
    assert any(name.endswith(".pdf") for name in sent[0]["attachments"])
