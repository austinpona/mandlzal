"""Admin endpoints for managing field devices and enrollment codes."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.api.field import _generate_enrollment_code
from app.config import settings
from app.core.security import hash_password
from app.database import get_db
from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus
from app.models.user import Role, User, role_at_least
from app.schemas.field import DeviceOut, DevicesResponse, EnrollmentCodeOut


router = APIRouter(prefix="/admin/field", tags=["field-admin"])


def _dev_field_admin(db: Session) -> User:
    user = db.query(User).filter(User.email == "field-preview@mandlzi.local").first()
    if user is not None:
        return user
    user = User(
        email="field-preview@mandlzi.local",
        hashed_password=hash_password("field-preview"),
        full_name="Field Preview",
        role=Role.admin,
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def field_admin_user(
    db: Session = Depends(get_db),
    current: User | None = Depends(get_current_user_optional),
) -> User:
    """Admin guard for field-device management.

    In local dev/preview, this can be used without logging in so the field PWA
    is easy to try. `PRODUCTION=1` always requires a real admin token.
    """
    if current is not None and role_at_least(current.role, Role.admin):
        return current
    if not settings.PRODUCTION and settings.DEV_FIELD_ADMIN_NO_LOGIN:
        return _dev_field_admin(db)
    if current is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    raise HTTPException(status_code=403, detail="Requires role admin or higher")


@router.post("/enrollment-codes", response_model=EnrollmentCodeOut)
def create_enrollment_code(
    db: Session = Depends(get_db),
    user: User = Depends(field_admin_user),
) -> EnrollmentCodeOut:
    for _ in range(8):
        code = _generate_enrollment_code()
        existing = db.query(DeviceEnrollmentCode).filter_by(code=code).first()
        if existing is None:
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate a unique code")

    expires_at = datetime.utcnow() + timedelta(hours=settings.ENROLLMENT_CODE_EXPIRES_HOURS)
    row = DeviceEnrollmentCode(
        code=code,
        created_by_user_id=user.id,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    return EnrollmentCodeOut(code=code, expires_at=expires_at)


@router.get("/devices", response_model=DevicesResponse)
def list_devices(
    db: Session = Depends(get_db),
    _: User = Depends(field_admin_user),
) -> DevicesResponse:
    devices = db.query(Device).order_by(Device.id).all()
    return DevicesResponse(devices=[
        DeviceOut(
            id=device.id,
            name=device.name,
            status=device.status.value if hasattr(device.status, "value") else str(device.status),
            enrolled_at=device.enrolled_at,
            last_seen_at=device.last_seen_at,
        )
        for device in devices
    ])


@router.post("/devices/{device_id}/revoke")
def revoke_device(
    device_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(field_admin_user),
) -> dict[str, object]:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.status = DeviceStatus.revoked
    db.add(device)
    db.commit()
    return {"ok": True, "device_id": device_id, "status": DeviceStatus.revoked.value}
