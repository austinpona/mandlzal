"""Field-capture device enrollment and lifecycle models."""
import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class DeviceStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    token_hash = Column(String(128), nullable=False)
    status = Column(Enum(DeviceStatus), default=DeviceStatus.active, nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)


class DeviceEnrollmentCode(Base):
    __tablename__ = "device_enrollment_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(6), unique=True, nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    consumed_by_device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)

    consumed_by_device = relationship("Device")
