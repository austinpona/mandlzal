# Mandlzi - Subscription Management System

Production-ready backend for managing **insurance-like subscriptions** (funeral policies / group schemes). Tracks customers, policies, monthly payments, group-scheme members, and computes whether each customer is **PAID**, **NOT PAID**, or **OVERDUE** based on configurable business rules.

## Stack

- **Backend**: Python 3.11+ / FastAPI
- **ORM**: SQLAlchemy 2.x
- **DB**: PostgreSQL (production) or SQLite (dev/tests)
- **Auth**: JWT (OAuth2 password flow)
- **Tests**: pytest + httpx TestClient

## Architecture

```
app/
├── main.py             # FastAPI app factory & router wiring
├── config.py           # Settings (env-driven)
├── database.py         # SQLAlchemy engine, session, Base
├── models/             # ORM models (one file per entity)
├── schemas/            # Pydantic request/response schemas
├── core/
│   ├── security.py     # bcrypt + JWT helpers
│   └── audit.py        # audit log helper
├── services/
│   ├── billing.py      # PURE payment-status logic (unit-tested)
│   └── notifications.py
└── api/                # Routers: auth, customers, policies, payments, members, dashboard
scripts/seed.py         # Sample data
tests/                  # pytest suite
schema.sql              # Reference PostgreSQL DDL
```

The **billing service** (`app/services/billing.py`) is framework-free pure logic: it takes a `Policy` + its payments and computes per-month status, arrears count, and outstanding amounts. The API layer wraps it and persists side effects (auto-lapse, notifications).

## Setup

```bash
# 1. Create venv & install
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# 2. Configure (defaults to SQLite if not set)
copy .env.example .env

# 3. Seed sample data
python -m scripts.seed

# 4. Run the API
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for interactive Swagger UI.

### With PostgreSQL

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/mandlzi
```

Tables are auto-created on startup when `RUN_INIT_DB=1` (the default, for dev convenience). **For production set `RUN_INIT_DB=0` and use Alembic** — see below.

## Database migrations (Alembic)

The schema is managed by Alembic. The initial migration in `alembic/versions/` is the baseline.

```bash
# apply all pending migrations (the production path)
alembic upgrade head

# show currently-applied revision
alembic current

# create a new migration from model diffs (review the file before committing!)
alembic revision --autogenerate -m "add foo column"

# roll back one step
alembic downgrade -1
```

`alembic/env.py` reads `DATABASE_URL` from the environment, so the same `.env` configures both the app and migrations.

A regression test (`tests/test_alembic.py::test_metadata_matches_migration`) runs `compare_metadata` and **fails CI if models drift from migrations** — so you can't accidentally ship a model change without a matching migration.

## Auth & RBAC

1. `POST /auth/register` - the **first user becomes admin**; everyone else self-registers as `viewer` (read-only).
2. `POST /auth/login` (form fields `username`+`password`) -> JWT
3. Send `Authorization: Bearer <token>` for all other endpoints.

Seeded login: **admin@example.com / admin123**

### Roles

| Role     | Read | Create / Update | Delete / Manage users |
|----------|:----:|:---------------:|:---------------------:|
| `viewer` | yes  | -               | -                     |
| `agent`  | yes  | yes             | -                     |
| `admin`  | yes  | yes             | yes                   |

Admin-only endpoints:

```
GET    /auth/users                       # list all users
PATCH  /auth/users/{user_id}/role        # promote / demote (body: {"role": "agent"})
DELETE /customers/{id}                   # cascade delete
POST   /admin/run-billing-sweep          # manual sweep
POST   /admin/dispatch-notifications     # manual notification flush
```

The `role` column was added in Alembic revision `78cb5b6ea99e` and is backfilled
from the legacy `is_admin` boolean. `is_admin` is kept in sync with `role == admin`
for back-compat with older clients.

### Rate limits

`POST /auth/login` and `POST /auth/register` are throttled with **slowapi**, keyed
by remote IP. Defaults: `10/minute` for login, `5/minute` for register. Configure
via `RATE_LIMIT_LOGIN`, `RATE_LIMIT_REGISTER`. Disable globally with
`RATE_LIMIT_ENABLED=0` (the test suite does this).

Behind a proxy / load balancer, ensure the real client IP reaches FastAPI
(e.g. uvicorn `--proxy-headers --forwarded-allow-ips '*'`), otherwise every
request will share the proxy's bucket.

### Production hardening

Set `PRODUCTION=1` in your deployment env. The app will then refuse to start if:

- `JWT_SECRET` is missing, equals the placeholder default, or is shorter than 32 chars.

Generate a strong key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Observability

### Prometheus `/metrics`

`prometheus-fastapi-instrumentator` exposes the standard HTTP metrics at
`GET /metrics` (no auth by default; flip `METRICS_REQUIRE_ADMIN=1` to put it
behind admin). `/health` and `/metrics` itself are excluded from the
histogram to keep cardinality sane.

Custom business gauges, updated by every billing sweep:

| Metric                      | Type  | Meaning                              |
|-----------------------------|-------|--------------------------------------|
| `mandlzi_active_policies`   | Gauge | Count of policies in `active` status |
| `mandlzi_lapsed_policies`   | Gauge | Count of policies in `lapsed` status |
| `mandlzi_inprogress_requests` | Gauge | Currently-executing HTTP requests |

Standard families also included: `http_requests_total`,
`http_request_duration_seconds_*`, `http_request_size_bytes_*`, etc.

### Access log

Every HTTP request emits one INFO line on the `mandlzi.access` logger:

```
method=GET path=/customers status=200 dur_ms=12.34 ip=10.0.0.4 user=42
```

The `user` field is the JWT `sub` claim when a valid `Authorization: Bearer`
header is present, `-` otherwise. Pipe stdout into any logfmt / JSON-line
parser. Disable in tests / quiet environments with `REQUEST_LOG_ENABLED=0`.

## Background scheduler

The app uses **APScheduler** to run a daily **billing sweep** at `SWEEP_HOUR_UTC:SWEEP_MINUTE_UTC` (default `02:00 UTC`). The sweep:

1. Re-evaluates every `active` policy (no need to wait for a UI request)
2. Emits `MISSED_PAYMENT` notifications for newly-overdue months (idempotent — won't duplicate)
3. Auto-lapses policies whose arrears cross the threshold (+ `POLICY_LAPSED` notification + audit log)
4. Marks customers `lapsed` once all their policies are lapsed

You can also trigger it manually:

```
POST /admin/run-billing-sweep            # admin only, returns the sweep report
POST /admin/run-billing-sweep?as_of=2025-12-01   # time-travel for testing
GET  /admin/scheduler                    # shows running jobs + next_run_time
```

Disable in tests or in multi-replica deployments (until a shared lock is added) with `SCHEDULER_ENABLED=0`.

## Notification delivery

`Notification` rows produced by the sweep (or anywhere else) start as unsent. A second scheduler job runs every `NOTIFICATION_DISPATCH_INTERVAL_MINUTES` minutes (default 5) and pushes them through the configured provider:

| Provider | Set `NOTIFICATION_PROVIDER=` | What it does |
| --- | --- | --- |
| **log** (default) | `log` | Writes the notification to the app log. Use in dev. |
| **webhook** | `webhook` + `NOTIFICATION_WEBHOOK_URL=https://...` | `POST`s a JSON body to the URL. Plug into Slack incoming webhooks, an integration backend, or a Twilio/SES facade. |

Each notification tracks `is_sent`, `sent_at`, `delivery_attempts`, and `last_error`. Failed sends are retried until `NOTIFICATION_MAX_ATTEMPTS` (default 5), then skipped — you can inspect them in the **Notifications** page in the dashboard, which now shows delivery status.

Manual trigger:

```
POST /admin/dispatch-notifications     # admin only, returns {scanned, sent, failed, skipped_max_attempts}
```

Adding a real SMS/email provider (Twilio, SES, Postmark) is a 30-line subclass — see `app/services/notification_providers.py`.

## Key endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/customers` | Create customer |
| GET  | `/customers/{id}` | Fetch customer |
| PATCH| `/customers/{id}` | Update |
| DELETE | `/customers/{id}` | Delete |
| GET  | `/customers/{id}/payment-status` | **Per-customer status** (optionally `?month=YYYY-MM`) |
| POST | `/policies` | Create policy |
| PATCH| `/policies/{id}` | Update policy (incl. per-policy rules) |
| POST | `/payments` | Record a payment |
| GET  | `/payments?customer_id=&policy_id=` | List payments |
| POST | `/members` | Add group-scheme member |
| GET  | `/members/policy/{id}/payment-status` | Per-member status |
| GET  | `/dashboard` | Summary metrics |
| GET  | `/audit-logs` | Audit trail |
| GET  | `/notifications` | Notifications |

## Payment status semantics

For each `(policy, month)` we classify:

- **PAID** - `sum(paid_payments_in_month) >= premium_amount`
- **PARTIAL** - some paid but less than premium, still within grace
- **NOT_PAID** - nothing paid, still within grace window
- **OVERDUE** - past `grace_period_days` of the month start and still under-paid

A policy auto-transitions to **lapsed** when `months_in_arrears >= lapse_threshold_months` (configurable globally via env or per-policy in the DB). A customer becomes **lapsed** when all their policies have lapsed.

## Business rules

Global defaults (env):

```
GRACE_PERIOD_DAYS=30
LAPSE_THRESHOLD_MONTHS=3
```

Per-policy overrides live on `policies.grace_period_days` and `policies.lapse_threshold_months`.

## Group schemes

A `policy_type=group_scheme` policy can have many `members`. Payments can optionally reference a `member_id`. `GET /members/policy/{id}/payment-status` returns per-member PAID/NOT_PAID/OVERDUE using each member's `contribution_amount` (or the policy premium as fallback).

## Tests

```bash
pytest -q
```

Covers:

- pure billing logic: expected months, classification (PAID/NOT_PAID/OVERDUE/PARTIAL), grace, lapse threshold, failed-payment exclusion
- API: auth required, fully-paid customer, overdue + auto-lapse side effect, month filter, group scheme member status

## Sample data

`scripts/seed.py` creates:

- **Sipho Dlamini** - fully paid 6 months
- **Thandi Nkosi** - in arrears, only 2 of 6 months paid
- **Mandla Mthembu** - group scheme of 3 members with varying coverage

## Frontend (React dashboard)

A Vite + React + TypeScript + Tailwind admin dashboard lives in `frontend/`.

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173 (proxies /api -> http://127.0.0.1:8000)
npm run build   # type-check + production bundle into frontend/dist
```

Make sure the FastAPI backend is running on port 8000 first (`uvicorn app.main:app --reload`). Sign in with the seeded **admin@example.com / admin123**, or click **Register** to create your own account (first user becomes admin).

##~~# Pages~~✓ dnepluggable prvider iterface + `og`and `webook` implemntations;ubclss `NoifiationProvid` toaddTwlo/SES

- **Dashboard** - summary cards, revenue progress bar, recent notifications
- **Customers** - searchable list, click through to detail
- **Customer detail** - profile, per-policy month-by-month status grid, group-scheme members, payments timeline, inline forms to add policy / add member / delete customer
- **Record payment** - cascading selects (customer → policy → optional member), auto-fills the premium
- **Notifications** - chronological feed of system-generated alerts
- **Audit log** - last 100 mutating actions with details

### How it talks to the backend

Vite dev server proxies `/api/*` → `http://127.0.0.1:8000/*` so you avoid CORS in dev. The API client (`src/api/client.ts`) stores the JWT in `localStorage` under `mandlzi.token`. For prod, build the SPA and serve `frontend/dist` behind the same domain (or set up a real reverse proxy).

## Production hardening checklist

- ~~Switch `init_db()` to Alembic migrations~~ ✓ done — set `RUN_INIT_DB=0` and use `alembic upgrade head`
- ~~Daily background sweep~~ ✓ done — APScheduler runs `run_billing_sweep` at `SWEEP_HOUR_UTC`; also exposed via `POST /admin/run-billing-sweep`
- ~~Set a strong `JWT_SECRET`~~ ✓ done — set `PRODUCTION=1` to refuse boot with the default / short (<32 char) secret
- ~~Rate limiting on `/auth/login`~~ ✓ done — slowapi limits configurable via `RATE_LIMIT_LOGIN` / `RATE_LIMIT_REGISTER` (defaults `10/minute` and `5/minute`), toggle off with `RATE_LIMIT_ENABLED=0`
- Wire the existing `Notification` rows to a real SMS/email provider (Twilio, SES) — only the dispatcher is missing
- ~~Add request logging & metrics~~ ✓ done — structured access log + Prometheus `/metrics` (toggle via `REQUEST_LOG_ENABLED`, `METRICS_ENABLED`)
- For multi-replica deploys: add a shared lock around the sweep job (DB advisory lock or single dedicated worker)
