"""Device JWT helpers and token-type firewall tests."""
import pytest
from fastapi import HTTPException

from app.core.device_auth import create_device_token, decode_device_token, hash_device_jti, get_current_device
from app.core.security import create_access_token
from app.models.device import Device, DeviceStatus


def _make_device(db, *, name="Phone-01", status=DeviceStatus.active, jti="test-jti"):
    device = Device(name=name, token_hash=hash_device_jti(jti), status=status)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def test_create_and_decode_device_token(db):
    device = _make_device(db)
    token = create_device_token(device.id, name=device.name, jti="test-jti")
    claims = decode_device_token(token)
    assert claims["type"] == "device"
    assert claims["sub"] == f"device:{device.id}"
    assert claims["name"] == "Phone-01"
    assert claims["jti"] == "test-jti"


def test_decode_rejects_user_token():
    with pytest.raises(HTTPException) as exc:
        decode_device_token(create_access_token(subject=42))
    assert exc.value.status_code == 401


def test_get_current_device_happy_path(db):
    device = _make_device(db)
    token = create_device_token(device.id, name=device.name, jti="test-jti")
    resolved = get_current_device(token=token, db=db)
    assert resolved.id == device.id
    assert resolved.last_seen_at is not None


def test_get_current_device_rejects_revoked(db):
    device = _make_device(db, status=DeviceStatus.revoked)
    token = create_device_token(device.id, name=device.name, jti="test-jti")
    with pytest.raises(HTTPException) as exc:
        get_current_device(token=token, db=db)
    assert exc.value.status_code == 401
    assert exc.value.detail == {"code": "DEVICE_REVOKED"}


def test_get_current_user_rejects_device_token(client, db):
    device = _make_device(db)
    token = create_device_token(device.id, name=device.name, jti="test-jti")
    resp = client.get("/customers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
