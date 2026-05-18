"""Tests for device enrollment and field utility endpoints."""
from datetime import datetime, timedelta
import io

from PIL import Image

from app.core.device_auth import decode_device_token
from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.device import DeviceEnrollmentCode
from app.models.user import User


def _admin_id(db):
    user = db.query(User).first()
    assert user is not None
    return user.id


def _make_code(db, *, user_id: int, code="ABC123", ttl_hours=24):
    row = DeviceEnrollmentCode(
        code=code,
        created_by_user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "blue").save(buf, format="JPEG")
    return buf.getvalue()


def test_enroll_consumes_code_and_returns_device_token(client, auth_client, db):
    code = _make_code(db, user_id=_admin_id(db), code="K3MZ9P")
    resp = client.post("/api/field/enroll", json={"code": "k3mz9p", "name": "Phone-01"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["device_id"]
    claims = decode_device_token(body["device_jwt"])
    assert claims["sub"] == f"device:{body['device_id']}"
    db.refresh(code)
    assert code.consumed_at is not None
    assert code.consumed_by_device_id == body["device_id"]


def test_enroll_rejects_reused_or_expired_code(client, auth_client, db):
    code = _make_code(db, user_id=_admin_id(db), code="USED11")
    first = client.post("/api/field/enroll", json={"code": code.code, "name": "Phone-01"})
    assert first.status_code == 200
    second = client.post("/api/field/enroll", json={"code": code.code, "name": "Phone-02"})
    assert second.status_code == 400

    _make_code(db, user_id=_admin_id(db), code="OLD111", ttl_hours=-1)
    expired = client.post("/api/field/enroll", json={"code": "OLD111", "name": "Phone-03"})
    assert expired.status_code == 400


def test_field_cover_plans_requires_device_token_and_returns_active_plans(client, auth_client, db):
    plan = CoverPlan(
        category=CoverCategory.me,
        cover_type="Me",
        monthly_premium=120,
        max_dependents=0,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    code = _make_code(db, user_id=_admin_id(db), code="PLAN11")
    token = client.post("/api/field/enroll", json={"code": code.code, "name": "Phone"}).json()["device_jwt"]
    resp = client.get("/api/field/cover-plans", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["plans"][0]["cover_type"] == "Me"


def test_photo_upload_validates_and_stores_file(client, auth_client, db, monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    code = _make_code(db, user_id=_admin_id(db), code="PHOTO1")
    token = client.post("/api/field/enroll", json={"code": code.code, "name": "Phone"}).json()["device_jwt"]
    resp = client.post(
        "/api/field/photos",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("id.jpg", _jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id_photo_id"]
    assert body["id_photo_id"] == body["path"]
    assert (tmp_path / body["path"]).exists()

    bad = client.post(
        "/api/field/photos",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("id.txt", b"not an image", "text/plain")},
    )
    assert bad.status_code == 400
