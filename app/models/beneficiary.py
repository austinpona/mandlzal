"""Beneficiary - who receives the payout when the policy claims.

Multiple beneficiaries per policy. Their `share_pct` values **must
sum to exactly 100** for the policy to be valid; this is enforced
in the signup service and re-checked on any later edit.
"""
from datetime import datetime
from sqlalchemy import Column, Date, Integer, String, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from app.database import Base


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Identification & contact (step 3 fields in the wizard).
    relationship_to_holder = Column(String(64), nullable=False)
    first_name = Column(String(120), nullable=False)
    surname = Column(String(120), nullable=False)
    cellphone = Column(String(32), nullable=True)
    country_of_birth = Column(String(80), nullable=True)
    # Percentage of the payout this beneficiary receives.
    # Stored as Numeric(5,2) so we can express e.g. 33.33 / 33.33 / 33.34.
    share_pct = Column(Numeric(5, 2), nullable=False)
    title = Column(String(8), nullable=True)
    gender = Column(String(16), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(80), nullable=True)
    email = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    policy = relationship("Policy", back_populates="beneficiaries")
