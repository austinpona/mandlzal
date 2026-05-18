"""JWT helpers and FastAPI dependency for field-capture devices."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password, verify_password
from app.database import get_db
from app.models.device import Device, DeviceStatus


device_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/field/enroll")


def new_device_jti() -> str:
    return secrets.token_urlsafe(32)


def hash_device_jti(jti: str) -> str:
    return hash_password(jti)


def create_device_token(device_id: int, *, name: str, jti: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    token_jti = jti or new_device_jti()
    payload: dict[str, Any] = {
        "sub": f"device:{device_id}",
        "type": "device",
        "name": name,
        "jti": token_jti,
        "iat": now,
        "exp": now + timedelta(days=settings.DEVICE_JWT_EXPIRES_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_device_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_TOKEN_EXPIRED"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_TOKEN_INVALID"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "device":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_TOKEN_INVALID"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.startswith("device:"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_TOKEN_INVALID"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not payload.get("jti"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_TOKEN_INVALID"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_device(
    token: str = Depends(device_oauth2_scheme),
    db: Session = Depends(get_db),
) -> Device:
    claims = decode_device_token(token)
    try:
        device_id = int(str(claims["sub"]).split(":", 1)[1])
    except (KeyError, ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_TOKEN_INVALID"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_NOT_FOUND"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if device.status == DeviceStatus.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_REVOKED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(str(claims["jti"]), device.token_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "DEVICE_TOKEN_REVOKED"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    device.last_seen_at = datetime.utcnow()
    db.add(device)
    db.commit()
    db.refresh(device)
    return device
