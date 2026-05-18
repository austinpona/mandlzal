"""Server-side PDF receipt rendering for synced field signups."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.config import settings
from app.models.cover_plan import CoverPlan
from app.models.customer import Customer
from app.models.member import Member
from app.models.payment import Payment
from app.models.policy import Policy


_templates = Path(__file__).resolve().parents[1] / "templates" / "receipts"
_env = Environment(
    loader=FileSystemLoader(str(_templates)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _money(value: Any) -> str:
    return f"{value:.2f}"


def build_receipt_data(db: Session, *, payment_id: int, device_name: str | None = None) -> dict[str, Any]:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    policy = db.get(Policy, payment.policy_id)
    customer = db.get(Customer, payment.customer_id)
    if policy is None or customer is None:
        raise HTTPException(status_code=500, detail="Receipt data is incomplete")
    plan = db.get(CoverPlan, policy.cover_plan_id) if policy.cover_plan_id else None
    dependents = db.query(Member).filter(Member.policy_id == policy.id).order_by(Member.id).all()
    threshold = policy.lapse_threshold_months or settings.LAPSE_THRESHOLD_MONTHS
    reference = payment.reference or f"MZ-{policy.id}-{payment.id}"

    return {
        "company_name": "Mandlzi",
        "title": "Funeral cover receipt",
        "reference": reference,
        "receipt_date": payment.payment_date.isoformat(),
        "holder_name": customer.full_name,
        "holder_id_number": customer.id_number,
        "plan_name": plan.cover_type if plan else "Funeral cover",
        "monthly_premium": _money(policy.premium_amount),
        "amount_paid": _money(payment.amount_paid),
        "payment_method": payment.payment_method.value if hasattr(payment.payment_method, "value") else str(payment.payment_method),
        "month_label": payment.payment_date.strftime("%B %Y"),
        "dependents_summary": (
            f"{len(dependents)} dependent(s): " + ", ".join(d.full_name for d in dependents)
            if dependents
            else "None"
        ),
        "coverage_start_iso": policy.start_date.isoformat() if policy.start_date else "",
        "lapse_threshold_months": threshold,
        "device_name": device_name or "-",
        "captured_at_iso": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy_id": policy.id,
    }


def _pdf_text(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _minimal_pdf(data: dict[str, Any]) -> bytes:
    lines = [
        "Mandlzi funeral cover receipt",
        f"Reference: {data.get('reference', '')}",
        f"Date: {data.get('receipt_date', '')}",
        f"Holder: {data.get('holder_name', '')}",
        f"ID number: {data.get('holder_id_number', '')}",
        f"Plan: {data.get('plan_name', '')} (R{data.get('monthly_premium', '')} monthly)",
        f"Amount paid: R{data.get('amount_paid', '')}",
        f"Payment method: {data.get('payment_method', '')}",
        f"Payment month: {data.get('month_label', '')}",
        f"Dependents: {data.get('dependents_summary', '')}",
        f"Policy ID: {data.get('policy_id', '')}",
        (
            f"Coverage active from {data.get('coverage_start_iso', '')}. "
            f"Cover lapses after {data.get('lapse_threshold_months', '')} missed payments."
        ),
        f"Device: {data.get('device_name', '')}",
        f"Captured: {data.get('captured_at_iso', '')}",
    ]
    commands = ["BT", "/F1 12 Tf", "50 790 Td"]
    for idx, line in enumerate(lines):
        if idx:
            commands.append("0 -20 Td")
        commands.append(f"({_pdf_text(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 595] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_at = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def render_receipt_pdf(data: dict[str, Any]) -> bytes:
    html = _env.get_template("funeral_cover.html").render(**data)
    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except (ImportError, OSError):
        return _minimal_pdf(data)
