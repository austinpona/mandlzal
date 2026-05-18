"""Payment record - a money movement against a policy (and optional member)."""
import enum
from datetime import datetime, date
from sqlalchemy import Column, Integer, DateTime, Date, Enum, Numeric, ForeignKey, String
from sqlalchemy.orm import relationship

from app.database import Base


class PaymentMethod(str, enum.Enum):
    debit_order = "debit_order"
    cash = "cash"
    eft = "eft"


class PaymentStatus(str, enum.Enum):
    paid = "paid"
    pending = "pending"
    failed = "failed"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id = Column(Integer, ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="SET NULL"), nullable=True, index=True)
    field_submission_id = Column(
        Integer,
        ForeignKey("field_submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    amount_paid = Column(Numeric(12, 2), nullable=False)
    payment_date = Column(Date, nullable=False, default=date.today, index=True)
    payment_method = Column(Enum(PaymentMethod), default=PaymentMethod.debit_order, nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.paid, nullable=False)
    reference = Column(String(128), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    customer = relationship("Customer", back_populates="payments")
    policy = relationship("Policy", back_populates="payments")
    member = relationship("Member", back_populates="payments")
