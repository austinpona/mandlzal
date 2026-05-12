"""Audit log entry - records mutating actions for traceability."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor = Column(String(255), nullable=True)  # user email or "system"
    action = Column(String(64), nullable=False)  # e.g. CREATE_CUSTOMER
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)  # JSON-encoded payload
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
