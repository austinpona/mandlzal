"""Shared rate-limiter for the application.

We use **slowapi** (a starlette-friendly wrapper around `limits`) to
throttle authentication endpoints. The limiter is keyed by the remote
IP address by default. For deployments behind a proxy, make sure
`X-Forwarded-For` is being honoured by your ASGI server / proxy so the
real client IP reaches us, otherwise everyone shares the same bucket.

Limits are configurable per-call (e.g. `@limiter.limit("5/minute")`)
and can be disabled wholesale by setting `RATE_LIMIT_ENABLED=0`, which
is what the test suite does to avoid flaky tests.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


# When disabled, we still construct a Limiter so route decorators stay
# valid - but we override its `enabled` attribute so it never trips.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.RATE_LIMIT_ENABLED,
    # NOTE: `headers_enabled=True` is intentionally OFF. slowapi 0.1.9's
    # header injection assumes a starlette Response instance is already
    # available when the limit decorator wraps the handler, which is
    # not the case for FastAPI routes that return a Pydantic model.
    # Enabling it raises at request time. Re-enable only if you upgrade
    # slowapi and confirm the bug is fixed.
    headers_enabled=False,
    default_limits=[],     # opt-in only; specific routes choose their limits
)
