"""Policy entity - an active subscription owned by a customer."""
import enum
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, Date, Enum, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class PolicyType(str, enum.Enum):
    individual = "individual"
    group_scheme = "group_scheme"


class PolicyStatus(str, enum.Enum):
    active = "active"
    lapsed = "lapsed"
    cancelled = "cancelled"


class BillingCycle(str, enum.Enum):
    monthly = "monthly"


class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_type = Column(Enum(PolicyType), default=PolicyType.individual, nullable=False)
    premium_amount = Column(Numeric(12, 2), nullable=False)
    billing_cycle = Column(Enum(BillingCycle), default=BillingCycle.monthly, nullable=False)
    start_date = Column(Date, nullable=False, default=date.today)
    status = Column(Enum(PolicyStatus), default=PolicyStatus.active, nullable=False)

    # Per-policy overridable business rules
    grace_period_days = Column(Integer, nullable=True)
    lapse_threshold_months = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Snapshot of the cover plan at the moment of signup. Nullable so
    # legacy/admin-created policies (no plan) continue to work.
    cover_plan_id = Column(Integer, ForeignKey("cover_plans.id", ondelete="SET NULL"), nullable=True, index=True)

    customer = relationship("Customer", back_populates="policies")
    payments = relationship("Payment", back_populates="policy", cascade="all, delete-orphan")
    members = relationship("Member", back_populates="policy", cascade="all, delete-orphan")
    beneficiaries = relationship("Beneficiary", back_populates="policy", cascade="all, delete-orphan")
    cover_plan = relationship("CoverPlan")
