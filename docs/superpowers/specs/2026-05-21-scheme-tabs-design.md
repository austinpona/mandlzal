# Scheme-Tabs UI — Design

**Status:** Approved, ready for implementation plan
**Date:** 2026-05-21
**Project:** Ntshembo @Nyoni / `mandlzi`
**Sub-project:** A (of A / B / C decomposition — see Background)

## 1. Background and goal

The client described his product as a set of tabs: **Funeral / Stokvel / Purchase / Goat purchase** (message 18/05 22:32), later broadened to include **Wedding / Party / Breeding / Farming** as separate schemes (message 18/05 23:23).

Today the funeral product is functionally complete (schema, signup wizard, monthly payment classification, 3-month auto-lapse, dashboard, audit, notifications, 120-day eligibility helper). What's missing is the **visible UI organization** the client described. Customers are listed in one flat page; there is no scheme axis.

This spec covers sub-project **A** of a three-part decomposition:

| Sub-project | Scope | Status |
| --- | --- | --- |
| **A. Scheme-tabs UI (this spec)** | Segment the UI by scheme. Show the existing funeral product + the existing livestock products in their scheme tabs. Stokvel and 4 "coming soon" schemes appear as nav entries. | Designed here |
| **B. Goal-savings engine** | Backend model + signup + payment-plan generator for member-pays-toward-a-target schemes. Powers Stokvel; will power Wedding / Party / Breeding / Farming later. | Future spec |
| **C. Per-goal-type customization** | Once B exists, give each goal type its own tab content (defaults, labels, payout semantics). | Future increments |

This spec makes the existing product *look* like the client's mental model and prepares the navigation that B and C will plug into.

## 2. Scope

### In scope
- A `SchemeType` enum with 8 values.
- An Alembic migration adding `CoverPlan.scheme_type` (Enum, NOT NULL), with backfill of existing rows.
- Updated `app/services/cover_seed.py` so every seeded plan declares its `scheme_type`.
- `?scheme_type=…` filter on the existing customers, policies, and plans list endpoints.
- A new `GET /schemes/{scheme_type}/overview` endpoint returning scheme-scoped counts.
- Frontend: sidebar "Schemes" group, scheme page with Overview / Customers / Policies / Plans sub-tabs, "Coming soon" placeholder for inactive schemes, real empty states for the active-but-empty Stokvel scheme.
- Backend tests + one happy-path Playwright UI test.

### Out of scope (deferred)
- The goal-savings engine (Stokvel scheme model, payment-plan generator, signup wizard). The Stokvel tab in this spec is **empty by design** — clicking it shows the scheme page with zero customers / zero policies / zero plans.
- Wedding / Party / Breeding / Farming content. Those four tabs render a "Coming soon" placeholder page.
- Per-scheme RBAC differences. Existing `require_admin` / `require_writer` / `get_current_user` dependencies are reused unchanged.
- Changes to the funeral signup wizard, the 120-day eligibility helper, or the daily billing sweep.

## 3. Decisions captured during brainstorming

| Decision | Value | Why |
| --- | --- | --- |
| Where scheme_type lives | New column on `CoverPlan` (Approach 2) | Right amount of structure for ~8 stable schemes. Cleaner than read-time derivation; lighter than a full `Scheme` table. |
| Enum values shipped | All 8 (funeral / stokvel / purchase / goat_purchase / wedding / party / breeding / farming) | Sidebar shows the full product roadmap from day 1; inactive ones go to a placeholder page. |
| Sidebar arrangement | New "Schemes" group; existing **Customers** entry kept as a cross-scheme view | Schemes are the primary axis; Customers is the admin-friendly catch-all. |
| API shape | Extend existing list endpoints with `?scheme_type=` filter | Less code, reuses existing tests. Only Overview is a new endpoint. |
| Scheme page structure | One shared React component with sub-tab routes: Overview / Customers / Policies / Plans | Familiar pattern; scales as schemes grow. |
| Overview content | Four cards (Customers / Policies / This month / Revenue) + a plans-count strip | Mirrors the global dashboard; no charts. |
| Migration shape | Single migration: add nullable → backfill → make NOT NULL | OK for the current single-environment deployment. |
| Test surface | Backend filter + overview + migration + seed + one Playwright UI happy-path | Playwright UI test is worth the existing flakiness because the scheme tabs are *the* visible feature. |

## 4. Data model

### 4.1 `SchemeType` enum

```python
# app/models/cover_plan.py (extend)
class SchemeType(str, enum.Enum):
    funeral = "funeral"
    stokvel = "stokvel"
    purchase = "purchase"
    goat_purchase = "goat_purchase"
    wedding = "wedding"
    party = "party"
    breeding = "breeding"
    farming = "farming"
```

### 4.2 `CoverPlan.scheme_type` column

```python
scheme_type = Column(Enum(SchemeType), nullable=False, index=True)
```

Indexed because the filter and overview endpoints query by it.

### 4.3 Backfill mapping (applied by the migration)

| Source row (CoverPlan) | `scheme_type` |
| --- | --- |
| `category` in (`me`, `me_and_family`, `parents_and_inlaws`, `extended_family`) | `funeral` |
| `category = livestock_benefits` AND `cover_type = "Cattle during funeral"` | `funeral` |
| `category = livestock_benefits` AND `cover_type = "Cattle in December"` | `purchase` |
| `category = livestock_benefits` AND `cover_type = "Sheep in December"` | `purchase` |
| `category = livestock_benefits` AND `cover_type = "Goat in December"` | `goat_purchase` |

No existing rows map to `stokvel / wedding / party / breeding / farming` — those scheme tabs are empty until the goal-savings engine ships.

### 4.4 Seed update

`_DEFAULT_PLANS` in `app/services/cover_seed.py` becomes a 6-tuple per row; every entry includes its `scheme_type`. The idempotency lookup stays on `(category, cover_type)`.

## 5. API

### 5.1 Extended list endpoints

| Endpoint | Filter behavior |
| --- | --- |
| `GET /customers?scheme_type={st}` | Returns customers that hold ≥1 `Policy` whose `cover_plan.scheme_type == st`. Distinct on customer_id. |
| `GET /policies?scheme_type={st}` | Returns policies where `cover_plan.scheme_type == st`. |
| `GET /cover-plans?scheme_type={st}` (existing handler in `app/api/cover.py`, currently filters by `?category=` and `?include_inactive=`) | Add `?scheme_type=` as a third optional filter. Endpoint stays public — same auth as today. |

`scheme_type` is validated by the existing Pydantic enum binding (unknown values → 422). Omitting the param preserves current behavior — no breaking change.

### 5.2 New endpoint: scheme overview

```
GET /schemes/{scheme_type}/overview
```

Response shape:

```json
{
  "scheme_type": "funeral",
  "label": "Funeral",
  "active_customers": 42,
  "lapsed_customers": 3,
  "active_policies": 47,
  "lapsed_policies": 5,
  "paid_this_month": 35,
  "unpaid_this_month": 7,
  "overdue_this_month": 5,
  "revenue_this_month": "12450.00",
  "expected_revenue_this_month": "18900.00",
  "plan_count": 9
}
```

Auth: `Depends(get_current_user)`. The implementation reuses `app/services/billing.compute_policy_status` / `get_payment_status_for_month` — the pure billing functions are unchanged.

For empty schemes (Stokvel, Wedding, etc.), every count is 0, revenue strings are `"0.00"`, `plan_count = 0`.

### 5.3 What's NOT changed

- `POST /cover/signup` — unchanged. The chosen `CoverPlan` already implies the scheme via its column.
- `POST /payments`, `/customers/{id}/payment-status` — unchanged.
- The daily billing sweep — unchanged. It's already per-policy.

## 6. Frontend

### 6.1 Sidebar

`frontend/src/components/Layout.tsx` gets a new "Schemes" group between **Customers** and **Record payment**:

```
Dashboard
Customers                  ← cross-scheme view, unchanged

─ Schemes ─
  Funeral                  ← active link
  Stokvel                  ← active link (empty data)
  Purchase                 ← active link
  Goat purchase            ← active link
  ──
  Wedding                  ← muted, routes to /schemes/wedding (placeholder)
  Party                    ← muted
  Breeding                 ← muted
  Farming                  ← muted

Record payment
Notifications
Audit log
Field app
Field devices              (admin only, unchanged)
```

The 4 "Coming soon" entries render in a muted style (e.g., `text-slate-500`) but are still clickable.

### 6.2 Routes

```
/schemes/:schemeType                  → Overview sub-tab (default)
/schemes/:schemeType/customers
/schemes/:schemeType/policies
/schemes/:schemeType/plans
```

`:schemeType` is validated client-side against the enum; unknown values render a 404-ish "Unknown scheme" page (no crash).

### 6.3 Scheme page component

One shared `SchemePage` React component, parameterized by the route param `schemeType`:

- Page header: scheme display label (e.g., "Funeral") + a small badge showing the scheme's status (`active` for the 4 with content, `coming-soon` for the others).
- For `coming-soon` schemes: no sub-tabs, just a single-paragraph placeholder ("This scheme is not yet active. Check back soon.").
- For `active` schemes: a top sub-tab bar (Overview / Customers / Policies / Plans). The content area swaps based on the sub-route.

### 6.4 Sub-tab content

| Sub-tab | What it shows | How |
| --- | --- | --- |
| **Overview** | Four cards (Customers / Policies / This month / Revenue) + plans-count strip | Fetches `GET /schemes/{type}/overview` |
| **Customers** | Filtered customers list | Reuses the existing customers list component / hook, passing `scheme_type={type}` |
| **Policies** | Filtered policies list | New light wrapper that calls `GET /policies?scheme_type={type}` |
| **Plans** | Cover plan catalog for this scheme | Calls the plan-list endpoint with the filter |

Empty Stokvel scheme:
- Overview: cards all show 0, plans strip says "0 plans configured — add one to begin."
- Customers / Policies tabs: "No customers yet" / "No policies yet" empty-state cards.
- Plans tab: "No plans configured for this scheme yet." with an "Add plan" button if the user has admin/writer role.

### 6.5 Components reused

- `StatusBadge`, `formatMoney`, `formatDate`, `formatMonth` — all unchanged.
- `CustomersPage` list → wrapped or reused with a scheme filter prop. If the existing component is hard to parameterize, fork a thin `<SchemeCustomersTab>` that calls the same hook with `scheme_type=` and renders the same row component.
- Card styling matches the existing `DashboardPage` cards (no new card primitive).

## 7. Testing

### 7.1 Backend (pytest)

| Test file | What | New / Extend |
| --- | --- | --- |
| `tests/test_alembic.py` (or new sibling) | Upgrade → assert `cover_plans.scheme_type` exists, NOT NULL, indexed. Downgrade → column gone. | Extend |
| `tests/test_cover_seed.py` | Seed a fresh DB → every row has `scheme_type`; mapping matches §4.3 (especially "Cattle during funeral" → `funeral`). | New |
| `tests/test_customers.py` | `?scheme_type=funeral` returns only funeral-holders; `?scheme_type=stokvel` returns `[]`; unknown value → 422. | Extend |
| `tests/test_policies.py` | Same filter semantics for policies. | Extend |
| `tests/test_schemes_overview.py` | Empty scheme → zeros, no error. Mixed dataset → counts segment correctly. Auth required. | New |

No changes to `test_payment_logic.py`, `test_billing_sweep.py`, `test_funeral_eligibility.py`, `test_rbac.py`, `test_security_hardening.py`.

### 7.2 Frontend (Playwright)

One new happy-path UI test in `tests/test_playwright_scheme_tabs.py`:

1. Log in (existing fixture).
2. Click each of the 4 active scheme links in the sidebar → assert the URL changes and the scheme label is visible in the page header.
3. Click one "Coming soon" scheme (e.g., Wedding) → assert placeholder text renders, sub-tabs absent.
4. On the Funeral scheme page, click each sub-tab (Customers / Policies / Plans) → assert URL updates and a recognizable element renders (e.g., the table header).

Accepted limitation: this test joins the existing Playwright tests, which are currently flaky in this branch's parent commit. Treat its first red as a flake-vs-real triage rather than auto-blocking the branch.

### 7.3 TypeScript and build gates

`npm run lint` and `npm run build` must pass — unchanged from current CI expectations.

## 8. File touch list (estimate)

```
# Backend — modify
app/models/cover_plan.py                                # add SchemeType, scheme_type column
app/services/cover_seed.py                              # add scheme_type per seed row
app/api/customers.py                                    # ?scheme_type= filter on list
app/api/policies.py                                     # ?scheme_type= filter on list
app/api/cover.py                                        # add ?scheme_type= filter to existing GET /cover-plans
app/api/__init__.py + app/main.py                       # wire new schemes router

# Backend — create
alembic/versions/<rev>_scheme_type.py                   # migration
app/api/schemes.py                                      # GET /schemes/{type}/overview
app/schemas/scheme.py                                   # SchemeOverviewResponse + scheme_type binding

# Tests — modify or create
tests/test_alembic.py (extend) / new migration test
tests/test_cover_seed.py (new)
tests/test_customers.py (extend)
tests/test_policies.py (extend)
tests/test_schemes_overview.py (new)
tests/test_playwright_scheme_tabs.py (new)

# Frontend — modify
frontend/src/components/Layout.tsx                      # add Schemes group
frontend/src/App.tsx                                    # add /schemes/:type/* routes

# Frontend — create
frontend/src/pages/SchemePage.tsx                       # shared scheme page with sub-tab routing
frontend/src/pages/scheme/OverviewTab.tsx
frontend/src/pages/scheme/CustomersTab.tsx
frontend/src/pages/scheme/PoliciesTab.tsx
frontend/src/pages/scheme/PlansTab.tsx
frontend/src/pages/scheme/ComingSoonScheme.tsx
frontend/src/types.ts                                   # add SchemeType, SchemeOverviewResponse types
```

## 9. Risks and mitigations

- **Plans-listing endpoint** is confirmed to be `GET /cover-plans` in `app/api/cover.py` (public, already supports `?category=` and `?include_inactive=`). Adding `?scheme_type=` is additive — no public-auth or response-shape change.
- **Playwright flakiness** on the parent commit is real (5 failing tests pre-exist). The new UI test risks adding a 6th flake. Mitigation: write the test as a single linear flow with explicit waits on stable selectors; if it flakes on first run, investigate (don't xfail per CLAUDE.md).
- **Reusing the Customers list component** may push it toward a "god component" if it has to know about scheme filtering AND cross-scheme view AND legacy-shape paths. Mitigation: keep the existing `CustomersPage` unchanged for the cross-scheme view; build a thin `SchemeCustomersTab` that calls the same hook with `scheme_type=`. If that becomes ugly, refactor in a follow-up — not in this slice.

## 10. Acceptance criteria

- All four active schemes (Funeral / Stokvel / Purchase / Goat purchase) are reachable from the sidebar and render their scheme page with the Overview sub-tab.
- The four "Coming soon" schemes render a placeholder page.
- `GET /schemes/funeral/overview` returns non-zero counts on a seeded test DB; `GET /schemes/stokvel/overview` returns all zeros without error.
- `GET /customers?scheme_type=funeral`, `GET /policies?scheme_type=funeral`, and `GET /cover-plans?scheme_type=funeral` each return only matching rows; unknown scheme value returns 422.
- `pytest` (excluding the pre-existing Playwright flakes) is green.
- `cd frontend && npm run lint && npm run build` both pass.
- The new Playwright happy-path test passes in at least 2 of 3 consecutive runs (treat one flake as a flake, not a regression).
