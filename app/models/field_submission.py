"""Field-capture submission batches with device-scoped idempotency."""
import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from app.database import Base


class FieldSubmissionStatus(str, enum.Enum):
    processed = "processed"
    partial = "partial"
    failed = "failed"


class FieldSubmission(Base):
    __tablename__ = "field_submissions"
    __table_args__ = (
        UniqueConstraint("device_id", "client_uuid", name="uq_field_submission_dedupe"),
    )

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    client_uuid = Column(String(36), nullable=False, index=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    signups_count = Column(Integer, default=0, nullable=False)
    payments_count = Column(Integer, default=0, nullable=False)
    status = Column(Enum(FieldSubmissionStatus), default=FieldSubmissionStatus.processed, nullable=False)
    error_message = Column(Text, nullable=True)
    raw_payload = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
