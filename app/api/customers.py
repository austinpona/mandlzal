"""Customer CRUD + per-customer payment status endpoint."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_writer
from app.core.audit import log_action
from app.database import get_db
from app.models.customer import Customer, CustomerStatus
from app.models.payment import Payment
from app.models.policy import Policy, PolicyStatus
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.schemas.payment import (
    CustomerPaymentStatusResponse,
    MonthPaymentStatus,
    PolicyPaymentStatus,
)
from app.services import billing
from app.services.notifications import notify_policy_lapsed


router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_writer),
) -> Customer:
    if db.query(Customer).filter(Customer.id_number == payload.id_number).first():
        raise HTTPException(status_code=400, detail="Customer with this id_number already exists")
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.flush()
    log_action(db, actor=current.email, action="CREATE_CUSTOMER",
               entity_type="customer", entity_id=customer.id, details=payload.model_dump())
    db.commit()
    db.refresh(customer)
    return customer


@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = Query(100, le=500),
) -> list[Customer]:
    return db.query(Customer).offset(skip).limit(limit).all()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_writer),
) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(customer, field, value)
    log_action(db, actor=current.email, action="UPDATE_CUSTOMER",
               entity_type="customer", entity_id=customer.id, details=updates)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> None:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    log_action(db, actor=current.email, action="DELETE_CUSTOMER",
               entity_type="customer", entity_id=customer.id)
    db.delete(customer)
    db.commit()


@router.get("/{customer_id}/payment-status", response_model=CustomerPaymentStatusResponse)
def customer_payment_status(
    customer_id: int,
    month: str | None = Query(None, description="Optional YYYY-MM filter; if set, only that month is returned"),
    db: Session = Depends(get_db),
    _: User = Depends(require_writer),
) -> CustomerPaymentStatusResponse:
    """Aggregate payment status across all of a customer's policies.

    For each policy, compute month-by-month status. Mark policies as
    lapsed if arrears exceed the configured threshold (side effect).
    """
    # Note: this endpoint *mutates* (auto-lapse + notifications), so it
    # requires write privilege. Reading the customer alone is still
    # available to viewers via GET /customers/{id}.
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    target_month: date | None = None
    if month:
        try:
            target_month = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    today = date.today()
    policies = db.query(Policy).filter(Policy.customer_id == customer_id).all()
    policy_results: list[PolicyPaymentStatus] = []
    overall_overdue = False
    overall_unpaid = False

    for policy in policies:
        payments = db.query(Payment).filter(Payment.policy_id == policy.id).all()
        months, arrears, outstanding = billing.compute_policy_status(policy, payments, as_of=today)

        # Filter to requested month if specified
        if target_month is not None:
            wanted = billing.month_key(target_month)
            months = [m for m in months if billing.month_key(m.month_start) == wanted]

        month_payloads = [
            MonthPaymentStatus(
                month=billing.month_key(m.month_start),
                expected_amount=m.expected,
                paid_amount=m.paid,
                status=m.status,
            )
            for m in months
        ]

        # Auto-lapse side effect
        if billing.should_lapse(policy, arrears):
            policy.status = PolicyStatus.lapsed
            notify_policy_lapsed(db, customer_id=customer.id, policy_id=policy.id)
            log_action(db, actor="system", action="LAPSE_POLICY",
                       entity_type="policy", entity_id=policy.id,
                       details={"arrears": arrears})

        policy_results.append(
            PolicyPaymentStatus(
                policy_id=policy.id,
                status=policy.status.value,
                months_in_arrears=arrears,
                total_outstanding=outstanding,
                months=month_payloads,
            )
        )

        if arrears > 0:
            overall_overdue = True
        if any(m.status in (billing.STATUS_NOT_PAID, billing.STATUS_PARTIAL) for m in months):
            overall_unpaid = True

    # If a customer has any lapsed policies, mark customer lapsed.
    if policies and all(p.status == PolicyStatus.lapsed for p in policies):
        customer.status = CustomerStatus.lapsed

    db.commit()

    overall = billing.STATUS_PAID
    if overall_overdue:
        overall = billing.STATUS_OVERDUE
    elif overall_unpaid:
        overall = billing.STATUS_NOT_PAID

    return CustomerPaymentStatusResponse(
        customer_id=customer.id,
        overall_status=overall,
        policies=policy_results,
    )
