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
    "cover_plans",
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
