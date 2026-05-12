"""Group scheme member - belongs to a policy.

For group schemes, a single policy covers multiple members. Payments may
optionally reference a member to track per-member contributions.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, Enum, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from app.database import Base


class MemberStatus(str, enum.Enum):
    active = "active"
    lapsed = "lapsed"
    removed = "removed"


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    title = Column(String(8), nullable=True)            # Mr / Mrs / Ms / Dr
    first_names = Column(String(120), nullable=True)
    surname = Column(String(120), nullable=True)
    id_number = Column(String(64), nullable=True)
    relationship_to_holder = Column(String(64), nullable=True)
    # Demographics & contact captured during the cover-signup wizard.
    gender = Column(String(16), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(80), nullable=True)
    email = Column(String(255), nullable=True)
    cellphone = Column(String(32), nullable=True)
    country_of_birth = Column(String(80), nullable=True)
    contribution_amount = Column(Numeric(12, 2), nullable=True)
    status = Column(Enum(MemberStatus), default=MemberStatus.active, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    policy = relationship("Policy", back_populates="members")
    payments = relationship("Payment", back_populates="member")
