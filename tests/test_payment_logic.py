"""Unit tests for pure billing/payment-status logic."""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.models.payment import Payment, PaymentStatus, PaymentMethod
from app.models.policy import Policy, PolicyStatus, PolicyType, BillingCycle
from app.services import billing


def _policy(start: date, premium: str = "100.00", grace_days: int = 30, lapse_months: int = 3) -> Policy:
    return Policy(
        customer_id=1,
        policy_type=PolicyType.individual,
        premium_amount=Decimal(premium),
        billing_cycle=BillingCycle.monthly,
        start_date=start,
        status=PolicyStatus.active,
        grace_period_days=grace_days,
        lapse_threshold_months=lapse_months,
    )


def _payment(policy_id: int, amount: str, day: date, status: PaymentStatus = PaymentStatus.paid) -> Payment:
    return Payment(
        customer_id=1, policy_id=policy_id,
        amount_paid=Decimal(amount), payment_date=day,
        payment_method=PaymentMethod.cash, status=status,
    )


def test_expected_months_inclusive():
    today = date(2024, 6, 15)
    pol = _policy(start=date(2024, 4, 10))
    months = billing.expected_months(pol, as_of=today)
    assert [m.isoformat() for m in months] == ["2024-04-01", "2024-05-01", "2024-06-01"]


def test_classify_paid_full():
    assert billing.classify_month(Decimal("100"), Decimal("100"),
                                  date(2024, 1, 1), date(2024, 1, 5), 30) == billing.STATUS_PAID


def test_classify_not_paid_within_grace():
    assert billing.classify_month(Decimal("100"), Decimal("0"),
                                  date(2024, 1, 1), date(2024, 1, 15), 30) == billing.STATUS_NOT_PAID


def test_classify_overdue_after_grace():
    assert billing.classify_month(Decimal("100"), Decimal("0"),
                                  date(2024, 1, 1), date(2024, 3, 1), 30) == billing.STATUS_OVERDUE


def test_classify_partial_within_grace_is_partial():
    assert billing.classify_month(Decimal("100"), Decimal("40"),
                                  date(2024, 1, 1), date(2024, 1, 10), 30) == billing.STATUS_PARTIAL


def test_classify_partial_after_grace_is_overdue():
    assert billing.classify_month(Decimal("100"), Decimal("40"),
                                  date(2024, 1, 1), date(2024, 3, 1), 30) == billing.STATUS_OVERDUE


def test_compute_policy_status_full_paid():
    today = date(2024, 6, 15)
    pol = _policy(start=date(2024, 4, 1))
    payments = [
        _payment(1, "100", date(2024, 4, 5)),
        _payment(1, "100", date(2024, 5, 5)),
        _payment(1, "100", date(2024, 6, 5)),
    ]
    months, arrears, outstanding = billing.compute_policy_status(pol, payments, as_of=today)
    assert len(months) == 3
    assert all(m.status == billing.STATUS_PAID for m in months)
    assert arrears == 0
    assert outstanding == Decimal("0")


def test_compute_policy_status_with_arrears():
    today = date(2024, 6, 15)
    pol = _policy(start=date(2024, 1, 1))
    # Only Jan paid; Feb-Apr are overdue (past grace); May/Jun status depends on grace.
    payments = [_payment(1, "100", date(2024, 1, 5))]
    months, arrears, outstanding = billing.compute_policy_status(pol, payments, as_of=today)
    assert len(months) == 6
    assert months[0].status == billing.STATUS_PAID
    # Feb/Mar/Apr definitely overdue
    assert months[1].status == billing.STATUS_OVERDUE
    assert months[2].status == billing.STATUS_OVERDUE
    assert months[3].status == billing.STATUS_OVERDUE
    assert arrears >= 3
    assert outstanding >= Decimal("300")


def test_failed_payment_does_not_count():
    # Within grace window so a missing payment is NOT_PAID rather than OVERDUE.
    today = date(2024, 1, 20)
    pol = _policy(start=date(2024, 1, 1))
    payments = [_payment(1, "100", date(2024, 1, 5), status=PaymentStatus.failed)]
    months, arrears, _ = billing.compute_policy_status(pol, payments, as_of=today)
    assert months[0].status == billing.STATUS_NOT_PAID
    assert arrears == 0


def test_get_payment_status_for_month():
    today = date(2024, 6, 15)
    pol = _policy(start=date(2024, 1, 1))
    payments = [_payment(1, "100", date(2024, 3, 5))]
    assert billing.get_payment_status_for_month(pol, payments, date(2024, 3, 1), as_of=today) == billing.STATUS_PAID
    assert billing.get_payment_status_for_month(pol, payments, date(2024, 2, 1), as_of=today) == billing.STATUS_OVERDUE


def test_should_lapse_threshold():
    pol = _policy(start=date(2024, 1, 1), lapse_months=3)
    assert billing.should_lapse(pol, months_in_arrears=2) is False
    assert billing.should_lapse(pol, months_in_arrears=3) is True


def test_should_not_lapse_when_already_lapsed():
    pol = _policy(start=date(2024, 1, 1), lapse_months=3)
    pol.status = PolicyStatus.lapsed
    assert billing.should_lapse(pol, months_in_arrears=5) is False
