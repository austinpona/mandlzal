"""Observability: structured request logging + Prometheus /metrics.

Two independent pieces:

1. `RequestLogMiddleware` - logs one JSON-ish line per request with
   method, path, status, duration and (when authenticated) the JWT
   `sub` claim, so you can correlate latency / errors with a user.
   Use a real JSON log formatter in production (e.g. structlog +
   python-json-logger); the implementation here is deliberately
   dependency-free.

2. `setup_metrics(app)` - mounts `/metrics` exposing the standard
   `prometheus_fastapi_instrumentator` HTTP metrics (request count,
   duration histogram, in-progress gauge, etc.) plus a custom
   gauge per business entity that the daily sweep can update.

Both can be toggled off via `REQUEST_LOG_ENABLED` / `METRICS_ENABLED`
for unit tests.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from jose import JWTError
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import decode_token


logger = logging.getLogger("mandlzi.access")


# Custom domain metrics. The HTTP metrics (`http_requests_total`,
# `http_request_duration_seconds`, etc.) are added automatically by
# Instrumentator below; these gauges are for the *business* dimensions
# that operators tend to alert on.
active_policies_gauge = Gauge(
    "mandlzi_active_policies", "Number of policies currently in `active` status."
)
lapsed_policies_gauge = Gauge(
    "mandlzi_lapsed_policies", "Number of policies currently in `lapsed` status."
)


def _extract_user_id(request: Request) -> str | None:
    """Best-effort: pull the `sub` claim from a Bearer token, if any.

    Never raises - bad / missing tokens just return None so the access
    log stays unobtrusive on anonymous traffic.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        return str(sub) if sub is not None else None
    except (JWTError, ValueError, TypeError):
        return None


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Emit one access-log line per request.

    Format (space-separated key=value, easy to parse with logfmt
    consumers and human-readable in `tail -f`):

        ts=... method=GET path=/customers status=200 dur_ms=12.3
        ip=127.0.0.1 user=42

    Failures inside the handler are still logged (status from the
    exception's response, dur_ms from the partial timing) and then
    re-raised so the normal exception handlers can take over.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        client_ip = request.client.host if request.client else "-"
        user_id = _extract_user_id(request) or "-"
        status_code = 500  # default if the handler explodes before sending a response
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            dur_ms = (time.perf_counter() - start) * 1000.0
            logger.info(
                "method=%s path=%s status=%d dur_ms=%.2f ip=%s user=%s",
                request.method, request.url.path, status_code, dur_ms,
                client_ip, user_id,
            )


def setup_metrics(app: FastAPI) -> None:
    """Attach Prometheus instrumentation to `app` and expose `/metrics`.

    Safe to call exactly once at app creation time. Calling it again
    (e.g. in tests that build multiple apps) is a no-op for the global
    registry because Instrumentator deduplicates by metric name.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,    # we want 401 vs 403 etc separately
        should_ignore_untemplated=True,     # don't blow up cardinality on bad paths
        should_respect_env_var=False,
        excluded_handlers=["/metrics", "/health"],
        inprogress_name="mandlzi_inprogress_requests",
        inprogress_labels=True,
    )
    instrumentator.instrument(app)
    # Expose at /metrics. We register the route on the FastAPI app
    # directly so it inherits the same auth / middleware stack.
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
