"""Tests for production-hardening features:
  * rate limiting on /auth/login + /auth/register
  * refusing to boot in PRODUCTION mode with a weak JWT_SECRET
"""
from contextlib import contextmanager

import pytest


# ---------- Helpers ----------


@contextmanager
def _settings_override(**overrides):
    """Temporarily set attributes on the live `settings` object.

    Bypasses pydantic-settings' env-driven construction so each test can
    flip a few flags without reloading modules. Original values are
    restored on exit, even when assertions fail.
    """
    from app.config import settings
    saved = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        object.__setattr__(settings, k, v)
    try:
        yield settings
    finally:
        for k, v in saved.items():
            object.__setattr__(settings, k, v)


# ---------- Rate limiting ----------


@pytest.fixture
def limited_client(client):
    """Enable rate limiting at runtime with very low limits, then yield a
    TestClient using the existing app. The limit strings are read
    lazily by the auth router's `@limiter.limit(lambda: ...)`, so a
    plain attribute override is enough - no module reloading required.
    """
    from app.core.rate_limit import limiter
    with _settings_override(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_LOGIN="3/minute",
        RATE_LIMIT_REGISTER="2/minute",
    ):
        saved_enabled = limiter.enabled
        limiter.enabled = True
        limiter.reset()
        try:
            yield client
        finally:
            limiter.enabled = saved_enabled
            limiter.reset()


def test_login_rate_limit_returns_429(limited_client):
    """The 4th login attempt within a minute should be rejected with 429."""
    limited_client.post("/auth/register", json={
        "email": "rl-user@example.com", "password": "secret123",
    })

    statuses = []
    for _ in range(4):
        r = limited_client.post(
            "/auth/login",
            data={"username": "rl-user@example.com", "password": "secret123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        statuses.append(r.status_code)

    # First three within budget; the 4th is throttled.
    assert statuses[:3] == [200, 200, 200], statuses
    assert statuses[3] == 429, statuses


def test_register_rate_limit_returns_429(limited_client):
    """The 3rd register call within a minute should be rejected with 429."""
    statuses = []
    for i in range(3):
        r = limited_client.post("/auth/register", json={
            "email": f"rl-reg-{i}@example.com", "password": "secret123",
        })
        statuses.append(r.status_code)

    assert statuses[:2] == [201, 201], statuses
    assert statuses[2] == 429, statuses


def test_rate_limit_disabled_by_default_in_tests(client):
    """Smoke test: with the default test config (RATE_LIMIT_ENABLED=0
    set by conftest), repeated logins do not trip 429. Guards against
    future regressions where rate limiting accidentally leaks into the
    rest of the suite.
    """
    client.post("/auth/register", json={
        "email": "norl@example.com", "password": "secret123",
    })
    for _ in range(15):
        r = client.post(
            "/auth/login",
            data={"username": "norl@example.com", "password": "secret123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200


# ---------- Production JWT secret guard ----------


def test_production_mode_refuses_default_jwt_secret():
    from app.main import _verify_production_config
    with _settings_override(PRODUCTION=True, JWT_SECRET="dev-secret-change-me"):
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            _verify_production_config()


def test_production_mode_refuses_short_jwt_secret():
    from app.main import _verify_production_config
    with _settings_override(PRODUCTION=True, JWT_SECRET="short"):
        with pytest.raises(RuntimeError, match="32 chars"):
            _verify_production_config()


def test_production_mode_accepts_strong_jwt_secret():
    from app.main import _verify_production_config
    with _settings_override(PRODUCTION=True, JWT_SECRET="x" * 48):
        _verify_production_config()  # must not raise


def test_dev_mode_allows_default_jwt_secret():
    """In dev mode the secret strength check is skipped."""
    from app.main import _verify_production_config
    with _settings_override(PRODUCTION=False, JWT_SECRET="dev-secret-change-me"):
        _verify_production_config()  # must not raise
