"""End-to-end test of the field-capture backend flow, no frontend."""
import io
from decimal import Decimal

from PIL import Image

from app.models.cover_plan import CoverCategory, CoverPlan


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "blue").save(buf, format="JPEG")
    return buf.getvalue()


def test_full_field_happy_path(client, auth_client, db, tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    plan = CoverPlan(
        category=CoverCategory.me_and_family,
        cover_type="Family",
        monthly_premium=Decimal("360"),
        max_dependents=4,
        is_active=True,
    )
    db.add(plan)
    db.commit()

    code_resp = auth_client.post("/admin/field/enrollment-codes")
    assert code_resp.status_code == 200, code_resp.text
    code = code_resp.json()["code"]

    enroll = client.post("/api/field/enroll", json={"code": code, "name": "Phone-01"})
    assert enroll.status_code == 200, enroll.text
    jwt = enroll.json()["device_jwt"]
    device_id = enroll.json()["device_id"]
    device_headers = {"Authorization": f"Bearer {jwt}"}

    plans = client.get("/api/field/cover-plans", headers=device_headers)
    assert plans.status_code == 200
    assert plans.json()["plans"][0]["cover_type"] == "Family"

    photo = client.post(
        "/api/field/photos",
        headers=device_headers,
        files={"file": ("id.jpg", _jpeg(), "image/jpeg")},
    )
    assert photo.status_code == 200, photo.text

    body = {
        "client_uuid": "1" * 36,
        "signups": [{
            "local_id": "1",
            "cover_plan_id": plan.id,
            "holder": {
                "title": "Mr",
                "first_names": "John",
                "surname": "Smith",
                "id_number": "9001015800086",
                "email": "john@example.com",
            },
            "id_photo_id": photo.json()["id_photo_id"],
            "dependents": [{
                "title": "Mrs",
                "first_names": "Jane",
                "surname": "Smith",
                "relationship_to_holder": "Spouse",
            }],
            "beneficiaries": [{
                "relationship_to_holder": "Daughter",
                "first_name": "Jill",
                "surname": "Smith",
                "share_pct": "100",
            }],
            "first_payment": {"amount": "360", "method": "cash", "reference": "FLD-001"},
            "email_receipt_requested": True,
        }],
    }
    submit = client.post("/api/field/submissions", json=body, headers=device_headers)
    assert submit.status_code == 200, submit.text
    out = submit.json()
    assert out["results"][0]["status"] == "ok"
    assert out["results"][0]["policy_id"]

    retry = client.post("/api/field/submissions", json=body, headers=device_headers)
    assert retry.status_code == 200
    assert retry.json() == out

    fetched = client.get(f"/api/field/submissions/{body['client_uuid']}", headers=device_headers)
    assert fetched.status_code == 200
    assert fetched.json() == out

    revoke = auth_client.post(f"/admin/field/devices/{device_id}/revoke")
    assert revoke.status_code == 200, revoke.text

    after = client.get("/api/field/cover-plans", headers=device_headers)
    assert after.status_code == 401
    assert after.json()["detail"] == {"code": "DEVICE_REVOKED"}
