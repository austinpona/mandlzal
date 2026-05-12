"""Billing / payment-status domain logic.

This module contains the *pure* business rules:
- expected monthly billing periods for a policy
- whether a given month is PAID / NOT PAID / OVERDUE
- whether a policy should be lapsed

It is intentionally framework-free so it can be unit-tested without a DB
session or HTTP layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from dateutil.relativedelta import relativedelta

from app.config import settings
from app.models.payment import Payment, PaymentStatus
from app.models.policy import Policy, PolicyStatus


# Domain-level status constants used in API responses.
STATUS_PAID = "PAID"
STATUS_NOT_PAID = "NOT_PAID"
STATUS_OVERDUE = "OVERDUE"
STATUS_PARTIAL = "PARTIAL"


def month_key(d: date) -> str:
    """Return the 'YYYY-MM' key for the month containing `d`."""
    return f"{d.year:04d}-{d.month:02d}"


def first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def expected_months(policy: Policy, as_of: date | None = None) -> list[date]:
    """Return the list of monthly billing period start dates that are due
    for `policy` from its start date through `as_of` (inclusive).

    Only `monthly` cycles are supported (per spec).
    """
    if as_of is None:
        as_of = date.today()
    start = first_of_month(policy.start_date)
    end = first_of_month(as_of)
    if start > end:
        return []
    months: list[date] = []
    cur = start
    while cur <= end:
        months.append(cur)
        cur = cur + relativedelta(months=1)
    return months


def _policy_grace_days(policy: Policy) -> int:
    """Grace period for a policy, falling back to global default."""
    return policy.grace_period_days if policy.grace_period_days is not None else settings.GRACE_PERIOD_DAYS


def _policy_lapse_threshold(policy: Policy) -> int:
    return policy.lapse_threshold_months if policy.lapse_threshold_months is not None else settings.LAPSE_THRESHOLD_MONTHS


def is_overdue(month_start: date, as_of: date, grace_days: int) -> bool:
    """A month is overdue once we are past (month_start + grace_days)."""
    return as_of > month_start + timedelta(days=grace_days)


def sum_paid_for_month(payments: Iterable[Payment], month_start: date) -> Decimal:
    """Sum of successfully-paid amounts whose `payment_date` falls inside
    the month identified by `month_start`. Only `status=paid` counts."""
    total = Decimal("0")
    for p in payments:
        if p.status != PaymentStatus.paid:
            continue
        if p.payment_date.year == month_start.year and p.payment_date.month == month_start.month:
            total += Decimal(p.amount_paid)
    return total


@dataclass
class MonthStatus:
    month_start: date
    expected: Decimal
    paid: Decimal
    status: str


def classify_month(expected: Decimal, paid: Decimal, month_start: date, as_of: date, grace_days: int) -> str:
    """Return PAID / PARTIAL / NOT_PAID / OVERDUE for a single month."""
    if paid >= expected and expected > 0:
        return STATUS_PAID
    if paid > 0 and paid < expected:
        # Partially paid; if past grace, treat as overdue.
        return STATUS_OVERDUE if is_overdue(month_start, as_of, grace_days) else STATUS_PARTIAL
    # Nothing paid.
    if is_overdue(month_start, as_of, grace_days):
        return STATUS_OVERDUE
    return STATUS_NOT_PAID


def compute_policy_status(
    policy: Policy,
    payments: Iterable[Payment],
    as_of: date | None = None,
) -> tuple[list[MonthStatus], int, Decimal]:
    """Compute per-month statuses for a policy.

    Returns:
        (months, months_in_arrears, total_outstanding)
        where `months_in_arrears` counts months whose status is OVERDUE
        and `total_outstanding` is the sum of (expected - paid) for those.
    """
    if as_of is None:
        as_of = date.today()
    grace = _policy_grace_days(policy)
    expected_amount = Decimal(policy.premium_amount)
    payments_list = list(payments)

    results: list[MonthStatus] = []
    arrears = 0
    outstanding = Decimal("0")
    for m in expected_months(policy, as_of):
        paid = sum_paid_for_month(payments_list, m)
        status = classify_month(expected_amount, paid, m, as_of, grace)
        results.append(MonthStatus(month_start=m, expected=expected_amount, paid=paid, status=status))
        if status == STATUS_OVERDUE:
            arrears += 1
            outstanding += max(expected_amount - paid, Decimal("0"))
    return results, arrears, outstanding


def should_lapse(policy: Policy, months_in_arrears: int) -> bool:
    """Policy should lapse if arrears exceed the configured threshold."""
    return months_in_arrears >= _policy_lapse_threshold(policy) and policy.status == PolicyStatus.active


def get_payment_status_for_month(
    policy: Policy,
    payments: Iterable[Payment],
    target_month: date,
    as_of: date | None = None,
) -> str:
    """Public helper - status for a single given month.

    Implements the spec's `getPaymentStatus(customer_id, month)` semantics
    at the policy level. (Customer-level aggregation lives in the API layer.)
    """
    if as_of is None:
        as_of = date.today()
    grace = _policy_grace_days(policy)
    m = first_of_month(target_month)
    paid = sum_paid_for_month(payments, m)
    return classify_month(Decimal(policy.premium_amount), paid, m, as_of, grace)
