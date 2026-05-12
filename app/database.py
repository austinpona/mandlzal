"""Database engine, session factory and Base class.

Single source of truth for SQLAlchemy plumbing. The `get_db` dependency
yields a request-scoped session that is closed automatically.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import settings


# SQLite needs a special connect arg for multi-threaded FastAPI usage.
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and ensures cleanup."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Suitable for dev; use Alembic in production."""
    # Import models so they register with Base.metadata
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
