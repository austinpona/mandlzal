"""Pytest fixtures: isolated in-memory SQLite DB for each test session."""
import os

# Use a fresh sqlite file for tests before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_mandlzi.db")
os.environ.setdefault("SCHEDULER_ENABLED", "0")
# Rate-limit-aware tests opt back in explicitly; for the rest of the
# suite we keep it disabled so repeated logins don't trip 429.
os.environ.setdefault("RATE_LIMIT_ENABLED", "0")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


TEST_DB_URL = "sqlite:///./test_mandlzi.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """A TestClient with an authenticated admin token attached."""
    client.post("/auth/register", json={
        "email": "tester@example.com",
        "password": "secret123",
        "full_name": "Tester",
    })
    resp = client.post(
        "/auth/login",
        data={"username": "tester@example.com", "password": "secret123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
