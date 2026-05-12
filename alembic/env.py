"""Alembic environment.

Sources the database URL from the application's `settings` (which in turn
reads `DATABASE_URL` from the environment / .env file) and uses the
SQLAlchemy `Base.metadata` so that `alembic revision --autogenerate`
detects model changes automatically.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the app so all models register with Base.metadata.
from app.config import Settings
from app.database import Base
import app.models  # noqa: F401  (side-effect: register all models)


config = context.config

# Resolve the DB URL fresh on every invocation. We prefer the live
# environment variable so tests / CI can override per-run without being
# foiled by Python module caching of `settings`.
_db_url = os.environ.get("DATABASE_URL") or Settings().DATABASE_URL
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    # `disable_existing_loggers=False` so loggers configured by the host
    # application (e.g. `mandlzi.access`) survive when alembic runs in
    # the same process - otherwise running migrations inside the test
    # suite (or via `alembic upgrade head` while the app is up) would
    # silence them.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Skip Alembic's own version table during autogenerate diffs."""
    if type_ == "table" and name == "alembic_version":
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL scripts without a live DB connection (`alembic upgrade --sql ...`)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
        render_as_batch=url.startswith("sqlite"),  # SQLite needs batch mode for ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
            render_as_batch=is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
