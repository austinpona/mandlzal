"""Policy endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_writer
from app.core.audit import log_action
from app.database import get_db
from app.models.cover_plan import CoverPlan, SchemeType
from app.models.customer import Customer
from app.models.policy import Policy
from app.models.user import User
from app.schemas.policy import PolicyCreate, PolicyOut, PolicyUpdate


router = APIRouter(prefix="/policies", tags=["policies"])


@router.post("", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_writer),
) -> Policy:
    if not db.get(Customer, payload.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    data = payload.model_dump()
    if data.get("start_date") is None:
        data["start_date"] = date.today()
    policy = Policy(**data)
    db.add(policy)
    db.flush()
    log_action(db, actor=current.email, action="CREATE_POLICY",
               entity_type="policy", entity_id=policy.id, details=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(policy)
    return policy


@router.get("", response_model=list[PolicyOut])
def list_policies(
    customer_id: int | None = Query(None, description="Filter to one customer"),
    scheme_type: SchemeType | None = Query(None, description="Filter to one scheme tab"),
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Policy]:
    q = db.query(Policy)
    if customer_id is not None:
        q = q.filter(Policy.customer_id == customer_id)
    if scheme_type is not None:
        q = q.join(CoverPlan, Policy.cover_plan_id == CoverPlan.id) \
             .filter(CoverPlan.scheme_type == scheme_type)
    return q.order_by(Policy.id).offset(skip).limit(limit).all()


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Policy:
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.patch("/{policy_id}", response_model=PolicyOut)
def update_policy(
    policy_id: int,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_writer),
) -> Policy:
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    updates = payload.model_dump(exclude_unset=True)
    for f, v in updates.items():
        setattr(policy, f, v)
    log_action(db, actor=current.email, action="UPDATE_POLICY",
               entity_type="policy", entity_id=policy.id, details=updates)
    db.commit()
    db.refresh(policy)
    return policy
