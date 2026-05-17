# Field Capture App — Design

- **Date:** 2026-05-17
- **Status:** Approved (pending written-spec review)
- **Owner:** kutulloaustin@gmail.com
- **Project:** Mandlzi monthly-contribution platform

## 1. Problem & Motivation

Field workers currently capture new funeral-cover clients on paper. The paper flow is slow, error-prone, hard to audit, and creates a multi-day delay between a client signing up in the township and the policy actually existing in the back-office system. Cash collected for the first month is reconciled by hand, with no per-transaction digital evidence.

We need a **mobile-first capture app** that field workers can use on a phone in the field, often without mobile signal, to:

1. Sign up a new client (main member + dependents + beneficiaries) under a chosen cover plan.
2. Capture a photo of the client's ID as proof.
3. Optionally take the first month's payment in cash and produce a receipt.
4. Sync the captured data to the existing Mandlzi backend when signal returns, with the client becoming an active policyholder immediately on sync (no admin approval gate).
5. Share the receipt with the client via WhatsApp (offline-capable) or email (sent server-side after sync).

The platform itself — cover plans, policies, members, beneficiaries, payments, the "miss 3 months → lapse" rule via daily billing sweep — already exists in this repo. This design adds a **field-capture path** that feeds the existing system. Existing models (`Customer`, `Policy`, `Member`, `Beneficiary`, `Payment`, `CoverPlan`) are not modified, except for two additive nullable FK columns for traceability.

## 2. Goals

- Field worker can sign up a new client end-to-end on a phone, with no signal, in under five minutes.
- Captured data + ID photo + first-payment receipt sync reliably when signal returns.
- Same submission posted twice (retry after a network blip) does not create duplicate customers, policies, or payments.
- Client receives a receipt via WhatsApp on the spot (offline) and via email once the phone syncs (if they gave an email).
- Phone can be revoked from the admin tool if lost or stolen, preventing further captures.

## 3. Non-Goals

- Per-worker individual login or personal credentials (the device is the actor).
- Digital signature capture (ID photo is the proof artifact).
- Admin approval queue between capture and policy activation.
- Door-to-door monthly collections (only the first-payment-on-signup is in scope).
- Bluetooth thermal printer support.
- Native iOS / Android app (PWA only — see Section 4 on architectural choice).

## 4. Architecture (chosen approach)

A **Progressive Web App** added to the existing `frontend/` (React + Vite + Tailwind) under a new route namespace `/field/*`. The PWA uses Workbox for the Service Worker, `idb` for IndexedDB access, and the existing React Router. The backend gains a small new module `app/api/field.py` with five endpoints under `/api/field/*`, plus three new SQLAlchemy models. The existing `app/services/cover_signup.py` service is reused unchanged.

**Why PWA, not native:**

- Reuses the team's existing React/Vite/Tailwind stack — one codebase, one build, one deployment.
- No app store review delays on every release.
- Native camera, file system, share-sheet, and offline storage are all reachable from a PWA on Android (the primary target).
- iOS PWA storage limits (~50 MB) are not a binding constraint at the design's photo size (~200 KB compressed per ID).
- A separate React Native app was considered and rejected: introduces a second codebase + build pipeline + skill set with no existing repo footprint, and the failure mode for a missing native feature is "rewrite" rather than "polyfill".

## 5. Data Model

### 5.1 New tables

#### `devices`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `name` | String(80) | Human-readable, e.g. `Phone-01` |
| `token_hash` | String(128) | bcrypt hash of the JWT's `jti` (so leaked DB doesn't leak active tokens) |
| `status` | Enum(`active`, `revoked`) | |
| `enrolled_at` | DateTime | |
| `last_seen_at` | DateTime nullable | Updated on every authenticated request |

#### `device_enrollment_codes`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `code` | String(6) unique | Alphanumeric, uppercase |
| `created_by_user_id` | FK → users.id | The admin who generated it |
| `created_at` | DateTime | |
| `expires_at` | DateTime | `created_at + 24h` |
| `consumed_at` | DateTime nullable | Set when code is exchanged for a device JWT |
| `consumed_by_device_id` | FK → devices.id nullable | |

#### `field_submissions`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `device_id` | FK → devices.id | |
| `client_uuid` | String(36) | UUIDv4 generated on the phone |
| `submitted_at` | DateTime | Server receipt time |
| `signups_count` | Integer | |
| `payments_count` | Integer | |
| `status` | Enum(`processed`, `partial`, `failed`) | `partial` = some signups in batch succeeded, some failed |
| `error_message` | Text nullable | |
| `raw_payload` | JSONB | Full original submission, for diagnostics |

Unique constraint: `(device_id, client_uuid)`. This is the idempotency key.

### 5.2 Additive columns on existing tables

- `customers.id_photo_path` — `String(255)` nullable. Filesystem path under `media/id_photos/`.
- `policies.field_submission_id` — `Integer FK → field_submissions.id` nullable.
- `payments.field_submission_id` — `Integer FK → field_submissions.id` nullable.
- `beneficiaries.title` — `String(8)` nullable. Title to match the source sketches and the corresponding `members.title` column.
- `beneficiaries.gender` — `String(16)` nullable.
- `beneficiaries.date_of_birth` — `Date` nullable.
- `beneficiaries.nationality` — `String(80)` nullable.
- `beneficiaries.email` — `String(255)` nullable.

All columns are nullable additive. Existing rows remain valid. No data migration needed. The five new `beneficiaries` columns close the gap identified between the source sketches (which list those fields on page 2) and the current `Beneficiary` model. The existing back-office wizard ([`NewCustomerPage.tsx`](../../../frontend/src/pages/NewCustomerPage.tsx)) is updated to surface these new fields as part of this work so the admin and field paths stay in parity.

### 5.3 Photo storage

ID photos are stored on the filesystem at `media/id_photos/<uuid>.jpg`, accessed via a storage-adapter abstraction:

```python
class PhotoStorage(Protocol):
    def save(self, blob: bytes, ext: str) -> str: ...    # returns path
    def load(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...

class FilesystemPhotoStorage:  # used in production today
    ...

class S3PhotoStorage:  # placeholder for future swap
    ...
```

The adapter is bound at app startup based on `settings.PHOTO_STORAGE_BACKEND`. Swapping to S3 in the future is one config change + one new class, no changes to consumers.

## 6. Backend API

All endpoints under `/api/field/*` except `/enroll` require `Authorization: Bearer <device_jwt>`.

### 6.1 `POST /api/field/enroll`

**Auth:** none (the code itself is the credential).

**Request:**
```json
{ "code": "K3MZ9P", "name": "Phone-01" }
```

**Response 200:**
```json
{
  "device_id": 7,
  "name": "Phone-01",
  "device_jwt": "eyJ..."
}
```

**Errors:** 400 if code expired/consumed/unknown.

**Side effects:** marks `device_enrollment_codes` row consumed, creates `devices` row, signs JWT.

### 6.2 `GET /api/field/cover-plans`

**Auth:** device JWT.

**Response 200:**
```json
{
  "plans": [
    {
      "id": 1,
      "category": "me_and_family",
      "cover_type": "Me and My Family",
      "monthly_premium": "360.00",
      "max_dependents": 4,
      "description": "Covers main member + 4 dependents."
    }
  ]
}
```

Phone caches this via service-worker stale-while-revalidate.

### 6.3 `POST /api/field/photos`

**Auth:** device JWT.

**Request:** `multipart/form-data` with one `file` field. JPEG or PNG only, max 5 MB.

**Response 200:**
```json
{ "id_photo_id": "a3f1c2b8-...", "path": "media/id_photos/a3f1c2b8-....jpg" }
```

Server validates MIME type, writes via storage adapter, returns the opaque `id_photo_id` (which is the path's UUID portion).

### 6.4 `POST /api/field/submissions`

**Auth:** device JWT.

**Request:**
```json
{
  "client_uuid": "5a8d3e2c-...",
  "signups": [
    {
      "local_id": "1",
      "cover_plan_id": 1,
      "holder": { "title": "Mr", "first_names": "...", "surname": "...", "id_number": "...", "date_of_birth": "1980-01-15", "gender": "M", "nationality": "ZA", "email": "...", "cellphone": "...", "country_of_birth": "ZA" },
      "id_photo_id": "a3f1c2b8-...",
      "dependents": [ { "title": "...", "first_names": "...", "surname": "...", "relationship_to_holder": "Spouse", "date_of_birth": "...", "gender": "...", "nationality": "...", "email": "...", "cellphone": "...", "country_of_birth": "..." } ],
      "beneficiaries": [ { "relationship_to_holder": "Daughter", "title": "Ms", "first_name": "...", "surname": "...", "gender": "F", "date_of_birth": "...", "nationality": "...", "email": "...", "cellphone": "...", "country_of_birth": "...", "share_pct": "100.00" } ],
      "first_payment": { "amount": "360.00", "method": "cash", "reference": "FLD-...", "payment_date": "2026-05-17" },
      "email_receipt_requested": true
    }
  ]
}
```

**Response 200:**
```json
{
  "field_submission_id": 42,
  "results": [
    { "local_id": "1", "status": "ok", "customer_id": 101, "policy_id": 55, "payment_id": 88 }
  ]
}
```

Or for a partial failure:
```json
{
  "field_submission_id": 42,
  "results": [
    { "local_id": "1", "status": "ok", "customer_id": 101, "policy_id": 55 },
    { "local_id": "2", "status": "error", "error": "Beneficiary share_pct must sum to 100 (got 99.5)." }
  ]
}
```

**Idempotency:** if a row with `(device_id, client_uuid)` already exists, the server returns the previously-stored response without re-processing.

**Processing:** for each signup, the server calls the existing `app.services.cover_signup.perform_cover_signup(...)` and, if a `first_payment` is present, inserts a `Payment` row linked to the new policy. The `field_submission_id` is stamped on each created `Policy` and `Payment`. The `id_photo_id` is resolved to a filesystem path and stored on the `Customer.id_photo_path`. An email-receipt notification is queued **if and only if** the signup payload includes `email_receipt_requested: true` (set by the worker tapping **Email me** on the receipt screen) **and** `holder.email` is present. This makes the email opt-in: capturing an email for contact purposes does not auto-trigger a receipt send.

### 6.5 `GET /api/field/submissions/{client_uuid}`

**Auth:** device JWT.

**Response 200:** identical shape to the POST response, looked up by `(device_id, client_uuid)`.

**Use case:** the phone sent a submission, didn't receive a response (network dropped), and wants to know if it landed before retrying.

### 6.6 Auth dependency

A new dependency `get_current_device` in `app/api/deps.py`:

- Decodes the JWT.
- Asserts `type == "device"` and `sub` starts with `device:`.
- Looks up `devices` row, asserts `status == active`.
- Updates `last_seen_at`.
- Returns the `Device` ORM object.

A device JWT presented to any non-`/api/field/*` route is rejected by the existing `get_current_user` dependency (different `type` claim). Conversely, a user JWT presented to `/api/field/*` is rejected by `get_current_device`. **Token-type firewall.**

## 7. Frontend (Field App)

### 7.1 Route layout

```
/field
├── /field/enroll                  # one-time enrollment screen
├── /field                         # home (after enrollment)
├── /field/signup/cover-category
├── /field/signup/cover-type
├── /field/signup/holder
├── /field/signup/id-photo
├── /field/signup/dependents
├── /field/signup/beneficiaries
├── /field/signup/payment
├── /field/signup/review
├── /field/signup/receipt
├── /field/sync                    # queue + manual sync controls
└── /field/settings                # device name, sign out, reset
```

### 7.2 Wizard

Single React context `FieldSignupContext` holds the in-progress signup. Every step change writes the context to a `drafts` IndexedDB store keyed by a stable local draft id, so a tab kill or browser crash mid-signup never loses work. On `/field/signup/receipt` (successful queue), the draft is moved to `pending_submissions` and removed from `drafts`.

UI conventions:

- Tailwind for styling, matching the existing admin app.
- React Hook Form per screen, validated with zod schemas shared between frontend and backend (Pydantic on the backend mirrors the same shape).
- Native HTML form controls (`<input type="date">`, `<select>`, `<input type="tel">`) — they get OS-native pickers on phones and beat custom JS for accessibility.
- Persistent offline banner at the top of every screen when `!navigator.onLine`.
- Sync badge in the header showing `pending_submissions.length`.
- One primary CTA per screen, full-width, anchored to the bottom safe-area.

### 7.3 Beneficiary form

The field-app beneficiary form captures all eleven fields shown on page 2 of the source sketches (relationship, title, first name, surname, gender, date of birth, nationality, email, cellphone, country of birth, share %). The five columns being added to the `Beneficiary` model to support this are listed in Section 5.2.

### 7.4 ID photo capture

The capture screen uses an `<input type="file" accept="image/*" capture="environment">` for cross-platform support — opens the back camera on most phones, falls back to a file picker on desktop / older browsers. On capture, the image is rendered to a `<canvas>` at max 1024×1024, re-encoded as JPEG at quality 0.7, and stored as a `Blob` in `pending_submissions[i].photo_blob`. Worker is shown a preview with **Retake** and **Use this photo** buttons.

### 7.5 Receipt screen

Renders the receipt to an off-screen `<canvas>` at 1080×1500, converts to a `Blob`, and offers two actions:

1. **Share via WhatsApp** → `navigator.share({ files: [receiptFile], title: 'Your Mandlzi receipt', text: '...' })`. Phone shows native share-sheet → user picks WhatsApp.
2. **Email me** → tags the submission with `email_receipt_requested: true`; server sends the PDF when the submission is processed.

The PNG is also written to a `receipts` IndexedDB store, keyed by `client_uuid`, kept 30 days. The Sync screen lists past receipts with a **Re-share** button.

**Fallback:** if `navigator.canShare?.({ files })` is false, the screen shows the rendered receipt inline with a long-press hint ("Long-press to save or share") plus a **Download** button.

## 8. Offline Mechanics

### 8.1 Service Worker (Workbox via `vite-plugin-pwa`)

- **App shell** (HTML, JS, CSS, icons, fonts): cache-first, max age 30 days, updated on each build via the SW skipWaiting + clientsClaim pattern.
- `GET /api/field/cover-plans`: stale-while-revalidate, max age 24h.
- All other API calls: network-only.
- `POST /api/field/*`: network-only (never cached).

### 8.2 IndexedDB

Database `mandlzi_field`, version 1, accessed via the `idb` wrapper:

| Object store | Key | Value shape |
|---|---|---|
| `device` | `'singleton'` | `{ device_id, name, jwt, enrolled_at, last_seen_sync_at }` |
| `cover_plans_cache` | `'singleton'` | `{ plans: [...], fetched_at }` |
| `drafts` | auto-increment | `{ id, context_state, last_step, updated_at }` |
| `pending_submissions` | `client_uuid` | `{ client_uuid, payload, photo_blob?, status, attempts, created_at, last_error? }` |
| `receipts` | `client_uuid` | `{ client_uuid, png_blob, created_at, expires_at }` |

### 8.3 Sync engine

A single async function `drainQueue()` in `frontend/src/pages/field/sync.ts`:

```
for each row in pending_submissions where status = 'queued':
  if row.photo_blob:
    POST /api/field/photos with the blob
    on 2xx: set row.payload.signups[].id_photo_id, drop row.photo_blob
    on error: leave row, bump attempts, return
  POST /api/field/submissions with row.payload
  on 2xx: mark row.status = 'synced', record server result, schedule deletion +24h
  on 4xx: mark row.status = 'failed', store error, surface in "Needs attention"
  on 5xx / network error: leave row, bump attempts, return
```

**Triggers** for `drainQueue`:
- `window.addEventListener('online', drainQueue)`
- `document.addEventListener('visibilitychange', () => visible && drainQueue())`
- After a successful submission queue (best-effort immediate ship).
- Manual **Sync now** button on `/field/sync` and the header badge.

**Deliberate non-use:** no Background Sync API (iOS Safari does not support it; building on top creates support gaps). No exponential-backoff loop (a phone that is asleep is the real bottleneck; user-driven + visibility-driven retry is sufficient).

### 8.4 Storage budgeting

- ID photos compressed to ~200 KB each.
- Worst-case pending capacity: 50 MB (iOS PWA budget) / 250 KB per signup envelope ≈ **200 unsynced signups**. A typical day is well under this.
- When `navigator.storage.estimate()` reports `>= 90%` usage, the home screen surfaces a yellow **"Phone almost full — sync soon"** banner.

## 9. Receipts

### 9.1 PNG (on phone, immediate, offline-capable)

Rendered to canvas at 1080×1500 from a render function `renderReceipt(ctx, data)` in `frontend/src/pages/field/receipt.ts`. Pure canvas — no library dependency.

### 9.2 PDF (on server, after sync, email)

Backend uses **WeasyPrint** to render a Jinja template at `app/templates/receipts/funeral_cover.html` to PDF. The template duplicates the visual layout of the PNG. Email goes out via the existing notification dispatcher with a new provider type `EMAIL_RECEIPT`.

Receipt content (both channels):

- Company name + logo header
- Title: **Funeral cover receipt**
- Date, reference code `MZ-<client_uuid_short>`
- Plan name + monthly premium
- Holder full name + ID number
- Amount paid · payment method · "First month" or "Month of YYYY-MM"
- Dependents covered (count + names)
- "Coverage active from <date>. Cover lapses after <N> consecutive missed monthly payments."
- Device name + capture timestamp

## 10. Device Auth Lifecycle

### 10.1 Enrollment

1. Admin → Devices → **Enroll new device** → server creates `device_enrollment_codes` row, returns the 6-char code, displays it on screen for 24h.
2. Worker opens field PWA → `/field/enroll` → enters code + friendly name.
3. Phone calls `POST /api/field/enroll` → server validates, creates `devices` row, returns device JWT.
4. Phone stores JWT in IndexedDB `device` store.

### 10.2 JWT

- Signed with same secret as user JWTs (`app/core/security.py`).
- Claims: `{ sub: "device:<id>", type: "device", name: "Phone-01", jti: "<random>", iat, exp }`.
- Lifetime: **180 days**.
- `token_hash` on the `devices` row is `bcrypt(jti)`, so a DB leak doesn't leak active tokens.

### 10.3 Revocation

- Admin sets `devices.status = revoked`.
- Next authenticated call from that phone returns 401 with body `{ "code": "DEVICE_REVOKED" }`.
- Field app intercepts, wipes `device` and `pending_submissions` and `receipts` stores, routes to `/field/enroll`.

### 10.4 Expiry

- On 401 with `{ "code": "DEVICE_TOKEN_EXPIRED" }`, app routes to `/field/enroll` and shows "Phone needs re-enrollment".
- No automatic refresh-token rotation. Can be added later as a refresh-on-sync mechanism without changing this design.

### 10.5 Threat model

| Attack | Defence |
|---|---|
| Random person guesses field URL | No token → 401 on every endpoint except `/enroll` (which needs a code) |
| Stolen phone | Admin revokes → next call 401 → phone wipes |
| Compromised device JWT used against admin routes | `get_current_user` rejects `type=device` tokens (firewall) |
| Worker submits fraudulent signups | Out of scope for this design — operational mitigation (cash reconciliation, audit-log spot checks) |
| DB leaks the `devices` table | `token_hash` is bcrypt of `jti`, not the JWT itself; attacker still needs the JWT secret |

## 11. Testing

Follows existing patterns in `tests/` and `frontend/src/`.

### 11.1 Backend (pytest + httpx)

- `tests/test_field_enrollment.py` — code generation, single-use, 24h expiry, double-enroll rejected, JWT claims.
- `tests/test_field_submission.py` — happy-path single + batch; **idempotency**; partial failure; duplicate ID number reuses customer.
- `tests/test_field_photo_upload.py` — multipart, size limit, MIME allowlist, storage adapter write path.
- `tests/test_field_auth.py` — token-type firewall (device→admin denied, user→field denied), revoked device → 401 + `DEVICE_REVOKED`.
- `tests/test_alembic.py` (extend) — new tables + additive columns migrate up + down cleanly.

All tests hit a real Postgres-via-SQLAlchemy test DB (no DB mocking — per `CLAUDE.md`).

### 11.2 Frontend (Vitest + React Testing Library)

New directory `frontend/src/pages/field/__tests__/`:

- Wizard state machine: forward/back preserves data; advance blocked on invalid required fields.
- Share-% live total + Submit disabled until = 100.
- IndexedDB queue: capture → row in `pending_submissions`; mocked fetch 2xx → row deleted; network error → row preserved with attempts bumped.
- Receipt PNG: canvas snapshot for a known input.
- Storage-full banner triggers at 90% usage (mocked `navigator.storage.estimate`).

### 11.3 End-to-end (Playwright)

Extending existing `test_playwright_*.py` patterns:

- `tests/test_playwright_field_signup.py` — full wizard on a 390×844 viewport; mocked camera input (fixed JPEG); asserts the customer + policy + member + beneficiary + payment rows exist with expected values.
- `tests/test_playwright_field_offline.py` — load shell online, go offline (`page.context.set_offline(true)`), capture a signup, come back online, assert the submission lands. **Critical test.**
- `tests/test_playwright_field_revoke.py` — enroll → queue a submission → admin revokes → next sync returns 401 → field app shows enrollment screen.

### 11.4 Manual smoke checklist

Before any release:

1. Install the PWA on a real Android phone from the dev URL.
2. Enroll with a code generated in the admin UI.
3. Airplane mode → capture a signup + photo + first payment → close app → reopen → confirm queued.
4. Re-enable signal → confirm auto-sync drains the queue.
5. Confirm WhatsApp share-sheet opens with the receipt PNG attached.
6. Check the holder's inbox for the emailed PDF.

## 12. Dependencies (new)

**Backend:**
- `weasyprint` — PDF rendering for emailed receipts.
- `Pillow` — server-side image validation + thumbnailing if needed.

**Frontend:**
- `vite-plugin-pwa` — Service Worker + manifest generation.
- `idb` — typed IndexedDB wrapper.

All four are mainstream, actively maintained, and have no incompatible licensing.

## 13. Out of Scope (deferred)

The following were considered and deliberately deferred. None of them require changes to this design's data model to add later:

- **Per-worker attribution** ("who's using the phone right now?" picker) — add a `worker_name` String column to `field_submissions`, no auth change.
- **Door-to-door monthly collections** — new endpoint `POST /api/field/collections`, new screens, reuses the rest.
- **Admin approval queue** — change `Policy.status` to include `pending`, add review screen.
- **Bluetooth thermal printer support** — new screen + Web Bluetooth integration.
- **Native iOS / Android app** — would replace the PWA but keep the backend unchanged.
- **S3 photo storage** — swap `FilesystemPhotoStorage` for `S3PhotoStorage` via config.
- **Refresh-token rotation for device JWTs** — replace fixed 180-day expiry with a rotation flow.

## 14. Acceptance Criteria

This design is "done" when:

1. A worker can install the PWA on an Android phone, enroll with an admin-generated code, and reach the home screen — fully offline after first install.
2. A worker can complete the wizard end-to-end with no signal: pick a cover plan (from cached list), enter holder + dependents + beneficiaries, take an ID photo, optionally take cash, see a receipt, share it via WhatsApp.
3. On signal return, the submission lands in the backend exactly once even if retried. The resulting `Customer`, `Policy`, `Member`, `Beneficiary`, `Payment` rows are correct.
4. The client receives the emailed PDF receipt if they gave an email.
5. An admin can revoke the phone from the admin UI; the next sync attempt from that phone is rejected and the app routes back to enrollment.
6. The phone never loses captured data short of being physically destroyed: a tab kill mid-signup preserves a draft; a sync failure preserves the queued submission until the worker manually clears it.
7. All new pytest, Vitest, and Playwright tests pass. The manual smoke checklist passes on a real Android phone.
