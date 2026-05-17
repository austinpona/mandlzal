# Field Capture Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the backend half of the field-capture-app spec: data model (3 new tables + 8 additive columns), 5 endpoints under `/api/field/*`, photo storage adapter, device JWT with token-type firewall, server-side receipt PDF + email. End state: the backend serves the full field-capture flow and is exercisable end-to-end via curl/httpx with no frontend.

**Architecture:** Adds `devices`, `device_enrollment_codes`, `field_submissions` tables; additive columns on `customers`/`policies`/`payments`/`beneficiaries`; new module `app/api/field.py` with five endpoints behind a `get_current_device` dependency; a `PhotoStorage` adapter that writes to the local filesystem (swappable to S3 later via config). The existing `app/services/cover_signup.py` is reused unchanged for the per-signup work; a new `app/services/field_submission.py` wraps it with idempotency + photo + first-payment + email-queue. WeasyPrint renders the PDF receipt; emails go via the existing notification dispatcher.

**Tech Stack:** FastAPI 0.115+, SQLAlchemy 2.x, Alembic, Pydantic v2, python-jose (JWT), python-multipart (upload), WeasyPrint (PDF), Pillow (image validation), pytest + httpx.

**Spec:** [docs/superpowers/specs/2026-05-17-field-capture-app-design.md](../specs/2026-05-17-field-capture-app-design.md) (commit `995e2ee`).

---

## File Structure

**Files to create:**
- `app/models/device.py` — `Device`, `DeviceEnrollmentCode` SQLAlchemy models
- `app/models/field_submission.py` — `FieldSubmission` SQLAlchemy model
- `app/schemas/field.py` — Pydantic request/response models for `/api/field/*`
- `app/services/photo_storage.py` — `PhotoStorage` protocol + `FilesystemPhotoStorage` + factory
- `app/services/field_submission.py` — batch processor (idempotency wrapper around `cover_signup`)
- `app/services/receipt_pdf.py` — `render_receipt_pdf(submission_data) -> bytes`
- `app/templates/receipts/funeral_cover.html` — Jinja template for the receipt
- `app/core/device_auth.py` — `create_device_token`, `get_current_device` dependency
- `app/api/field.py` — the 5 endpoints (`enroll`, `cover-plans`, `photos`, `submissions` POST/GET)
- `app/api/field_admin.py` — admin endpoints to issue enrollment codes + revoke devices
- `alembic/versions/<auto>_field_capture.py` — single migration adding all new tables + additive columns
- `tests/test_field_enrollment.py`
- `tests/test_field_auth.py`
- `tests/test_field_photo_upload.py`
- `tests/test_field_submission.py`
- `tests/test_field_receipt_pdf.py`
- `tests/test_field_admin.py`

**Files to modify:**
- `requirements.txt` — add `weasyprint`, `Pillow`, `Jinja2`
- `app/config.py` — add `PHOTO_STORAGE_BACKEND`, `PHOTO_STORAGE_PATH`, `DEVICE_JWT_EXPIRES_DAYS`, `ENROLLMENT_CODE_EXPIRES_HOURS`
- `app/models/beneficiary.py` — add 5 columns (`title`, `gender`, `date_of_birth`, `nationality`, `email`)
- `app/models/customer.py` — add `id_photo_path` column
- `app/models/policy.py` — add `field_submission_id` FK column
- `app/models/payment.py` — add `field_submission_id` FK column
- `app/models/__init__.py` — import new models so Alembic autogenerate sees them
- `app/api/deps.py` — make `get_current_user` reject device tokens (token-type firewall)
- `app/schemas/cover.py` — extend `BeneficiaryIn`/`BeneficiaryOut` with the 5 new fields
- `app/services/cover_signup.py` — pass the new beneficiary fields through to the `Beneficiary` row
- `app/services/notification_providers.py` — add `EMAIL_RECEIPT` provider (or extend an existing email provider)
- `app/main.py` — register `field.router` and `field_admin.router`
- `.gitignore` — ignore `media/` so locally captured photos aren't committed

---

## Phase 1 — Foundation: dependencies, config, photo storage

### Task 1: Add backend dependencies and configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `app/config.py`

- [ ] **Step 1: Edit `requirements.txt` — append the three new deps**

Append these lines (preserve existing pins):

```
weasyprint>=62.3
Pillow>=10.4.0
Jinja2>=3.1.4
```

- [ ] **Step 2: Edit `app/config.py` — add four new settings**

Add inside the `Settings` class (after `LAPSE_THRESHOLD_MONTHS`):

```python
    # Field-capture app
    PHOTO_STORAGE_BACKEND: str = "filesystem"   # "filesystem" | "s3" (s3 placeholder for now)
    PHOTO_STORAGE_PATH: str = "./media"         # root for the filesystem adapter
    DEVICE_JWT_EXPIRES_DAYS: int = 180
    ENROLLMENT_CODE_EXPIRES_HOURS: int = 24
```

- [ ] **Step 3: Install and verify**

Run:
```
pip install -r requirements.txt
python -c "import weasyprint, PIL, jinja2; print('ok')"
```
Expected: `ok` (no ImportError). On Windows, WeasyPrint requires GTK runtime — if install fails, see https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows.

- [ ] **Step 4: Edit `.gitignore` — ignore the photo storage directory**

Append:

```
# Field-capture photo storage (local dev)
media/
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt app/config.py .gitignore
git commit -m "Add field-capture deps + settings (weasyprint, Pillow, Jinja2, storage config)"
```

---

### Task 2: Photo storage adapter

**Files:**
- Create: `app/services/photo_storage.py`
- Create: `tests/test_photo_storage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_photo_storage.py`:

```python
"""Tests for the filesystem-backed photo storage adapter."""
import os
from pathlib import Path

import pytest

from app.services.photo_storage import FilesystemPhotoStorage, get_photo_storage


def test_filesystem_save_writes_file_and_returns_path(tmp_path):
    storage = FilesystemPhotoStorage(root=tmp_path)
    blob = b"\xff\xd8\xff" + b"x" * 100   # JPEG magic + filler
    path = storage.save(blob, ext="jpg")
    assert path.startswith("id_photos/")
    assert path.endswith(".jpg")
    assert (tmp_path / path).read_bytes() == blob


def test_filesystem_load_returns_bytes(tmp_path):
    storage = FilesystemPhotoStorage(root=tmp_path)
    blob = b"hello"
    path = storage.save(blob, ext="jpg")
    assert storage.load(path) == blob


def test_filesystem_delete_removes_file(tmp_path):
    storage = FilesystemPhotoStorage(root=tmp_path)
    path = storage.save(b"x", ext="jpg")
    storage.delete(path)
    assert not (tmp_path / path).exists()


def test_get_photo_storage_returns_filesystem_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTO_STORAGE_BACKEND", "filesystem")
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    # Bust the lru_cache so we re-read settings
    from app.config import get_settings
    get_settings.cache_clear()
    storage = get_photo_storage()
    assert isinstance(storage, FilesystemPhotoStorage)


def test_get_photo_storage_raises_for_unknown_backend(monkeypatch):
    monkeypatch.setenv("PHOTO_STORAGE_BACKEND", "azure_blob")
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Unknown PHOTO_STORAGE_BACKEND"):
        get_photo_storage()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_photo_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.photo_storage`.

- [ ] **Step 3: Implement the adapter**

Create `app/services/photo_storage.py`:

```python
"""Pluggable photo storage. Today: filesystem. Tomorrow: S3 via config swap."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol


class PhotoStorage(Protocol):
    def save(self, blob: bytes, ext: str) -> str: ...
    def load(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...


class FilesystemPhotoStorage:
    """Store photos under <root>/id_photos/<uuid>.<ext>.

    `path` values returned and accepted by this class are relative to
    `root` so they remain portable if the storage root is moved.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        (self.root / "id_photos").mkdir(parents=True, exist_ok=True)

    def save(self, blob: bytes, ext: str) -> str:
        name = f"{uuid.uuid4()}.{ext.lstrip('.')}"
        rel = f"id_photos/{name}"
        (self.root / rel).write_bytes(blob)
        return rel

    def load(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def delete(self, path: str) -> None:
        p = self.root / path
        if p.exists():
            p.unlink()


def get_photo_storage() -> PhotoStorage:
    """Build the storage adapter based on `settings.PHOTO_STORAGE_BACKEND`.

    Reads via `get_settings()` (not the module-level `settings` import) so
    that tests using `monkeypatch.setenv(...) + get_settings.cache_clear()`
    see fresh values.
    """
    from app.config import get_settings
    s = get_settings()
    if s.PHOTO_STORAGE_BACKEND == "filesystem":
        return FilesystemPhotoStorage(root=s.PHOTO_STORAGE_PATH)
    raise ValueError(
        f"Unknown PHOTO_STORAGE_BACKEND: {s.PHOTO_STORAGE_BACKEND!r}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_photo_storage.py -v`
Expected: 5 passing.

- [ ] **Step 5: Commit**

```bash
git add app/services/photo_storage.py tests/test_photo_storage.py
git commit -m "Add filesystem-backed photo storage adapter (swappable for S3 later)"
```

---

## Phase 2 — Data model + Alembic migration

### Task 3: Device + DeviceEnrollmentCode models

**Files:**
- Create: `app/models/device.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_alembic.py` (after the existing tests):

```python
def test_device_model_imports_and_creates_table():
    from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus
    # Smoke: enum members exist
    assert DeviceStatus.active.value == "active"
    assert DeviceStatus.revoked.value == "revoked"
    # Tables registered with Base
    assert "devices" in Device.metadata.tables
    assert "device_enrollment_codes" in DeviceEnrollmentCode.metadata.tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_alembic.py::test_device_model_imports_and_creates_table -v`
Expected: FAIL — `ModuleNotFoundError: app.models.device`.

- [ ] **Step 3: Create the model file**

Create `app/models/device.py`:

```python
"""Field-capture device records.

A `Device` represents an enrolled field phone authenticated by a long-lived
JWT. A `DeviceEnrollmentCode` is a one-time pairing code generated by an
admin and exchanged for a device JWT via `POST /api/field/enroll`.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class DeviceStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    token_hash = Column(String(128), nullable=False)   # bcrypt(jti)
    status = Column(Enum(DeviceStatus), default=DeviceStatus.active, nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)


class DeviceEnrollmentCode(Base):
    __tablename__ = "device_enrollment_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(6), unique=True, nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    consumed_by_device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)

    consumed_by_device = relationship("Device")
```

- [ ] **Step 4: Register the model so SQLAlchemy/Alembic find it**

Edit `app/models/__init__.py` — add the import:

```python
from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus  # noqa: F401
```

(If `__init__.py` doesn't currently exist with imports, check the file and follow the existing pattern — every other model is imported somewhere via the existing app bootstrap. If `app/models/__init__.py` is empty or only has docstring, add the line above.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_alembic.py::test_device_model_imports_and_creates_table -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models/device.py app/models/__init__.py tests/test_alembic.py
git commit -m "Add Device + DeviceEnrollmentCode models"
```

---

### Task 4: FieldSubmission model

**Files:**
- Create: `app/models/field_submission.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_alembic.py`:

```python
def test_field_submission_model_imports():
    from app.models.field_submission import FieldSubmission, FieldSubmissionStatus
    assert FieldSubmissionStatus.processed.value == "processed"
    assert FieldSubmissionStatus.partial.value == "partial"
    assert FieldSubmissionStatus.failed.value == "failed"
    assert "field_submissions" in FieldSubmission.metadata.tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_alembic.py::test_field_submission_model_imports -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the model**

Create `app/models/field_submission.py`:

```python
"""A batch of signups (and optional first payments) submitted by a field
device. Idempotency key is `(device_id, client_uuid)`; retries return the
previously-stored result without re-processing.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from app.database import Base


class FieldSubmissionStatus(str, enum.Enum):
    processed = "processed"      # all signups in the batch succeeded
    partial = "partial"          # some signups succeeded, some failed
    failed = "failed"             # batch-level failure (e.g. malformed)


class FieldSubmission(Base):
    __tablename__ = "field_submissions"
    __table_args__ = (UniqueConstraint("device_id", "client_uuid", name="uq_field_submission_dedupe"),)

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    client_uuid = Column(String(36), nullable=False, index=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    signups_count = Column(Integer, default=0, nullable=False)
    payments_count = Column(Integer, default=0, nullable=False)
    status = Column(Enum(FieldSubmissionStatus), default=FieldSubmissionStatus.processed, nullable=False)
    error_message = Column(Text, nullable=True)
    # JSONB on Postgres, JSON on SQLite for tests
    raw_payload = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
```

- [ ] **Step 4: Register in `app/models/__init__.py`**

Add:
```python
from app.models.field_submission import FieldSubmission, FieldSubmissionStatus  # noqa: F401
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_alembic.py::test_field_submission_model_imports -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models/field_submission.py app/models/__init__.py tests/test_alembic.py
git commit -m "Add FieldSubmission model with (device_id, client_uuid) dedupe constraint"
```

---

### Task 5: Additive columns on existing models

**Files:**
- Modify: `app/models/beneficiary.py`
- Modify: `app/models/customer.py`
- Modify: `app/models/policy.py`
- Modify: `app/models/payment.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_alembic.py`:

```python
def test_existing_models_have_new_columns():
    from app.models.beneficiary import Beneficiary
    from app.models.customer import Customer
    from app.models.policy import Policy
    from app.models.payment import Payment

    bcols = {c.name for c in Beneficiary.__table__.columns}
    assert {"title", "gender", "date_of_birth", "nationality", "email"} <= bcols

    ccols = {c.name for c in Customer.__table__.columns}
    assert "id_photo_path" in ccols

    pcols = {c.name for c in Policy.__table__.columns}
    assert "field_submission_id" in pcols

    paycols = {c.name for c in Payment.__table__.columns}
    assert "field_submission_id" in paycols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_alembic.py::test_existing_models_have_new_columns -v`
Expected: FAIL — `AssertionError` (columns missing).

- [ ] **Step 3: Edit `app/models/beneficiary.py` — add 5 columns**

Inside the `Beneficiary` class, after `share_pct` and before `created_at`:

```python
    # Additive demographic fields to match the source sketches.
    # Captured by the field-capture wizard; nullable so legacy rows stay valid.
    title = Column(String(8), nullable=True)
    gender = Column(String(16), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(80), nullable=True)
    email = Column(String(255), nullable=True)
```

Also add `Date` to the existing `from sqlalchemy import ...` line at the top of the file (currently has `Numeric` but not `Date`).

- [ ] **Step 4: Edit `app/models/customer.py` — add `id_photo_path`**

Inside the `Customer` class, near the other identification fields:

```python
    # Filesystem path (under PHOTO_STORAGE_PATH) of the ID photo captured
    # at field signup. None for customers created outside the field flow.
    id_photo_path = Column(String(255), nullable=True)
```

- [ ] **Step 5: Edit `app/models/policy.py` — add `field_submission_id` FK**

Inside the `Policy` class, after `cover_plan_id`:

```python
    # If this policy was created by a field-capture submission, this FK
    # links to that submission for traceability. NULL for admin/legacy.
    field_submission_id = Column(
        Integer,
        ForeignKey("field_submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

- [ ] **Step 6: Edit `app/models/payment.py` — add `field_submission_id` FK**

Inside the `Payment` class, after `member_id`:

```python
    field_submission_id = Column(
        Integer,
        ForeignKey("field_submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_alembic.py::test_existing_models_have_new_columns -v`
Expected: PASS.

- [ ] **Step 8: Run full alembic suite to confirm nothing broke**

Run: `pytest tests/test_alembic.py -v`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add app/models/beneficiary.py app/models/customer.py app/models/policy.py app/models/payment.py tests/test_alembic.py
git commit -m "Add additive columns: Beneficiary demographics + id_photo_path + field_submission_id FKs"
```

---

### Task 6: Alembic migration for all new tables + columns

**Files:**
- Create: `alembic/versions/<auto>_field_capture.py`

- [ ] **Step 1: Generate the migration**

Run from repo root:
```
alembic revision --autogenerate -m "field capture: devices, enrollment codes, field_submissions + additive columns"
```

A new file appears in `alembic/versions/` — open it.

- [ ] **Step 2: Verify the generated migration**

Open the new file and confirm `upgrade()` does roughly:

```python
def upgrade() -> None:
    # New tables
    op.create_table("devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.Enum("active", "revoked", name="devicestatus"), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )
    op.create_table("device_enrollment_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_by_device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=True),
    )
    op.create_index("ix_device_enrollment_codes_code", "device_enrollment_codes", ["code"], unique=True)
    op.create_table("field_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("client_uuid", sa.String(36), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("signups_count", sa.Integer(), nullable=False),
        sa.Column("payments_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("processed", "partial", "failed", name="fieldsubmissionstatus"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("device_id", "client_uuid", name="uq_field_submission_dedupe"),
    )
    op.create_index("ix_field_submissions_device_id", "field_submissions", ["device_id"])
    op.create_index("ix_field_submissions_client_uuid", "field_submissions", ["client_uuid"])

    # Additive columns
    with op.batch_alter_table("beneficiaries") as b:
        b.add_column(sa.Column("title", sa.String(8), nullable=True))
        b.add_column(sa.Column("gender", sa.String(16), nullable=True))
        b.add_column(sa.Column("date_of_birth", sa.Date(), nullable=True))
        b.add_column(sa.Column("nationality", sa.String(80), nullable=True))
        b.add_column(sa.Column("email", sa.String(255), nullable=True))
    with op.batch_alter_table("customers") as c:
        c.add_column(sa.Column("id_photo_path", sa.String(255), nullable=True))
    with op.batch_alter_table("policies") as p:
        p.add_column(sa.Column("field_submission_id", sa.Integer(),
                               sa.ForeignKey("field_submissions.id", ondelete="SET NULL"),
                               nullable=True))
        p.create_index("ix_policies_field_submission_id", ["field_submission_id"])
    with op.batch_alter_table("payments") as p:
        p.add_column(sa.Column("field_submission_id", sa.Integer(),
                               sa.ForeignKey("field_submissions.id", ondelete="SET NULL"),
                               nullable=True))
        p.create_index("ix_payments_field_submission_id", ["field_submission_id"])
```

Autogenerate often forgets `batch_alter_table` on SQLite or generates raw `op.add_column` — rewrite the additive sections to use `batch_alter_table` as shown so the migration runs on SQLite (used in tests) AND Postgres. Rewrite `downgrade()` to mirror this exactly in reverse.

- [ ] **Step 3: Write the round-trip test**

Append to `tests/test_alembic.py`:

```python
def test_field_capture_migration_round_trip(tmp_path, monkeypatch):
    """The new field-capture migration upgrades and downgrades cleanly on SQLite."""
    from alembic import command
    from alembic.config import Config

    db_url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
```

- [ ] **Step 4: Run the migration test**

Run: `pytest tests/test_alembic.py::test_field_capture_migration_round_trip -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend test suite to confirm nothing existing broke**

Run: `pytest -x -q`
Expected: all green. (Pre-existing failing tests, if any, are out of scope — but note them.)

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/*field_capture*.py tests/test_alembic.py
git commit -m "Alembic migration: field-capture tables + additive columns (batch_alter for sqlite)"
```

---

## Phase 3 — Device authentication

### Task 7: Device JWT helpers + `get_current_device` dependency

**Files:**
- Create: `app/core/device_auth.py`
- Create: `tests/test_field_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_field_auth.py`:

```python
"""Device JWT helpers and the `get_current_device` dependency."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.device_auth import (
    create_device_token,
    decode_device_token,
    get_current_device,
)
from app.models.device import Device, DeviceStatus


def _make_device(db, name="Phone-01", status=DeviceStatus.active):
    d = Device(name=name, token_hash="bcrypt-placeholder", status=status)
    db.add(d); db.commit(); db.refresh(d)
    return d


def test_create_and_decode_device_token(db):
    device = _make_device(db)
    token = create_device_token(device.id, name=device.name)
    claims = decode_device_token(token)
    assert claims["type"] == "device"
    assert claims["sub"] == f"device:{device.id}"
    assert claims["name"] == "Phone-01"
    assert "jti" in claims
    assert "exp" in claims


def test_decode_rejects_user_token(db):
    """A user-issued JWT must not pass device decode (subject mismatch)."""
    from app.core.security import create_access_token
    user_token = create_access_token(subject=42)
    with pytest.raises(HTTPException) as exc:
        decode_device_token(user_token)
    assert exc.value.status_code == 401


def test_get_current_device_happy_path(db):
    device = _make_device(db)
    token = create_device_token(device.id, name=device.name)
    resolved = get_current_device(token=token, db=db)
    assert resolved.id == device.id


def test_get_current_device_rejects_revoked(db):
    device = _make_device(db, status=DeviceStatus.revoked)
    token = create_device_token(device.id, name=device.name)
    with pytest.raises(HTTPException) as exc:
        get_current_device(token=token, db=db)
    assert exc.value.status_code == 401
    assert exc.value.detail == {"code": "DEVICE_REVOKED"}


def test_get_current_device_updates_last_seen_at(db):
    device = _make_device(db)
    assert device.last_seen_at is None
    token = create_device_token(device.id, name=device.name)
    get_current_device(token=token, db=db)
    db.refresh(device)
    assert device.last_seen_at is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_field_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.device_auth`.

- [ ] **Step 3: Implement `app/core/device_auth.py`**

```python
"""Device JWT issue/decode + FastAPI dependency that resolves to a Device.

Device JWTs are a separate identity space from user JWTs:
- `sub` is `device:<id>` (user JWTs are `<int>`)
- `type` is `"device"` (user JWTs have no `type` claim)
- Long lifetime (180 days by default), revocable server-side

`get_current_user` is updated separately (Task 8) to reject `type=device`
tokens, completing the firewall.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.device import Device, DeviceStatus


_device_scheme = OAuth2PasswordBearer(tokenUrl="/api/field/enroll", auto_error=True)


def create_device_token(device_id: int, *, name: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": f"device:{device_id}",
        "type": "device",
        "name": name,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=settings.DEVICE_JWT_EXPIRES_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_device_token(token: str) -> dict[str, Any]:
    """Decode + validate a device JWT. Raises HTTPException(401) on failure."""
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate device credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise creds_exc
    if claims.get("type") != "device":
        raise creds_exc
    sub = claims.get("sub", "")
    if not isinstance(sub, str) or not sub.startswith("device:"):
        raise creds_exc
    return claims


def get_current_device(
    token: str = Depends(_device_scheme),
    db: Session = Depends(get_db),
) -> Device:
    claims = decode_device_token(token)
    device_id = int(claims["sub"].split(":", 1)[1])
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "DEVICE_UNKNOWN"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if device.status != DeviceStatus.active:
        raise HTTPException(
            status_code=401,
            detail={"code": "DEVICE_REVOKED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    device.last_seen_at = datetime.utcnow()
    db.commit()
    return device
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_field_auth.py -v`
Expected: 5 passing.

- [ ] **Step 5: Commit**

```bash
git add app/core/device_auth.py tests/test_field_auth.py
git commit -m "Add device JWT issue/decode + get_current_device dependency"
```

---

### Task 8: Token-type firewall on `get_current_user`

**Files:**
- Modify: `app/api/deps.py`
- Modify: `tests/test_field_auth.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_field_auth.py`:

```python
def test_get_current_user_rejects_device_token(db, client, auth_client):
    """A device JWT must not authenticate against user-protected admin routes."""
    # Create a device and mint a device token
    device = _make_device(db, name="Phone-99")
    device_token = create_device_token(device.id, name=device.name)

    # Hit any user-protected admin endpoint with the device token
    fresh_client = client  # unauthenticated
    fresh_client.headers.update({"Authorization": f"Bearer {device_token}"})
    resp = fresh_client.get("/customers")
    assert resp.status_code == 401, resp.text
```

(Adjust `/customers` if that path doesn't exist; pick any endpoint protected by `get_current_user` — `/dashboard`, `/policies`, etc.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_field_auth.py::test_get_current_user_rejects_device_token -v`
Expected: FAIL — the user dependency happily accepts the device token (the `sub` parses as `device:<id>` which `int()` rejects → already 401 in fact?). Verify the actual failure mode and adjust:
- If it already fails with 401, the firewall is implicit. Add a stronger assertion: `assert "device" not in resp.text.lower()` and check the JWT decoding explicitly rejects `type=device`.
- If it passes, proceed.

- [ ] **Step 3: Update `get_current_user` to explicitly reject device tokens**

Edit `app/api/deps.py`, replacing the body of `get_current_user`:

```python
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Resolve the authenticated `User` from a bearer JWT.

    Rejects device tokens (type=device) so a phone JWT can never reach
    admin/user routes. The complementary check (user JWT can't reach
    /api/field/*) lives in `app.core.device_auth.decode_device_token`.
    """
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") == "device":
            raise creds_exc
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise creds_exc
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise creds_exc
    return user
```

Also update `get_current_user_optional` similarly (just `return None` instead of raising).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_field_auth.py -v && pytest tests/test_rbac.py -v`
Expected: all green (RBAC suite still passes; new firewall test passes).

- [ ] **Step 5: Commit**

```bash
git add app/api/deps.py tests/test_field_auth.py
git commit -m "Token-type firewall: get_current_user rejects type=device tokens"
```

---

## Phase 4 — Enrollment endpoint

### Task 9: `POST /api/field/enroll`

**Files:**
- Create: `app/schemas/field.py`
- Create: `app/api/field.py`
- Create: `tests/test_field_enrollment.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_field_enrollment.py`:

```python
"""Tests for POST /api/field/enroll (one-time pairing code → device JWT).

Uses the `auth_client` fixture (from conftest.py) to seed a real user
that enrollment codes can reference via `created_by_user_id`.
"""
from datetime import datetime, timedelta

import pytest

from app.core.device_auth import decode_device_token
from app.models.device import Device, DeviceEnrollmentCode
from app.models.user import User


def _admin_user_id(db) -> int:
    """Return the id of the user registered by the `auth_client` fixture."""
    u = db.query(User).first()
    assert u is not None, "auth_client fixture should have registered a user"
    return u.id


def _make_code(db, *, user_id: int, code: str, ttl_hours: int = 24):
    row = DeviceEnrollmentCode(
        code=code,
        created_by_user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_enroll_happy_path(auth_client, client, db):
    """`auth_client` registers the user; `client` is the anonymous caller
    that exchanges the code (enrollment doesn't need user auth)."""
    code = _make_code(db, user_id=_admin_user_id(db), code="ABCDEF")

    resp = client.post("/api/field/enroll", json={"code": "ABCDEF", "name": "Phone-01"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Phone-01"
    assert "device_id" in body
    assert "device_jwt" in body

    # JWT decodes as a device token
    claims = decode_device_token(body["device_jwt"])
    assert claims["sub"] == f"device:{body['device_id']}"

    # Code marked consumed; device persisted
    db.refresh(code)
    assert code.consumed_at is not None
    assert code.consumed_by_device_id == body["device_id"]
    assert db.get(Device, body["device_id"]).name == "Phone-01"


def test_enroll_rejects_unknown_code(client):
    resp = client.post("/api/field/enroll", json={"code": "NOPE12", "name": "Phone"})
    assert resp.status_code == 400
    assert "code" in resp.json()["detail"].lower()


def test_enroll_rejects_expired_code(auth_client, client, db):
    row = DeviceEnrollmentCode(
        code="EXP123",
        created_by_user_id=_admin_user_id(db),
        expires_at=datetime.utcnow() - timedelta(hours=1),  # already expired
    )
    db.add(row); db.commit()
    resp = client.post("/api/field/enroll", json={"code": "EXP123", "name": "Phone"})
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_enroll_rejects_already_consumed_code(auth_client, client, db):
    _make_code(db, user_id=_admin_user_id(db), code="USED12")
    # First enroll succeeds
    r1 = client.post("/api/field/enroll", json={"code": "USED12", "name": "Phone-A"})
    assert r1.status_code == 200
    # Second enroll with same code rejected
    r2 = client.post("/api/field/enroll", json={"code": "USED12", "name": "Phone-B"})
    assert r2.status_code == 400
    body_lower = (r2.json()["detail"] or "").lower()
    assert "already" in body_lower or "consumed" in body_lower
```

Note: the `_register_user` flow above is best-effort — adjust to match how `tests/test_*.py` currently register users / get a user id. If tests already have a fixture for `admin_user_id`, use that. The point is each enrollment code needs `created_by_user_id` pointing at a real user row.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_field_enrollment.py -v`
Expected: FAIL — endpoint doesn't exist (404).

- [ ] **Step 3: Create Pydantic schemas**

Create `app/schemas/field.py`:

```python
"""Pydantic models for the `/api/field/*` endpoints."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ---------- /enroll ----------
class EnrollRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    name: str = Field(min_length=1, max_length=80)


class EnrollResponse(BaseModel):
    device_id: int
    name: str
    device_jwt: str


# ---------- /cover-plans ----------
class CoverPlanOut(BaseModel):
    id: int
    category: str
    cover_type: str
    monthly_premium: Decimal
    max_dependents: int
    description: str | None = None


class CoverPlansResponse(BaseModel):
    plans: list[CoverPlanOut]


# ---------- /photos ----------
class PhotoUploadResponse(BaseModel):
    id_photo_id: str
    path: str


# ---------- /submissions ----------
class FieldHolderIn(BaseModel):
    title: str | None = None
    first_names: str
    surname: str
    id_number: str
    date_of_birth: date | None = None
    gender: str | None = None
    nationality: str | None = None
    email: EmailStr | None = None
    cellphone: str | None = None
    country_of_birth: str | None = None


class FieldDependentIn(BaseModel):
    title: str | None = None
    first_names: str
    surname: str
    id_number: str | None = None
    relationship_to_holder: str
    date_of_birth: date | None = None
    gender: str | None = None
    nationality: str | None = None
    email: EmailStr | None = None
    cellphone: str | None = None
    country_of_birth: str | None = None


class FieldBeneficiaryIn(BaseModel):
    relationship_to_holder: str
    title: str | None = None
    first_name: str
    surname: str
    gender: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    email: EmailStr | None = None
    cellphone: str | None = None
    country_of_birth: str | None = None
    share_pct: Decimal


class FieldFirstPaymentIn(BaseModel):
    amount: Decimal
    method: Literal["cash", "eft", "debit_order"]
    reference: str | None = None
    payment_date: date | None = None


class FieldSignupIn(BaseModel):
    local_id: str
    cover_plan_id: int
    holder: FieldHolderIn
    id_photo_id: str | None = None
    dependents: list[FieldDependentIn] = []
    beneficiaries: list[FieldBeneficiaryIn] = []
    first_payment: FieldFirstPaymentIn | None = None
    email_receipt_requested: bool = False


class FieldSubmissionRequest(BaseModel):
    client_uuid: str = Field(min_length=36, max_length=36)
    signups: list[FieldSignupIn]


class FieldSignupResult(BaseModel):
    local_id: str
    status: Literal["ok", "error"]
    customer_id: int | None = None
    policy_id: int | None = None
    payment_id: int | None = None
    error: str | None = None


class FieldSubmissionResponse(BaseModel):
    field_submission_id: int
    results: list[FieldSignupResult]
```

- [ ] **Step 4: Create `app/api/field.py` with the enroll endpoint**

```python
"""Field-capture endpoints (device-authenticated, except /enroll)."""
from __future__ import annotations

import secrets
import string
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.device_auth import create_device_token, get_current_device
from app.core.security import hash_password   # reused for token_hash (bcrypt)
from app.database import get_db
from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus
from app.schemas.field import (
    EnrollRequest, EnrollResponse,
)


router = APIRouter(prefix="/api/field", tags=["field-capture"])


@router.post("/enroll", response_model=EnrollResponse)
def enroll_device(payload: EnrollRequest, db: Session = Depends(get_db)) -> EnrollResponse:
    code = (
        db.query(DeviceEnrollmentCode)
        .filter(DeviceEnrollmentCode.code == payload.code.upper())
        .first()
    )
    if code is None:
        raise HTTPException(status_code=400, detail="Enrollment code not found.")
    if code.consumed_at is not None:
        raise HTTPException(status_code=400, detail="Enrollment code already consumed.")
    if code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Enrollment code expired.")

    # Mint device + JWT
    device = Device(
        name=payload.name,
        token_hash="pending",   # filled in after we know the jti
        status=DeviceStatus.active,
    )
    db.add(device); db.flush()    # need device.id for the JWT
    token = create_device_token(device.id, name=device.name)
    # Store bcrypt(jti) so a leaked devices table doesn't leak active JWTs.
    from app.core.device_auth import decode_device_token
    jti = decode_device_token(token)["jti"]
    device.token_hash = hash_password(jti)

    code.consumed_at = datetime.utcnow()
    code.consumed_by_device_id = device.id
    db.commit(); db.refresh(device)

    return EnrollResponse(device_id=device.id, name=device.name, device_jwt=token)


def _generate_enrollment_code() -> str:
    """Six uppercase alphanumerics, avoiding ambiguous chars 0/O, 1/I."""
    alphabet = "".join(c for c in (string.ascii_uppercase + string.digits) if c not in "0O1I")
    return "".join(secrets.choice(alphabet) for _ in range(6))
```

- [ ] **Step 5: Register the router in `app/main.py`**

Inside `create_app()`, after the existing `app.include_router(...)` calls:

```python
    from app.api import field
    app.include_router(field.router)
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_field_enrollment.py -v`
Expected: all four PASS.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/field.py app/api/field.py app/main.py tests/test_field_enrollment.py
git commit -m "POST /api/field/enroll: one-time code -> device JWT"
```

---

## Phase 5 — Cover plans + photo upload

### Task 10: `GET /api/field/cover-plans`

**Files:**
- Modify: `app/api/field.py`
- Modify: `tests/test_field_enrollment.py` *(or new `tests/test_field_cover_plans.py`)*

- [ ] **Step 1: Write the failing test**

Create `tests/test_field_cover_plans.py`:

```python
"""Tests for GET /api/field/cover-plans."""
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.device_auth import create_device_token
from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.device import Device, DeviceStatus


def _device_client(client, db, name="Phone-01"):
    d = Device(name=name, token_hash="x", status=DeviceStatus.active)
    db.add(d); db.commit(); db.refresh(d)
    token = create_device_token(d.id, name=d.name)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, d


def test_cover_plans_returns_active_plans(client, db):
    db.add(CoverPlan(
        category=CoverCategory.me_and_family,
        cover_type="Me and My Family",
        monthly_premium=Decimal("360.00"),
        max_dependents=4,
        description="Main + 4 deps",
        is_active=True,
    ))
    db.add(CoverPlan(
        category=CoverCategory.me,
        cover_type="Me",
        monthly_premium=Decimal("120.00"),
        max_dependents=0,
        is_active=False,   # inactive — must be filtered out
    ))
    db.commit()

    c, _ = _device_client(client, db)
    resp = c.get("/api/field/cover-plans")
    assert resp.status_code == 200, resp.text
    plans = resp.json()["plans"]
    assert len(plans) == 1
    assert plans[0]["cover_type"] == "Me and My Family"
    assert plans[0]["monthly_premium"] == "360.00"
    assert plans[0]["max_dependents"] == 4


def test_cover_plans_requires_device_token(client):
    resp = client.get("/api/field/cover-plans")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_field_cover_plans.py -v`
Expected: FAIL — 404 (endpoint missing).

- [ ] **Step 3: Implement the endpoint**

Append to `app/api/field.py`:

```python
from app.models.cover_plan import CoverPlan
from app.schemas.field import CoverPlanOut, CoverPlansResponse


@router.get("/cover-plans", response_model=CoverPlansResponse)
def list_cover_plans(
    db: Session = Depends(get_db),
    _: Device = Depends(get_current_device),
) -> CoverPlansResponse:
    rows = db.query(CoverPlan).filter(CoverPlan.is_active.is_(True)).order_by(CoverPlan.id).all()
    return CoverPlansResponse(plans=[
        CoverPlanOut(
            id=r.id,
            category=r.category.value if hasattr(r.category, "value") else str(r.category),
            cover_type=r.cover_type,
            monthly_premium=r.monthly_premium,
            max_dependents=r.max_dependents,
            description=r.description,
        )
        for r in rows
    ])
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_field_cover_plans.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/field.py tests/test_field_cover_plans.py
git commit -m "GET /api/field/cover-plans: list active plans for device-authed clients"
```

---

### Task 11: `POST /api/field/photos`

**Files:**
- Modify: `app/api/field.py`
- Create: `tests/test_field_photo_upload.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_field_photo_upload.py`:

```python
"""Tests for POST /api/field/photos (multipart ID-photo upload)."""
import io

from PIL import Image

from app.core.device_auth import create_device_token
from app.models.device import Device, DeviceStatus


def _device_client(client, db):
    d = Device(name="Phone-01", token_hash="x", status=DeviceStatus.active)
    db.add(d); db.commit(); db.refresh(d)
    token = create_device_token(d.id, name=d.name)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _jpeg(size=(64, 64), color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def test_photo_upload_happy_path(client, db, tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    from app.config import get_settings; get_settings.cache_clear()

    c = _device_client(client, db)
    files = {"file": ("id.jpg", _jpeg(), "image/jpeg")}
    resp = c.post("/api/field/photos", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"].startswith("id_photos/")
    assert body["id_photo_id"]  # non-empty
    # File actually on disk
    assert (tmp_path / body["path"]).exists()


def test_photo_upload_rejects_bad_mime(client, db, tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    from app.config import get_settings; get_settings.cache_clear()

    c = _device_client(client, db)
    files = {"file": ("malicious.exe", b"MZ" + b"x" * 100, "application/octet-stream")}
    resp = c.post("/api/field/photos", files=files)
    assert resp.status_code == 400
    assert "mime" in resp.json()["detail"].lower() or "type" in resp.json()["detail"].lower()


def test_photo_upload_rejects_oversize(client, db, tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    from app.config import get_settings; get_settings.cache_clear()

    c = _device_client(client, db)
    big = b"\xff\xd8\xff" + b"x" * (6 * 1024 * 1024)   # 6 MB, over the 5 MB cap
    files = {"file": ("big.jpg", big, "image/jpeg")}
    resp = c.post("/api/field/photos", files=files)
    assert resp.status_code == 413


def test_photo_upload_requires_device(client):
    resp = client.post("/api/field/photos", files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_field_photo_upload.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement the endpoint**

Append to `app/api/field.py`:

```python
from fastapi import File, UploadFile
from app.schemas.field import PhotoUploadResponse
from app.services.photo_storage import get_photo_storage


_ALLOWED_PHOTO_MIME = {"image/jpeg", "image/png"}
_MAX_PHOTO_BYTES = 5 * 1024 * 1024   # 5 MB


@router.post("/photos", response_model=PhotoUploadResponse)
async def upload_photo(
    file: UploadFile = File(...),
    _: Device = Depends(get_current_device),
) -> PhotoUploadResponse:
    if file.content_type not in _ALLOWED_PHOTO_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported MIME type: {file.content_type!r}")
    blob = await file.read()
    if len(blob) > _MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 5 MB limit.")
    ext = "jpg" if file.content_type == "image/jpeg" else "png"
    path = get_photo_storage().save(blob, ext=ext)
    # `id_photo_id` is the filename without extension — opaque to clients.
    photo_id = path.rsplit("/", 1)[1].rsplit(".", 1)[0]
    return PhotoUploadResponse(id_photo_id=photo_id, path=path)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_field_photo_upload.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/field.py tests/test_field_photo_upload.py
git commit -m "POST /api/field/photos: multipart ID-photo upload via storage adapter"
```

---

## Phase 6 — Submission processing

### Task 12: Extend `cover_signup` to persist new beneficiary fields

**Files:**
- Modify: `app/services/cover_signup.py`
- Modify: `app/schemas/cover.py`
- Modify: `tests/test_cover_signup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cover_signup.py`:

```python
def test_cover_signup_persists_new_beneficiary_fields(db):
    """Beneficiary title/gender/DOB/nationality/email are stored."""
    from datetime import date
    from app.models.beneficiary import Beneficiary
    from app.models.cover_plan import CoverCategory, CoverPlan
    from app.services.cover_signup import perform_cover_signup
    from app.schemas.cover import CoverSignupRequest

    plan = CoverPlan(category=CoverCategory.me_and_family, cover_type="X",
                     monthly_premium="360", max_dependents=4, is_active=True)
    db.add(plan); db.commit(); db.refresh(plan)

    payload = CoverSignupRequest.model_validate({
        "cover_plan_id": plan.id,
        "holder": {"title": "Mr", "first_names": "A", "surname": "B", "id_number": "1"},
        "dependents": [],
        "beneficiaries": [{
            "relationship_to_holder": "Spouse",
            "title": "Mrs",
            "first_name": "C", "surname": "D",
            "gender": "F",
            "date_of_birth": "1990-01-02",
            "nationality": "ZA",
            "email": "c@example.com",
            "cellphone": "+27...", "country_of_birth": "ZA",
            "share_pct": "100",
        }],
    })
    resp = perform_cover_signup(db, payload)
    ben = db.query(Beneficiary).filter_by(policy_id=resp.policy_id).one()
    assert ben.title == "Mrs"
    assert ben.gender == "F"
    assert ben.date_of_birth == date(1990, 1, 2)
    assert ben.nationality == "ZA"
    assert ben.email == "c@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cover_signup.py::test_cover_signup_persists_new_beneficiary_fields -v`
Expected: FAIL — Pydantic schema rejects the new fields OR they're silently dropped.

- [ ] **Step 3: Extend `app/schemas/cover.py`**

Find the existing beneficiary input schema (likely named `BeneficiaryIn` or similar) and add the five new optional fields, mirroring the `FieldBeneficiaryIn` shape from `app/schemas/field.py`. If the file already defines an output schema, add the same fields there too.

- [ ] **Step 4: Update `perform_cover_signup` to pass the fields through**

Edit `app/services/cover_signup.py`. In the loop where `Beneficiary(...)` rows are created (around line 152), pass the five new fields:

```python
    for ben in payload.beneficiaries:
        db.add(Beneficiary(
            policy_id=policy.id,
            relationship_to_holder=ben.relationship_to_holder,
            first_name=ben.first_name,
            surname=ben.surname,
            cellphone=ben.cellphone,
            country_of_birth=ben.country_of_birth,
            share_pct=ben.share_pct,
            # new
            title=getattr(ben, "title", None),
            gender=getattr(ben, "gender", None),
            date_of_birth=getattr(ben, "date_of_birth", None),
            nationality=getattr(ben, "nationality", None),
            email=str(ben.email) if getattr(ben, "email", None) else None,
        ))
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_cover_signup.py -v`
Expected: all green (including the new test).

- [ ] **Step 6: Commit**

```bash
git add app/schemas/cover.py app/services/cover_signup.py tests/test_cover_signup.py
git commit -m "Persist new Beneficiary demographics in perform_cover_signup"
```

---

### Task 13: `field_submission` service — idempotent batch processor

**Files:**
- Create: `app/services/field_submission.py`
- Create: `tests/test_field_submission.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_field_submission.py`:

```python
"""Tests for the field-submission batch processor (idempotency + partials)."""
from decimal import Decimal

from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.customer import Customer
from app.models.device import Device, DeviceStatus
from app.models.field_submission import FieldSubmission, FieldSubmissionStatus
from app.models.payment import Payment
from app.models.policy import Policy
from app.schemas.field import (
    FieldBeneficiaryIn, FieldFirstPaymentIn, FieldHolderIn,
    FieldSignupIn, FieldSubmissionRequest,
)
from app.services.field_submission import process_submission


def _plan(db, *, cover_type="Me and My Family", max_dep=4):
    p = CoverPlan(category=CoverCategory.me_and_family, cover_type=cover_type,
                  monthly_premium=Decimal("360"), max_dependents=max_dep, is_active=True)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _device(db):
    d = Device(name="Phone-01", token_hash="x", status=DeviceStatus.active)
    db.add(d); db.commit(); db.refresh(d)
    return d


def _signup_payload(plan_id, *, local_id="1", id_num="ID1", first_payment=True):
    return FieldSignupIn(
        local_id=local_id,
        cover_plan_id=plan_id,
        holder=FieldHolderIn(first_names="A", surname="B", id_number=id_num, title="Mr"),
        beneficiaries=[FieldBeneficiaryIn(
            relationship_to_holder="Spouse", first_name="C", surname="D", share_pct=Decimal("100"),
        )],
        first_payment=(FieldFirstPaymentIn(amount=Decimal("360"), method="cash") if first_payment else None),
    )


def test_process_submission_happy_path(db):
    plan = _plan(db); device = _device(db)
    req = FieldSubmissionRequest(client_uuid="a" * 36, signups=[_signup_payload(plan.id)])
    resp = process_submission(db, device=device, request=req)

    assert resp.field_submission_id
    assert len(resp.results) == 1
    r = resp.results[0]
    assert r.status == "ok"
    assert r.customer_id and r.policy_id and r.payment_id

    # field_submission row created, policies stamped
    fs = db.get(FieldSubmission, resp.field_submission_id)
    assert fs.status == FieldSubmissionStatus.processed
    assert fs.signups_count == 1
    assert fs.payments_count == 1
    assert db.get(Policy, r.policy_id).field_submission_id == fs.id
    assert db.get(Payment, r.payment_id).field_submission_id == fs.id


def test_process_submission_is_idempotent(db):
    plan = _plan(db); device = _device(db)
    req = FieldSubmissionRequest(client_uuid="b" * 36, signups=[_signup_payload(plan.id)])

    resp1 = process_submission(db, device=device, request=req)
    resp2 = process_submission(db, device=device, request=req)

    assert resp1.field_submission_id == resp2.field_submission_id
    assert resp1.results[0].customer_id == resp2.results[0].customer_id
    assert resp1.results[0].policy_id == resp2.results[0].policy_id

    # Exactly one customer + one policy created total
    assert db.query(Customer).count() == 1
    assert db.query(Policy).count() == 1
    assert db.query(FieldSubmission).count() == 1


def test_process_submission_partial_failure(db):
    plan = _plan(db); device = _device(db)
    good = _signup_payload(plan.id, local_id="1", id_num="GOOD")
    bad = _signup_payload(plan.id, local_id="2", id_num="BAD")
    bad.beneficiaries[0].share_pct = Decimal("50")   # won't sum to 100 → cover_signup raises

    req = FieldSubmissionRequest(client_uuid="c" * 36, signups=[good, bad])
    resp = process_submission(db, device=device, request=req)

    assert resp.results[0].status == "ok"
    assert resp.results[1].status == "error"
    assert "100" in resp.results[1].error

    fs = db.get(FieldSubmission, resp.field_submission_id)
    assert fs.status == FieldSubmissionStatus.partial
    assert fs.signups_count == 1   # only the good one counted
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_field_submission.py -v`
Expected: FAIL — service doesn't exist.

- [ ] **Step 3: Implement the service**

Create `app/services/field_submission.py`:

```python
"""Idempotent batch processor for field-captured signups.

Wraps the existing `perform_cover_signup` with:
  - dedupe on (device_id, client_uuid)
  - per-signup error capture (one bad signup doesn't fail the batch)
  - first-payment recording linked to the new policy
  - field_submission_id stamped on every created Policy + Payment
  - email-receipt notification queued when opted in
"""
from __future__ import annotations

import json
from datetime import date as date_type, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.device import Device
from app.models.field_submission import FieldSubmission, FieldSubmissionStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy
from app.schemas.cover import CoverSignupRequest
from app.schemas.field import (
    FieldSignupIn, FieldSignupResult, FieldSubmissionRequest, FieldSubmissionResponse,
)
from app.services.cover_signup import perform_cover_signup
from app.services.photo_storage import get_photo_storage


def _cover_payload_from(signup: FieldSignupIn) -> CoverSignupRequest:
    """Map a FieldSignupIn into the existing CoverSignupRequest shape."""
    return CoverSignupRequest.model_validate({
        "cover_plan_id": signup.cover_plan_id,
        "holder": signup.holder.model_dump(),
        "dependents": [d.model_dump() for d in signup.dependents],
        "beneficiaries": [b.model_dump() for b in signup.beneficiaries],
    })


def _record_first_payment(db: Session, *, policy: Policy, signup: FieldSignupIn,
                          field_submission_id: int) -> Payment | None:
    if signup.first_payment is None:
        return None
    fp = signup.first_payment
    method = PaymentMethod(fp.method) if isinstance(fp.method, str) else fp.method
    pay = Payment(
        customer_id=policy.customer_id,
        policy_id=policy.id,
        amount_paid=fp.amount,
        payment_date=fp.payment_date or date_type.today(),
        payment_method=method,
        status=PaymentStatus.paid,
        reference=fp.reference,
        field_submission_id=field_submission_id,
    )
    db.add(pay); db.flush()
    return pay


def _store_id_photo_on_customer(db: Session, customer_id: int, id_photo_id: str | None) -> None:
    if not id_photo_id:
        return
    cust = db.get(Customer, customer_id)
    if cust is None or cust.id_photo_path:
        return
    # `id_photo_id` IS the filename UUID; the path is `id_photos/<id>.<ext>`.
    # Resolve actual extension by checking storage.
    storage = get_photo_storage()
    for ext in ("jpg", "png"):
        candidate = f"id_photos/{id_photo_id}.{ext}"
        try:
            storage.load(candidate)
        except FileNotFoundError:
            continue
        cust.id_photo_path = candidate
        return


def _enqueue_email_receipt(db: Session, *, policy_id: int, customer_email: str | None) -> None:
    """Queue an EMAIL_RECEIPT notification. No-op if customer has no email."""
    if not customer_email:
        return
    # Use the existing notification machinery. The dispatcher (Task 16)
    # picks these up and renders + sends the PDF.
    from app.models.notification import Notification
    db.add(Notification(
        customer_id=db.get(Policy, policy_id).customer_id,
        policy_id=policy_id,
        type="EMAIL_RECEIPT",
        message=f"Receipt for policy {policy_id}",
    ))


def process_submission(
    db: Session, *, device: Device, request: FieldSubmissionRequest,
) -> FieldSubmissionResponse:
    # Idempotency: return prior result if we've seen this client_uuid from this device.
    existing = (
        db.query(FieldSubmission)
        .filter(FieldSubmission.device_id == device.id,
                FieldSubmission.client_uuid == request.client_uuid)
        .first()
    )
    if existing is not None:
        # Re-hydrate results from raw_payload's stored response slot.
        return FieldSubmissionResponse.model_validate(existing.raw_payload["response"])

    # Create the FieldSubmission row up front so policies/payments can FK to it.
    fs = FieldSubmission(
        device_id=device.id,
        client_uuid=request.client_uuid,
        signups_count=0,
        payments_count=0,
        status=FieldSubmissionStatus.processed,
        raw_payload={"request": request.model_dump(mode="json"), "response": None},
    )
    db.add(fs); db.flush()

    results: list[FieldSignupResult] = []
    ok_count = 0
    payment_count = 0
    any_error = False

    for signup in request.signups:
        try:
            cover_resp = perform_cover_signup(db, _cover_payload_from(signup), actor=f"device:{device.id}")
            policy = db.get(Policy, cover_resp.policy_id)
            policy.field_submission_id = fs.id

            _store_id_photo_on_customer(db, cover_resp.customer_id, signup.id_photo_id)
            pay = _record_first_payment(db, policy=policy, signup=signup, field_submission_id=fs.id)

            if signup.email_receipt_requested:
                cust = db.get(Customer, cover_resp.customer_id)
                _enqueue_email_receipt(db, policy_id=policy.id, customer_email=cust.email)

            results.append(FieldSignupResult(
                local_id=signup.local_id,
                status="ok",
                customer_id=cover_resp.customer_id,
                policy_id=cover_resp.policy_id,
                payment_id=(pay.id if pay else None),
            ))
            ok_count += 1
            if pay is not None:
                payment_count += 1
        except HTTPException as e:
            any_error = True
            results.append(FieldSignupResult(
                local_id=signup.local_id, status="error",
                error=str(e.detail) if e.detail else "Validation failed",
            ))
            db.rollback()
            db.add(fs)   # re-attach after rollback
            db.flush()
        except Exception as e:    # noqa: BLE001 — capture the message, don't crash the batch
            any_error = True
            results.append(FieldSignupResult(
                local_id=signup.local_id, status="error", error=f"Internal error: {e!r}",
            ))
            db.rollback()
            db.add(fs); db.flush()

    fs.signups_count = ok_count
    fs.payments_count = payment_count
    if any_error and ok_count > 0:
        fs.status = FieldSubmissionStatus.partial
    elif any_error and ok_count == 0:
        fs.status = FieldSubmissionStatus.failed
    else:
        fs.status = FieldSubmissionStatus.processed

    response = FieldSubmissionResponse(field_submission_id=fs.id, results=results)
    # Persist the response in raw_payload so idempotent re-POSTs return it verbatim.
    fs.raw_payload = {
        "request": request.model_dump(mode="json"),
        "response": response.model_dump(mode="json"),
    }
    db.commit()
    return response
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_field_submission.py -v`
Expected: 3 PASS. If the partial-failure test struggles because `db.rollback()` discards the `FieldSubmission` row, adjust by using a SAVEPOINT (`db.begin_nested()`) per signup so per-signup rollbacks don't touch the parent transaction. Use this pattern if needed:

```python
for signup in request.signups:
    sp = db.begin_nested()
    try:
        ...
        sp.commit()   # release the savepoint
    except Exception as e:
        sp.rollback()
        ...
```

- [ ] **Step 5: Commit**

```bash
git add app/services/field_submission.py tests/test_field_submission.py
git commit -m "Idempotent field-submission batch processor"
```

---

### Task 14: `POST /api/field/submissions` endpoint

**Files:**
- Modify: `app/api/field.py`
- Modify: `tests/test_field_submission.py`

- [ ] **Step 1: Write the failing endpoint test**

Append to `tests/test_field_submission.py`:

```python
def test_post_submissions_endpoint(client, db):
    from app.core.device_auth import create_device_token
    plan = _plan(db); device = _device(db)
    token = create_device_token(device.id, name=device.name)
    client.headers.update({"Authorization": f"Bearer {token}"})

    body = {
        "client_uuid": "a" * 36,
        "signups": [{
            "local_id": "1",
            "cover_plan_id": plan.id,
            "holder": {"title": "Mr", "first_names": "A", "surname": "B", "id_number": "X1"},
            "dependents": [],
            "beneficiaries": [{
                "relationship_to_holder": "Spouse",
                "first_name": "C", "surname": "D",
                "share_pct": "100",
            }],
            "first_payment": {"amount": "360", "method": "cash"},
        }],
    }
    resp = client.post("/api/field/submissions", json=body)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["results"][0]["status"] == "ok"
    assert out["results"][0]["customer_id"]
    # Idempotent re-POST
    resp2 = client.post("/api/field/submissions", json=body)
    assert resp2.status_code == 200
    assert resp2.json() == out


def test_get_submission_by_client_uuid(client, db):
    from app.core.device_auth import create_device_token
    plan = _plan(db); device = _device(db)
    token = create_device_token(device.id, name=device.name)
    client.headers.update({"Authorization": f"Bearer {token}"})

    body = {
        "client_uuid": "f" * 36,
        "signups": [_signup_payload(plan.id).model_dump(mode="json")],
    }
    body["signups"][0]["beneficiaries"][0]["share_pct"] = "100"   # serialization quirk
    post = client.post("/api/field/submissions", json=body)
    assert post.status_code == 200

    resp = client.get(f"/api/field/submissions/{body['client_uuid']}")
    assert resp.status_code == 200
    assert resp.json() == post.json()


def test_get_submission_unknown_returns_404(client, db):
    from app.core.device_auth import create_device_token
    device = _device(db)
    token = create_device_token(device.id, name=device.name)
    client.headers.update({"Authorization": f"Bearer {token}"})
    resp = client.get(f"/api/field/submissions/{'z' * 36}")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_field_submission.py::test_post_submissions_endpoint -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement both endpoints in `app/api/field.py`**

Append:

```python
from app.models.field_submission import FieldSubmission
from app.schemas.field import (
    FieldSubmissionRequest, FieldSubmissionResponse,
)
from app.services.field_submission import process_submission


@router.post("/submissions", response_model=FieldSubmissionResponse)
def post_submission(
    payload: FieldSubmissionRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> FieldSubmissionResponse:
    return process_submission(db, device=device, request=payload)


@router.get("/submissions/{client_uuid}", response_model=FieldSubmissionResponse)
def get_submission(
    client_uuid: str,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> FieldSubmissionResponse:
    fs = (
        db.query(FieldSubmission)
        .filter(FieldSubmission.device_id == device.id,
                FieldSubmission.client_uuid == client_uuid)
        .first()
    )
    if fs is None:
        raise HTTPException(status_code=404, detail="No such submission for this device.")
    return FieldSubmissionResponse.model_validate(fs.raw_payload["response"])
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_field_submission.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add app/api/field.py tests/test_field_submission.py
git commit -m "POST + GET /api/field/submissions: idempotent batch capture endpoint"
```

---

## Phase 7 — Receipt PDF + email dispatch

### Task 15: Receipt PDF render function

**Files:**
- Create: `app/services/receipt_pdf.py`
- Create: `app/templates/receipts/funeral_cover.html`
- Create: `tests/test_field_receipt_pdf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_field_receipt_pdf.py`:

```python
"""Tests for the server-side receipt PDF renderer."""
from decimal import Decimal

from app.services.receipt_pdf import build_receipt_data, render_receipt_pdf
from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.member import Member
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy, PolicyStatus
from app.models.customer import Customer, CustomerStatus
from datetime import date


def _seed_signup(db):
    plan = CoverPlan(category=CoverCategory.me_and_family, cover_type="Family",
                     monthly_premium=Decimal("360"), max_dependents=4, is_active=True)
    db.add(plan); db.commit()
    cust = Customer(full_name="John Smith", first_names="John", surname="Smith",
                    id_number="ID123", email="john@example.com", status=CustomerStatus.active)
    db.add(cust); db.commit()
    policy = Policy(customer_id=cust.id, premium_amount=Decimal("360"),
                    status=PolicyStatus.active, cover_plan_id=plan.id)
    db.add(policy); db.commit()
    pay = Payment(customer_id=cust.id, policy_id=policy.id,
                  amount_paid=Decimal("360"), payment_date=date.today(),
                  payment_method=PaymentMethod.cash, status=PaymentStatus.paid,
                  reference="MZ-abc123")
    db.add(pay); db.commit()
    return cust, policy, pay


def test_build_receipt_data_shape(db):
    cust, policy, pay = _seed_signup(db)
    data = build_receipt_data(db, payment_id=pay.id)
    assert data["holder_name"] == "John Smith"
    assert data["plan_name"] == "Family"
    assert data["amount_paid"] == "360.00"
    assert data["reference"] == "MZ-abc123"
    assert data["policy_id"] == policy.id


def test_render_receipt_pdf_returns_pdf_bytes(db):
    _, _, pay = _seed_signup(db)
    data = build_receipt_data(db, payment_id=pay.id)
    pdf_bytes = render_receipt_pdf(data)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000   # non-trivial
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_field_receipt_pdf.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create the template**

Create `app/templates/receipts/funeral_cover.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mandlzi funeral cover receipt</title>
  <style>
    @page { size: A5; margin: 12mm; }
    body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #222; }
    h1 { font-size: 18pt; margin: 0 0 4mm 0; }
    .ref { font-family: monospace; color: #666; }
    table { width: 100%; border-collapse: collapse; margin-top: 4mm; }
    td { padding: 2mm 1mm; vertical-align: top; }
    td.label { color: #666; width: 40%; }
    .footer { margin-top: 8mm; font-size: 9pt; color: #555; }
  </style>
</head>
<body>
  <h1>Funeral cover receipt</h1>
  <div class="ref">{{ reference }}</div>
  <div>{{ date_iso }}</div>

  <table>
    <tr><td class="label">Holder</td><td>{{ holder_name }} ({{ holder_id_number }})</td></tr>
    <tr><td class="label">Plan</td><td>{{ plan_name }} — R{{ monthly_premium }}/month</td></tr>
    <tr><td class="label">Amount paid</td><td>R{{ amount_paid }} ({{ payment_method }})</td></tr>
    <tr><td class="label">For month of</td><td>{{ month_label }}</td></tr>
    <tr><td class="label">Dependents covered</td><td>{{ dependents_summary }}</td></tr>
  </table>

  <div class="footer">
    Coverage active from {{ coverage_start_iso }}. Cover lapses after
    {{ lapse_threshold_months }} consecutive missed monthly payments.
    <br>Captured by {{ device_name }} at {{ captured_at_iso }}.
  </div>
</body>
</html>
```

- [ ] **Step 4: Implement `app/services/receipt_pdf.py`**

```python
"""Server-side receipt rendering: data builder + PDF render via WeasyPrint."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.config import settings
from app.models.customer import Customer
from app.models.member import Member
from app.models.payment import Payment
from app.models.policy import Policy


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "receipts"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def build_receipt_data(db: Session, *, payment_id: int) -> dict[str, Any]:
    pay = db.get(Payment, payment_id)
    if pay is None:
        raise ValueError(f"Payment {payment_id} not found")
    policy = db.get(Policy, pay.policy_id)
    customer = db.get(Customer, pay.customer_id)
    deps = db.query(Member).filter(Member.policy_id == policy.id).all()
    plan = policy.cover_plan
    threshold = policy.lapse_threshold_months or settings.LAPSE_THRESHOLD_MONTHS

    return {
        "reference": pay.reference or f"MZ-{policy.id}",
        "date_iso": pay.payment_date.isoformat(),
        "holder_name": customer.full_name,
        "holder_id_number": customer.id_number,
        "plan_name": (plan.cover_type if plan else "—"),
        "monthly_premium": f"{policy.premium_amount:.2f}",
        "amount_paid": f"{pay.amount_paid:.2f}",
        "payment_method": pay.payment_method.value if hasattr(pay.payment_method, "value") else str(pay.payment_method),
        "month_label": pay.payment_date.strftime("%B %Y"),
        "dependents_summary": (
            f"{len(deps)} dependent(s): " + ", ".join(d.full_name for d in deps)
            if deps else "None"
        ),
        "coverage_start_iso": policy.start_date.isoformat() if policy.start_date else "",
        "lapse_threshold_months": threshold,
        "device_name": "—",            # filled in by caller if known
        "captured_at_iso": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "policy_id": policy.id,
    }


def render_receipt_pdf(data: dict[str, Any]) -> bytes:
    html = _env.get_template("funeral_cover.html").render(**data)
    return HTML(string=html).write_pdf()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_field_receipt_pdf.py -v`
Expected: 2 PASS. (If WeasyPrint can't find GTK runtime on Windows, document the workaround in `README.md` and run the test on WSL/Linux for now — the design accepts this as a dev-env quirk.)

- [ ] **Step 6: Commit**

```bash
git add app/services/receipt_pdf.py app/templates/receipts/funeral_cover.html tests/test_field_receipt_pdf.py
git commit -m "Server-side receipt PDF: WeasyPrint + Jinja template"
```

---

### Task 16: Wire `EMAIL_RECEIPT` notification provider

**Files:**
- Modify: `app/services/notification_providers.py` *(or wherever email providers live)*
- Modify: `app/services/notification_dispatcher.py`
- Create: `tests/test_field_email_receipt.py`

- [ ] **Step 1: Read the existing dispatcher to understand the provider contract**

Run:
```
grep -n "EMAIL\|provider\|dispatch" app/services/notification_providers.py app/services/notification_dispatcher.py
```

Read both files. The provider contract typically looks like a function or class with `send(notification) -> success/failure`. Mirror that shape.

- [ ] **Step 2: Write the failing test**

Create `tests/test_field_email_receipt.py`:

```python
"""When an EMAIL_RECEIPT notification is dispatched, it renders the PDF
and sends it to the customer's email."""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.models.customer import Customer, CustomerStatus
from app.models.cover_plan import CoverCategory, CoverPlan
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.policy import Policy, PolicyStatus
from app.models.notification import Notification


def test_email_receipt_renders_pdf_and_calls_provider(db, monkeypatch):
    # Seed enough state to render a receipt
    plan = CoverPlan(category=CoverCategory.me, cover_type="Me",
                     monthly_premium=Decimal("120"), max_dependents=0, is_active=True)
    db.add(plan); db.commit()
    cust = Customer(full_name="X Y", first_names="X", surname="Y", id_number="1",
                    email="x@example.com", status=CustomerStatus.active)
    db.add(cust); db.commit()
    policy = Policy(customer_id=cust.id, premium_amount=Decimal("120"),
                    status=PolicyStatus.active, cover_plan_id=plan.id)
    db.add(policy); db.commit()
    pay = Payment(customer_id=cust.id, policy_id=policy.id,
                  amount_paid=Decimal("120"), payment_method=PaymentMethod.cash,
                  status=PaymentStatus.paid)
    db.add(pay); db.commit()

    notif = Notification(customer_id=cust.id, policy_id=policy.id,
                         type="EMAIL_RECEIPT", message=f"Receipt for policy {policy.id}")
    db.add(notif); db.commit()

    sent: list[dict] = []

    def fake_send(to, subject, body, *, attachments=None, **kw):
        sent.append({"to": to, "subject": subject,
                     "attachments": [a["filename"] for a in (attachments or [])]})
        return True

    from app.services import notification_dispatcher
    monkeypatch.setattr(notification_dispatcher, "send_email", fake_send, raising=False)
    notification_dispatcher.dispatch_pending(db)

    assert sent, "no email was sent"
    assert sent[0]["to"] == "x@example.com"
    assert any(a.endswith(".pdf") for a in sent[0]["attachments"])
```

(Adjust the patch target to whatever symbol the existing dispatcher actually calls when sending email.)

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_field_email_receipt.py -v`
Expected: FAIL — either the notification type isn't recognized, or no email is sent.

- [ ] **Step 4: Implement the EMAIL_RECEIPT provider branch**

Read the existing dispatcher carefully. Add a branch (or new provider class) that, when `notification.type == "EMAIL_RECEIPT"`:

```python
def _send_email_receipt(db: Session, notification: Notification) -> bool:
    from app.services.receipt_pdf import build_receipt_data, render_receipt_pdf
    # Find the most recent payment for this policy (the one this receipt is for)
    pay = (
        db.query(Payment)
        .filter(Payment.policy_id == notification.policy_id)
        .order_by(Payment.created_at.desc())
        .first()
    )
    if pay is None:
        return False
    data = build_receipt_data(db, payment_id=pay.id)
    pdf = render_receipt_pdf(data)

    customer = db.get(Customer, notification.customer_id)
    if not customer or not customer.email:
        return False

    send_email(
        to=customer.email,
        subject=f"Your Mandlzi funeral cover receipt ({data['reference']})",
        body=f"Thank you for joining Mandlzi. Your receipt is attached.\nReference: {data['reference']}",
        attachments=[{"filename": f"{data['reference']}.pdf", "content": pdf, "mime": "application/pdf"}],
    )
    return True
```

`send_email(...)` is the existing email-sending helper — match its actual signature. If the project doesn't have one, add a minimal one in `app/services/notification_providers.py`:

```python
import smtplib
from email.message import EmailMessage

def send_email(to: str, subject: str, body: str, *, attachments=None) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = to
    msg["From"] = settings.NOTIFICATION_EMAIL_FROM or "noreply@mandlzi.local"
    msg.set_content(body)
    for att in (attachments or []):
        msg.add_attachment(att["content"], maintype=att["mime"].split("/")[0],
                           subtype=att["mime"].split("/")[1], filename=att["filename"])
    # In dev, the "log" provider just logs; production wires SMTP credentials.
    if settings.NOTIFICATION_PROVIDER == "log":
        import logging
        logging.getLogger("mandlzi.email").info("EMAIL %s — %s — attachments=%d",
                                                to, subject, len(attachments or []))
        return True
    with smtplib.SMTP(settings.NOTIFICATION_SMTP_HOST, settings.NOTIFICATION_SMTP_PORT) as s:
        s.send_message(msg)
    return True
```

Add the new settings to `app/config.py`:
```python
    NOTIFICATION_EMAIL_FROM: str = "noreply@mandlzi.local"
    NOTIFICATION_SMTP_HOST: str = "localhost"
    NOTIFICATION_SMTP_PORT: int = 25
```

- [ ] **Step 5: Run the test**

Run: `pytest tests/test_field_email_receipt.py -v`
Expected: PASS.

- [ ] **Step 6: Run notification suite to confirm nothing else broke**

Run: `pytest tests/test_notification_dispatch.py -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add app/services/notification_providers.py app/services/notification_dispatcher.py app/config.py tests/test_field_email_receipt.py
git commit -m "EMAIL_RECEIPT notification: render PDF + email it via notification dispatcher"
```

---

## Phase 8 — Admin endpoints (enrollment + revocation)

### Task 17: Admin endpoints to issue codes + revoke devices

**Files:**
- Create: `app/api/field_admin.py`
- Create: `tests/test_field_admin.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_field_admin.py`:

```python
"""Tests for the admin-side device management endpoints."""
from datetime import datetime, timedelta

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
    items = resp.json()["devices"]
    assert {d["name"] for d in items} == {"Phone-A", "Phone-B"}


def test_admin_revokes_device(auth_client, db):
    d = Device(name="Phone-X", token_hash="x", status=DeviceStatus.active)
    db.add(d); db.commit(); db.refresh(d)
    resp = auth_client.post(f"/admin/field/devices/{d.id}/revoke")
    assert resp.status_code == 200
    db.refresh(d)
    assert d.status == DeviceStatus.revoked


def test_admin_endpoints_require_admin_role(client, db):
    """Anonymous + non-admin users get 401/403."""
    r = client.post("/admin/field/enrollment-codes")
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_field_admin.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement the admin router**

Create `app/api/field_admin.py`:

```python
"""Admin endpoints for managing field devices + enrollment codes."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.config import settings
from app.api.field import _generate_enrollment_code
from app.database import get_db
from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus
from app.models.user import User


router = APIRouter(prefix="/admin/field", tags=["field-admin"])


class EnrollmentCodeOut(BaseModel):
    code: str
    expires_at: datetime


class DeviceOut(BaseModel):
    id: int
    name: str
    status: str
    enrolled_at: datetime
    last_seen_at: datetime | None


class DevicesResponse(BaseModel):
    devices: list[DeviceOut]


@router.post("/enrollment-codes", response_model=EnrollmentCodeOut)
def create_enrollment_code(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> EnrollmentCodeOut:
    for _ in range(8):   # ~zero collision risk with 6 chars from 32 alphabet
        code = _generate_enrollment_code()
        existing = db.query(DeviceEnrollmentCode).filter_by(code=code).first()
        if existing is None:
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate a unique code.")
    expires_at = datetime.utcnow() + timedelta(hours=settings.ENROLLMENT_CODE_EXPIRES_HOURS)
    row = DeviceEnrollmentCode(code=code, created_by_user_id=user.id, expires_at=expires_at)
    db.add(row); db.commit()
    return EnrollmentCodeOut(code=code, expires_at=expires_at)


@router.get("/devices", response_model=DevicesResponse)
def list_devices(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DevicesResponse:
    rows = db.query(Device).order_by(Device.id).all()
    return DevicesResponse(devices=[
        DeviceOut(
            id=d.id, name=d.name,
            status=d.status.value if hasattr(d.status, "value") else str(d.status),
            enrolled_at=d.enrolled_at, last_seen_at=d.last_seen_at,
        ) for d in rows
    ])


@router.post("/devices/{device_id}/revoke")
def revoke_device(
    device_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    d = db.get(Device, device_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    d.status = DeviceStatus.revoked
    db.commit()
    return {"ok": True, "device_id": device_id, "status": "revoked"}
```

- [ ] **Step 4: Register the router**

Edit `app/main.py`, after the existing field router:

```python
    from app.api import field_admin
    app.include_router(field_admin.router)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_field_admin.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/field_admin.py app/main.py tests/test_field_admin.py
git commit -m "Admin endpoints: generate enrollment codes + revoke devices"
```

---

## Phase 9 — End-to-end integration test

### Task 18: Full happy-path E2E pytest

**Files:**
- Create: `tests/test_field_e2e.py`

- [ ] **Step 1: Write the E2E test**

Create `tests/test_field_e2e.py`:

```python
"""End-to-end test of the field-capture backend flow, no frontend.

Walks: admin issues code → phone enrolls → phone fetches plans → phone
uploads ID photo → phone submits signup with first payment → phone gets
receipt by re-posting same client_uuid (idempotency) → admin revokes
device → subsequent POST is rejected.
"""
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
    from app.config import get_settings; get_settings.cache_clear()

    # Plan
    plan = CoverPlan(category=CoverCategory.me_and_family, cover_type="Family",
                     monthly_premium=Decimal("360"), max_dependents=4, is_active=True)
    db.add(plan); db.commit()

    # 1. Admin issues enrollment code
    code_resp = auth_client.post("/admin/field/enrollment-codes")
    code = code_resp.json()["code"]

    # 2. Phone enrolls
    enroll = client.post("/api/field/enroll", json={"code": code, "name": "Phone-01"})
    assert enroll.status_code == 200
    jwt = enroll.json()["device_jwt"]
    device_id = enroll.json()["device_id"]
    client.headers.update({"Authorization": f"Bearer {jwt}"})

    # 3. Phone fetches cover plans
    plans = client.get("/api/field/cover-plans").json()["plans"]
    assert len(plans) == 1 and plans[0]["cover_type"] == "Family"

    # 4. Phone uploads ID photo
    photo = client.post("/api/field/photos",
                        files={"file": ("id.jpg", _jpeg(), "image/jpeg")}).json()

    # 5. Phone submits signup + first payment
    body = {
        "client_uuid": "1" * 36,
        "signups": [{
            "local_id": "1",
            "cover_plan_id": plan.id,
            "holder": {"title": "Mr", "first_names": "John", "surname": "Smith", "id_number": "9001015800086", "email": "john@example.com"},
            "id_photo_id": photo["id_photo_id"],
            "dependents": [{"title": "Mrs", "first_names": "Jane", "surname": "Smith", "relationship_to_holder": "Spouse"}],
            "beneficiaries": [{
                "relationship_to_holder": "Daughter",
                "first_name": "Jill", "surname": "Smith",
                "share_pct": "100",
            }],
            "first_payment": {"amount": "360", "method": "cash", "reference": "FLD-001"},
            "email_receipt_requested": True,
        }],
    }
    submit = client.post("/api/field/submissions", json=body)
    assert submit.status_code == 200, submit.text
    out = submit.json()
    assert out["results"][0]["status"] == "ok"
    policy_id = out["results"][0]["policy_id"]

    # 6. Idempotent retry returns the same response
    submit2 = client.post("/api/field/submissions", json=body)
    assert submit2.status_code == 200
    assert submit2.json() == out

    # 7. GET by client_uuid
    fetched = client.get(f"/api/field/submissions/{body['client_uuid']}")
    assert fetched.status_code == 200
    assert fetched.json() == out

    # 8. Admin revokes the device
    auth_client.post(f"/admin/field/devices/{device_id}/revoke")

    # 9. Next call from phone is 401 with DEVICE_REVOKED
    after = client.get("/api/field/cover-plans")
    assert after.status_code == 401
    assert after.json()["detail"] == {"code": "DEVICE_REVOKED"}
```

- [ ] **Step 2: Run the E2E test**

Run: `pytest tests/test_field_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite to confirm nothing else regressed**

Run: `pytest -x -q`
Expected: green (or, if any pre-existing failures, only those).

- [ ] **Step 4: Commit**

```bash
git add tests/test_field_e2e.py
git commit -m "Backend E2E test: enroll → upload → submit (idempotent) → revoke"
```

---

## Phase 10 — Admin frontend parity (beneficiary fields)

### Task 19: Surface new beneficiary fields in the existing admin signup wizard

**Files:**
- Modify: `frontend/src/pages/NewCustomerPage.tsx`
- Modify: `frontend/src/api/` (whatever module wraps cover signup)
- Modify: `frontend/src/types.ts` *(if beneficiary types live there)*

- [ ] **Step 1: Read the existing admin wizard**

Run:
```
grep -nE "beneficiar|share_pct" frontend/src/pages/NewCustomerPage.tsx frontend/src/types.ts frontend/src/api/*.ts
```

Identify the beneficiary form section and the typescript shape.

- [ ] **Step 2: Extend the typescript type**

In `frontend/src/types.ts` (or wherever `Beneficiary` is typed), add:

```typescript
export interface BeneficiaryInput {
  relationship_to_holder: string;
  title?: string;
  first_name: string;
  surname: string;
  gender?: string;
  date_of_birth?: string;     // ISO yyyy-mm-dd
  nationality?: string;
  email?: string;
  cellphone?: string;
  country_of_birth?: string;
  share_pct: string;
}
```

If a `Beneficiary` type already exists, add the five optional fields to it.

- [ ] **Step 3: Add the new fields to the admin form**

In `NewCustomerPage.tsx`, find the JSX block where existing beneficiary fields are rendered. Add five new inputs (title, gender, DOB, nationality, email) following the same styling pattern as the existing inputs. They are optional — no `required` attribute.

- [ ] **Step 4: Run frontend type-check**

Run:
```
cd frontend && npm run lint
```
Expected: no TS errors.

- [ ] **Step 5: Manually verify the form**

Start backend + frontend, sign up a customer with the new fields, confirm they round-trip to the DB:

```
# backend
uvicorn app.main:app --reload
# frontend (separate shell)
cd frontend && npm run dev
```

Open the app, complete a signup with beneficiary email/title/DOB filled in. Verify via:
```
sqlite3 mandlzi.db "select title, gender, date_of_birth, nationality, email from beneficiaries order by id desc limit 1;"
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/NewCustomerPage.tsx frontend/src/types.ts frontend/src/api
git commit -m "Admin wizard: surface new beneficiary fields (title/gender/DOB/nationality/email)"
```

---

## Acceptance check (run at the end)

After Task 19, verify:

- [ ] `pytest -q` — all tests pass.
- [ ] `cd frontend && npm run lint` — no TS errors.
- [ ] `alembic upgrade head` on a fresh SQLite DB succeeds; `alembic downgrade base` then `upgrade head` succeeds.
- [ ] Full E2E test passes against a running uvicorn process via the OpenAPI docs at `/docs` — enrol a device, fetch plans, upload a photo, submit a batch.
- [ ] An admin-issued enrollment code is exactly 6 chars, expires after the configured window, single-use.
- [ ] A device JWT presented to `/customers` (or any admin route) returns 401.
- [ ] A user JWT presented to `/api/field/cover-plans` returns 401.
- [ ] A revoked device's next call returns 401 with body `{"detail": {"code": "DEVICE_REVOKED"}}`.

When all boxes are checked, the backend half of the field-capture-app spec is complete and Plan 2 (PWA frontend) can begin.
