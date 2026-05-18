"""Device-facing field-capture endpoints."""
from __future__ import annotations

import secrets
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.device_auth import create_device_token, get_current_device, hash_device_jti, new_device_jti
from app.database import get_db
from app.models.cover_plan import CoverPlan
from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus
from app.models.field_submission import FieldSubmission
from app.schemas.field import (
    FieldCoverPlanOut,
    FieldCoverPlansResponse,
    FieldEnrollRequest,
    FieldEnrollResponse,
    FieldPhotoUploadResponse,
    FieldSubmissionRequest,
    FieldSubmissionResponse,
)
from app.services.field_submission import process_submission
from app.services.photo_storage import get_photo_storage


router = APIRouter(prefix="/api/field", tags=["field"])

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_MAX_PHOTO_BYTES = 5 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {"image/jpeg": "jpg", "image/png": "png"}


def _generate_enrollment_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


@router.post("/enroll", response_model=FieldEnrollResponse)
def enroll_device(
    payload: FieldEnrollRequest,
    db: Session = Depends(get_db),
) -> FieldEnrollResponse:
    code = payload.code.strip().upper()
    row = (
        db.query(DeviceEnrollmentCode)
        .filter(DeviceEnrollmentCode.code == code)
        .first()
    )
    if row is None or row.consumed_at is not None or row.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired enrollment code")

    jti = new_device_jti()
    device = Device(
        name=payload.name.strip(),
        token_hash=hash_device_jti(jti),
        status=DeviceStatus.active,
    )
    db.add(device)
    db.flush()
    row.consumed_at = datetime.utcnow()
    row.consumed_by_device_id = device.id
    db.add(row)
    db.commit()
    token = create_device_token(device.id, name=device.name, jti=jti)
    return FieldEnrollResponse(device_id=device.id, name=device.name, device_jwt=token)


@router.get("/cover-plans", response_model=FieldCoverPlansResponse)
def list_field_cover_plans(
    db: Session = Depends(get_db),
    _: Device = Depends(get_current_device),
) -> FieldCoverPlansResponse:
    plans = (
        db.query(CoverPlan)
        .filter(CoverPlan.is_active.is_(True))
        .order_by(CoverPlan.category, CoverPlan.monthly_premium)
        .all()
    )
    return FieldCoverPlansResponse(
        plans=[FieldCoverPlanOut.model_validate(p) for p in plans],
    )


def _validate_image(blob: bytes, content_type: str | None) -> str:
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG and PNG images are allowed")
    if len(blob) > _MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo must be 5MB or smaller")
    try:
        with Image.open(BytesIO(blob)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image") from exc
    return _ALLOWED_CONTENT_TYPES[content_type]


@router.post("/photos", response_model=FieldPhotoUploadResponse)
async def upload_field_photo(
    file: UploadFile = File(...),
    _: Device = Depends(get_current_device),
) -> FieldPhotoUploadResponse:
    blob = await file.read()
    ext = _validate_image(blob, file.content_type)
    path = get_photo_storage().save(blob, ext=ext)
    return FieldPhotoUploadResponse(id_photo_id=path, path=path)


@router.post("/submissions", response_model=FieldSubmissionResponse)
def submit_field_submission(
    payload: FieldSubmissionRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> FieldSubmissionResponse:
    return process_submission(db, device=device, request=payload)


@router.get("/submissions/{client_uuid}", response_model=FieldSubmissionResponse)
def get_field_submission(
    client_uuid: str,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> FieldSubmissionResponse:
    row = (
        db.query(FieldSubmission)
        .filter(
            FieldSubmission.device_id == device.id,
            FieldSubmission.client_uuid == client_uuid,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if not isinstance(row.raw_payload, dict) or "response" not in row.raw_payload:
        raise HTTPException(status_code=500, detail="Submission response is unavailable")
    return FieldSubmissionResponse.model_validate(row.raw_payload["response"])
