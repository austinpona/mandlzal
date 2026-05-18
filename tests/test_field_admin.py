"""Tests for admin-side field device management."""
from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus


def test_admin_generates_enrollment_code(auth_client, db):
    resp = auth_client.post("/admin/field/enrollment-codes", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["code"]) == 6
    assert body["expires_at"]
    row = db.query(DeviceEnrollmentCode).filter_by(code=body["code"]).one()
    assert row.consumed_at is None


def test_admin_lists_devices(auth_client, db):
    db.add(Device(name="Phone-A", token_hash="x", status=DeviceStatus.active))
    db.add(Device(name="Phone-B", token_hash="y", status=DeviceStatus.revoked))
    db.commit()
    resp = auth_client.get("/admin/field/devices")
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()["devices"]}
    assert names == {"Phone-A", "Phone-B"}


def test_admin_revokes_device(auth_client, db):
    device = Device(name="Phone-X", token_hash="x", status=DeviceStatus.active)
    db.add(device)
    db.commit()
    db.refresh(device)
    resp = auth_client.post(f"/admin/field/devices/{device.id}/revoke")
    assert resp.status_code == 200
    db.refresh(device)
    assert device.status == DeviceStatus.revoked


def test_admin_endpoints_require_auth_in_production(client, monkeypatch):
    monkeypatch.setattr("app.api.field_admin.settings.PRODUCTION", True)
    resp = client.post("/admin/field/enrollment-codes")
    assert resp.status_code in (401, 403)
