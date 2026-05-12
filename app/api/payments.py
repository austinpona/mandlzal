"""Payment endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_writer
from app.core.audit import log_action
from app.database import get_db
from app.models.customer import Customer
from app.models.member import Member
from app.models.payment import Payment
from app.models.policy import Policy
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentOut


router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_writer),
) -> Payment:
    customer = db.get(Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    policy = db.get(Policy, payload.policy_id)
    if not policy or policy.customer_id != customer.id:
        raise HTTPException(status_code=400, detail="Policy does not belong to customer")
    if payload.member_id is not None:
        member = db.get(Member, payload.member_id)
        if not member or member.policy_id != policy.id:
            raise HTTPException(status_code=400, detail="Member does not belong to policy")

    data = payload.model_dump()
    if data.get("payment_date") is None:
        data["payment_date"] = date.today()
    payment = Payment(**data)
    db.add(payment)
    db.flush()
    log_action(db, actor=current.email, action="CREATE_PAYMENT",
               entity_type="payment", entity_id=payment.id, details=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(payment)
    return payment


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Payment:
    p = db.get(Payment, payment_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return p


@router.get("", response_model=list[PaymentOut])
def list_payments(
    customer_id: int | None = None,
    policy_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Payment]:
    q = db.query(Payment)
    if customer_id is not None:
        q = q.filter(Payment.customer_id == customer_id)
    if policy_id is not None:
        q = q.filter(Payment.policy_id == policy_id)
    return q.order_by(Payment.payment_date.desc()).limit(500).all()
