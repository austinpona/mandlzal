"""Smoke test for the Alembic migration chain.

Spins up an isolated SQLite DB, runs `alembic upgrade head` against it
via the alembic Python API (no shell subprocess needed), then verifies:

1. The current revision is at HEAD
2. The expected tables all exist
3. `alembic downgrade base` cleans them all up again

This guards against the migration ever drifting from `Base.metadata`.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]
INI = ROOT / "alembic.ini"


EXPECTED_TABLES = {
    "users", "customers", "policies", "members",
    "payments", "audit_logs", "notifications",
    "cover_plans", "beneficiaries", "devices",
    "device_enrollment_codes", "field_submissions",
}


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Yield (alembic.Config, sqlalchemy_url) bound to a fresh SQLite file."""
    db_file = tmp_path / f"alembic_test_{uuid.uuid4().hex[:8]}.db"
    url = f"sqlite:///{db_file.as_posix()}"

    # Settings are cached - make absolutely sure alembic env.py sees this URL.
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("RUN_INIT_DB", "0")

    # Drop the cached Settings instance so env.py picks up the new env var.
    from app.config import get_settings
    get_settings.cache_clear()

    cfg = Config(str(INI))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    yield cfg, url

    get_settings.cache_clear()


def _current_revision(url: str) -> str | None:
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()


def test_upgrade_head_creates_all_tables(isolated_db):
    cfg, url = isolated_db
    command.upgrade(cfg, "head")

    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert _current_revision(url) == head

    engine = create_engine(url, future=True)
    tables = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"migration did not create: {missing}"


def test_downgrade_base_removes_app_tables(isolated_db):
    cfg, url = isolated_db
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    assert _current_revision(url) is None

    engine = create_engine(url, future=True)
    tables = set(inspect(engine).get_table_names())
    # alembic_version may still exist; the *app* tables must not.
    leftovers = EXPECTED_TABLES & tables
    assert not leftovers, f"downgrade left tables behind: {leftovers}"


def test_metadata_matches_migration(isolated_db):
    """After `upgrade head`, autogenerate should detect NO diffs.

    This catches the common bug of editing a model but forgetting to
    create a matching migration.
    """
    cfg, url = isolated_db
    command.upgrade(cfg, "head")

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext as MC
    from app.database import Base
    import app.models  # noqa: F401

    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        ctx = MC.configure(
            conn,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": lambda obj, name, type_, *_: not (type_ == "table" and name == "alembic_version"),
            },
        )
        diffs = compare_metadata(ctx, Base.metadata)
    assert not diffs, f"models drifted from migrations: {diffs}"


def test_field_capture_models_import_and_register():
    from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus
    from app.models.field_submission import FieldSubmission, FieldSubmissionStatus

    assert DeviceStatus.active.value == "active"
    assert DeviceStatus.revoked.value == "revoked"
    assert "devices" in Device.metadata.tables
    assert "device_enrollment_codes" in DeviceEnrollmentCode.metadata.tables
    assert FieldSubmissionStatus.processed.value == "processed"
    assert FieldSubmissionStatus.partial.value == "partial"
    assert FieldSubmissionStatus.failed.value == "failed"
    assert "field_submissions" in FieldSubmission.metadata.tables


def test_existing_models_have_field_capture_columns():
    from app.models.beneficiary import Beneficiary
    from app.models.customer import Customer
    from app.models.payment import Payment
    from app.models.policy import Policy

    bcols = {c.name for c in Beneficiary.__table__.columns}
    assert {"title", "gender", "date_of_birth", "nationality", "email"} <= bcols
    assert "id_photo_path" in {c.name for c in Customer.__table__.columns}
    assert "field_submission_id" in {c.name for c in Policy.__table__.columns}
    assert "field_submission_id" in {c.name for c in Payment.__table__.columns}
