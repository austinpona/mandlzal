"""Tests for field-capture submission processing and endpoints."""
from decimal import Decimal

from app.core.device_auth import create_device_token, hash_device_jti
from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.customer import Customer
from app.models.device import Device, DeviceStatus
from app.models.field_submission import FieldSubmission, FieldSubmissionStatus
from app.models.payment import Payment
from app.models.policy import Policy
from app.schemas.field import (
    FieldBeneficiaryIn,
    FieldFirstPaymentIn,
    FieldHolderIn,
    FieldSignupIn,
    FieldSubmissionRequest,
)
from app.services.field_submission import process_submission


def _plan(db, *, cover_type="Me and My Family", max_dep=4):
    plan = CoverPlan(
        category=CoverCategory.me_and_family,
        cover_type=cover_type,
        monthly_premium=Decimal("360"),
        max_dependents=max_dep,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _device(db, *, jti="test-jti", status=DeviceStatus.active):
    device = Device(name="Phone-01", token_hash=hash_device_jti(jti), status=status)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _signup_payload(plan_id, *, local_id="1", id_num="ID1", first_payment=True):
    return FieldSignupIn(
        local_id=local_id,
        cover_plan_id=plan_id,
        holder=FieldHolderIn(first_names="A", surname="B", id_number=id_num, title="Mr"),
        beneficiaries=[
            FieldBeneficiaryIn(
                relationship_to_holder="Spouse",
                first_name="C",
                surname="D",
                share_pct=Decimal("100"),
            )
        ],
        first_payment=(
            FieldFirstPaymentIn(amount=Decimal("360"), method="cash")
            if first_payment
            else None
        ),
    )


def test_process_submission_happy_path(db):
    plan = _plan(db)
    device = _device(db)
    req = FieldSubmissionRequest(client_uuid="a" * 36, signups=[_signup_payload(plan.id)])
    resp = process_submission(db, device=device, request=req)

    assert resp.field_submission_id
    result = resp.results[0]
    assert result.status == "ok"
    assert result.customer_id and result.policy_id and result.payment_id
    fs = db.get(FieldSubmission, resp.field_submission_id)
    assert fs.status == FieldSubmissionStatus.processed
    assert fs.signups_count == 1
    assert fs.payments_count == 1
    assert db.get(Policy, result.policy_id).field_submission_id == fs.id
    assert db.get(Payment, result.payment_id).field_submission_id == fs.id


def test_process_submission_is_idempotent(db):
    plan = _plan(db)
    device = _device(db)
    req = FieldSubmissionRequest(client_uuid="b" * 36, signups=[_signup_payload(plan.id)])

    resp1 = process_submission(db, device=device, request=req)
    resp2 = process_submission(db, device=device, request=req)

    assert resp1 == resp2
    assert db.query(Customer).count() == 1
    assert db.query(Policy).count() == 1
    assert db.query(Payment).count() == 1


def test_process_submission_partial_failure(db):
    plan = _plan(db, max_dep=0)
    device = _device(db)
    req = FieldSubmissionRequest(
        client_uuid="c" * 36,
        signups=[
            _signup_payload(plan.id, local_id="ok", id_num="OK"),
            FieldSignupIn(
                local_id="bad",
                cover_plan_id=plan.id,
                holder=FieldHolderIn(first_names="A", surname="B", id_number="BAD", title="Mr"),
                dependents=[
                    {
                        "title": "Ms",
                        "first_names": "Too",
                        "surname": "Many",
                        "relationship_to_holder": "Child",
                    }
                ],
                beneficiaries=[
                    FieldBeneficiaryIn(
                        relationship_to_holder="Spouse",
                        first_name="C",
                        surname="D",
                        share_pct=Decimal("100"),
                    )
                ],
            ),
        ],
    )
    resp = process_submission(db, device=device, request=req)
    assert [r.status for r in resp.results] == ["ok", "error"]
    assert db.get(FieldSubmission, resp.field_submission_id).status == FieldSubmissionStatus.partial


def test_post_submissions_endpoint_and_get_by_uuid(client, db):
    plan = _plan(db)
    device = _device(db)
    token = create_device_token(device.id, name=device.name, jti="test-jti")
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "client_uuid": "d" * 36,
        "signups": [{
            "local_id": "1",
            "cover_plan_id": plan.id,
            "holder": {"title": "Mr", "first_names": "A", "surname": "B", "id_number": "X1"},
            "dependents": [],
            "beneficiaries": [{
                "relationship_to_holder": "Spouse",
                "first_name": "C",
                "surname": "D",
                "share_pct": "100",
            }],
            "first_payment": {"amount": "360", "method": "cash"},
        }],
    }
    resp = client.post("/api/field/submissions", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["results"][0]["status"] == "ok"

    retry = client.post("/api/field/submissions", json=body, headers=headers)
    assert retry.status_code == 200
    assert retry.json() == out

    fetched = client.get(f"/api/field/submissions/{body['client_uuid']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json() == out
