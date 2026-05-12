"""Customer (policy holder) entity."""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, Enum  # noqa: F401
from sqlalchemy.orm import relationship

from app.database import Base


class CustomerStatus(str, enum.Enum):
    active = "active"
    lapsed = "lapsed"
    cancelled = "cancelled"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    # `full_name` is kept as the canonical display name for back-compat
    # with the older admin UI. New signups (via the funeral-cover wizard)
    # write the split fields below AND mirror them into `full_name`.
    full_name = Column(String(255), nullable=False)
    title = Column(String(8), nullable=True)
    first_names = Column(String(120), nullable=True)
    surname = Column(String(120), nullable=True)
    id_number = Column(String(64), unique=True, nullable=False, index=True)
    phone = Column(String(32), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    gender = Column(String(16), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(80), nullable=True)
    status = Column(Enum(CustomerStatus), default=CustomerStatus.active, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    policies = relationship("Policy", back_populates="customer", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="customer", cascade="all, delete-orphan")
