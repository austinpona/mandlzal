"""Idempotent batch processor for field-capture submissions."""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.device import Device
from app.models.field_submission import FieldSubmission, FieldSubmissionStatus
from app.models.notification import Notification
from app.models.payment import Payment, PaymentStatus
from app.models.policy import Policy
from app.schemas.cover import CoverSignupRequest
from app.schemas.field import (
    FieldSignupIn,
    FieldSubmissionRequest,
    FieldSubmissionResponse,
    FieldSubmissionResult,
)
from app.services.cover_signup import perform_cover_signup
from app.services.photo_storage import resolve_photo_path


def _to_cover_signup(signup: FieldSignupIn) -> CoverSignupRequest:
    return CoverSignupRequest(
        cover_plan_id=signup.cover_plan_id,
        holder=signup.holder.model_dump(),
        dependents=[d.model_dump() for d in signup.dependents],
        beneficiaries=[b.model_dump() for b in signup.beneficiaries],
    )


def _error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


def _previous_response(existing: FieldSubmission) -> FieldSubmissionResponse | None:
    if isinstance(existing.raw_payload, dict):
        response = existing.raw_payload.get("response")
        if isinstance(response, dict):
            return FieldSubmissionResponse.model_validate(response)
    return None


def _resolve_photo_or_raise(id_photo_id: str | None) -> str | None:
    if not id_photo_id:
        return None
    path = resolve_photo_path(id_photo_id)
    if path is None:
        raise HTTPException(status_code=400, detail=f"Unknown id_photo_id: {id_photo_id}")
    return path


def _apply_photo(db: Session, customer_id: int, path: str | None) -> None:
    if path is None:
        return
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=500, detail="Created customer disappeared")
    customer.id_photo_path = path
    db.add(customer)


def _record_first_payment(
    db: Session,
    *,
    signup: FieldSignupIn,
    field_submission_id: int,
    customer_id: int,
    policy_id: int,
) -> int | None:
    if signup.first_payment is None:
        return None
    first = signup.first_payment
    payment = Payment(
        customer_id=customer_id,
        policy_id=policy_id,
        amount_paid=first.amount,
        payment_date=first.payment_date or date.today(),
        payment_method=first.method,
        status=PaymentStatus.paid,
        reference=first.reference,
        field_submission_id=field_submission_id,
    )
    db.add(payment)
    db.flush()
    return payment.id


def _queue_email_receipt(
    db: Session,
    *,
    signup: FieldSignupIn,
    customer_id: int,
    policy_id: int,
    payment_id: int | None,
) -> None:
    if not signup.email_receipt_requested or not signup.holder.email or payment_id is None:
        return
    db.add(Notification(
        customer_id=customer_id,
        policy_id=policy_id,
        type="EMAIL_RECEIPT",
        message=f"Receipt for policy {policy_id}, payment {payment_id}",
    ))


def process_submission(
    db: Session,
    *,
    device: Device,
    request: FieldSubmissionRequest,
) -> FieldSubmissionResponse:
    """Process a batch once per `(device_id, client_uuid)`."""
    existing = (
        db.query(FieldSubmission)
        .filter(
            FieldSubmission.device_id == device.id,
            FieldSubmission.client_uuid == request.client_uuid,
        )
        .first()
    )
    if existing is not None:
        previous = _previous_response(existing)
        if previous is not None:
            return previous

    fs = FieldSubmission(
        device_id=device.id,
        client_uuid=request.client_uuid,
        signups_count=len(request.signups),
        payments_count=0,
        status=FieldSubmissionStatus.failed,
        raw_payload={"request": request.model_dump(mode="json")},
    )
    db.add(fs)
    db.flush()
    db.commit()
    db.refresh(fs)

    results: list[FieldSubmissionResult] = []
    payments_count = 0

    for signup in request.signups:
        try:
            photo_path = _resolve_photo_or_raise(signup.id_photo_id)
            cover_response = perform_cover_signup(
                db,
                _to_cover_signup(signup),
                actor=f"device:{device.id}:{device.name}",
            )
            policy = db.get(Policy, cover_response.policy_id)
            if policy is None:
                raise HTTPException(status_code=500, detail="Created policy disappeared")
            policy.field_submission_id = fs.id
            db.add(policy)
            _apply_photo(db, cover_response.customer_id, photo_path)
            payment_id = _record_first_payment(
                db,
                signup=signup,
                field_submission_id=fs.id,
                customer_id=cover_response.customer_id,
                policy_id=cover_response.policy_id,
            )
            if payment_id is not None:
                payments_count += 1
            _queue_email_receipt(
                db,
                signup=signup,
                customer_id=cover_response.customer_id,
                policy_id=cover_response.policy_id,
                payment_id=payment_id,
            )
            db.commit()
            results.append(FieldSubmissionResult(
                local_id=signup.local_id,
                status="ok",
                customer_id=cover_response.customer_id,
                policy_id=cover_response.policy_id,
                payment_id=payment_id,
            ))
        except Exception as exc:  # noqa: BLE001 - batch returns per-row failures
            db.rollback()
            fs = db.get(FieldSubmission, fs.id)
            results.append(FieldSubmissionResult(
                local_id=signup.local_id,
                status="error",
                error=_error_detail(exc),
            ))

    ok_count = sum(1 for r in results if r.status == "ok")
    if ok_count == len(results):
        status = FieldSubmissionStatus.processed
        error_message = None
    elif ok_count:
        status = FieldSubmissionStatus.partial
        error_message = "Some signups failed"
    else:
        status = FieldSubmissionStatus.failed
        error_message = "; ".join(r.error or "unknown error" for r in results)

    response = FieldSubmissionResponse(field_submission_id=fs.id, results=results)
    fs.signups_count = len(request.signups)
    fs.payments_count = payments_count
    fs.status = status
    fs.error_message = error_message
    fs.raw_payload = {
        "request": request.model_dump(mode="json"),
        "response": response.model_dump(mode="json"),
    }
    db.add(fs)
    db.commit()
    return response
