"""Seed sample data for local development.

Creates:
- admin user (admin@example.com / admin123)
- 3 customers
- 4 policies (incl. one group scheme with 3 members)
- A range of payments demonstrating PAID / NOT_PAID / OVERDUE cases.

Run with:  python -m scripts.seed
"""
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.core.security import hash_password
from app.database import SessionLocal, init_db
from app.models.customer import Customer, CustomerStatus
from app.models.member import Member
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy, PolicyType, PolicyStatus, BillingCycle
from app.models.user import Role, User


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "admin@example.com").first():
            db.add(User(
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                full_name="Admin User",
                is_admin=True,
                role=Role.admin,
            ))

        # Customer 1: fully paid up
        c1 = Customer(full_name="Sipho Dlamini", id_number="8001015009087",
                      phone="+27821234567", email="sipho@example.com",
                      status=CustomerStatus.active)
        # Customer 2: in arrears
        c2 = Customer(full_name="Thandi Nkosi", id_number="8503125009088",
                      phone="+27827654321", email="thandi@example.com",
                      status=CustomerStatus.active)
        # Customer 3: group scheme holder
        c3 = Customer(full_name="Mandla Mthembu", id_number="7501015009089",
                      phone="+27829999999", email="mandla@example.com",
                      status=CustomerStatus.active)
        db.add_all([c1, c2, c3])
        db.flush()

        today = date.today()
        six_months_ago = today - relativedelta(months=6)

        p1 = Policy(customer_id=c1.id, policy_type=PolicyType.individual,
                    premium_amount=Decimal("150.00"), billing_cycle=BillingCycle.monthly,
                    start_date=six_months_ago, status=PolicyStatus.active)
        p2 = Policy(customer_id=c2.id, policy_type=PolicyType.individual,
                    premium_amount=Decimal("200.00"), billing_cycle=BillingCycle.monthly,
                    start_date=six_months_ago, status=PolicyStatus.active)
        p3 = Policy(customer_id=c3.id, policy_type=PolicyType.group_scheme,
                    premium_amount=Decimal("450.00"), billing_cycle=BillingCycle.monthly,
                    start_date=six_months_ago, status=PolicyStatus.active)
        db.add_all([p1, p2, p3])
        db.flush()

        m1 = Member(policy_id=p3.id, full_name="Mandla Mthembu",
                    relationship_to_holder="self", contribution_amount=Decimal("150.00"))
        m2 = Member(policy_id=p3.id, full_name="Nomsa Mthembu",
                    relationship_to_holder="spouse", contribution_amount=Decimal("150.00"))
        m3 = Member(policy_id=p3.id, full_name="Lwazi Mthembu",
                    relationship_to_holder="child", contribution_amount=Decimal("150.00"))
        db.add_all([m1, m2, m3])
        db.flush()

        # c1 paid every month
        cur = six_months_ago
        while cur <= today:
            db.add(Payment(
                customer_id=c1.id, policy_id=p1.id,
                amount_paid=Decimal("150.00"),
                payment_date=cur, payment_method=PaymentMethod.debit_order,
                status=PaymentStatus.paid, reference=f"PAY-C1-{cur:%Y%m}",
            ))
            cur = cur + relativedelta(months=1)

        # c2 paid only first 2 months
        cur = six_months_ago
        for _ in range(2):
            db.add(Payment(
                customer_id=c2.id, policy_id=p2.id,
                amount_paid=Decimal("200.00"),
                payment_date=cur, payment_method=PaymentMethod.eft,
                status=PaymentStatus.paid, reference=f"PAY-C2-{cur:%Y%m}",
            ))
            cur = cur + relativedelta(months=1)

        # c3 (group): m1 paid all months, m2 paid 4, m3 paid 1
        cur = six_months_ago
        i = 0
        while cur <= today:
            # m1 always pays
            db.add(Payment(customer_id=c3.id, policy_id=p3.id, member_id=m1.id,
                           amount_paid=Decimal("150.00"), payment_date=cur,
                           payment_method=PaymentMethod.debit_order,
                           status=PaymentStatus.paid,
                           reference=f"PAY-M1-{cur:%Y%m}"))
            # m2 pays first 4 months
            if i < 4:
                db.add(Payment(customer_id=c3.id, policy_id=p3.id, member_id=m2.id,
                               amount_paid=Decimal("150.00"), payment_date=cur,
                               payment_method=PaymentMethod.debit_order,
                               status=PaymentStatus.paid,
                               reference=f"PAY-M2-{cur:%Y%m}"))
            # m3 pays only first month
            if i < 1:
                db.add(Payment(customer_id=c3.id, policy_id=p3.id, member_id=m3.id,
                               amount_paid=Decimal("150.00"), payment_date=cur,
                               payment_method=PaymentMethod.debit_order,
                               status=PaymentStatus.paid,
                               reference=f"PAY-M3-{cur:%Y%m}"))
            cur = cur + relativedelta(months=1)
            i += 1

        db.commit()
        print("Seed complete.")
        print("Login: admin@example.com / admin123")
    finally:
        db.close()


if __name__ == "__main__":
    main()
