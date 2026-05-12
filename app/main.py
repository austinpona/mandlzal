"""FastAPI application entrypoint.

Wires up routers, creates database tables on startup (dev convenience),
and exposes the OpenAPI docs at `/docs`.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import admin, auth, cover, customers, dashboard, members, payments, policies
from app.config import settings
from app.core.observability import RequestLogMiddleware, setup_metrics
from app.core.rate_limit import limiter
from app.database import init_db
from app.scheduler import start_scheduler, stop_scheduler


# The known-insecure default JWT secrets. Anything matching these in
# PRODUCTION mode blocks startup so a stolen .env can't accidentally
# ship with the dev key.
_INSECURE_DEFAULT_JWT_SECRETS = {"dev-secret-change-me", "change-me-to-a-long-random-string", ""}


def _verify_production_config() -> None:
    """Refuse to boot in production with insecure defaults."""
    if not settings.PRODUCTION:
        return
    if settings.JWT_SECRET in _INSECURE_DEFAULT_JWT_SECRETS or len(settings.JWT_SECRET) < 32:
        raise RuntimeError(
            "PRODUCTION=1 but JWT_SECRET is missing, default, or shorter than 32 chars. "
            "Set a strong random JWT_SECRET (e.g. "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: validate config, bootstrap schema (dev), start scheduler."""
    _verify_production_config()
    if settings.RUN_INIT_DB:
        init_db()
    # Make sure the funeral-cover catalog is populated. Idempotent, so
    # safe to run on every boot - it only inserts missing rows.
    from app.database import SessionLocal
    from app.services.cover_seed import seed_cover_plans
    _db = SessionLocal()
    try:
        seed_cover_plans(_db)
    finally:
        _db.close()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Subscription management for insurance-like products (funeral / group scheme).",
        lifespan=lifespan,
    )

    # Wire up rate limiting. The Limiter is attached to app.state so route
    # decorators (e.g. @limiter.limit) can find it; SlowAPIMiddleware does
    # the actual enforcement on every request.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Observability. Request logging runs as a starlette middleware so it
    # captures duration even for handlers that raise. Prometheus metrics
    # are mounted at /metrics by `setup_metrics`.
    if settings.REQUEST_LOG_ENABLED:
        app.add_middleware(RequestLogMiddleware)
    if settings.METRICS_ENABLED:
        setup_metrics(app)

    # Permissive CORS for dev; tighten `allow_origins` in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(customers.router)
    app.include_router(policies.router)
    app.include_router(payments.router)
    app.include_router(members.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)
    app.include_router(cover.router)
    return app


app = create_app()
