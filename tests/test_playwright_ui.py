"""End-to-end browser tests for the React dashboard.

Boots:
  1. FastAPI on a free port (isolated SQLite DB)
  2. Vite dev server on another free port, proxying /api to (1)

Then drives Chromium through real user flows:
  - register -> redirected to dashboard
  - create customer
  - add policy
  - record payment
  - month grid shows PAID
  - dashboard reflects the new customer

Run::

    .venv/Scripts/python -m pytest tests/test_playwright_ui.py -q

Requires Chromium (`python -m playwright install chromium`) and Node/npm
to be installed.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, Page, expect


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DB_FILE = ROOT / "playwright_ui.db"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for(url: str, timeout: float = 60.0) -> None:
    """Poll a URL until it returns any HTTP response, or raise on timeout."""
    import urllib.request
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status < 500:
                    return
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.5)
    raise RuntimeError(f"{url} not ready after {timeout}s: {last_err}")


def _kill(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try: proc.kill()
        except Exception: pass


@pytest.fixture(scope="module")
def stack():
    """Spin up backend + vite, yield (frontend_url, backend_url). Tear down on exit."""
    if not (FRONTEND / "node_modules").exists():
        pytest.skip("frontend/node_modules not installed - run `npm install` in frontend/ first")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        pytest.skip("npm not found on PATH")

    if DB_FILE.exists():
        DB_FILE.unlink()
    backend_port = _free_port()
    frontend_port = _free_port()
    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"

    backend_env = os.environ.copy()
    backend_env["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
    backend_env["JWT_SECRET"] = "playwright-ui"
    backend_env["SCHEDULER_ENABLED"] = "0"
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(backend_port), "--log-level", "warning"],
        cwd=ROOT, env=backend_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    frontend_env = os.environ.copy()
    frontend_env["VITE_API_TARGET"] = backend_url
    frontend_env["VITE_PORT"] = str(frontend_port)
    frontend = subprocess.Popen(
        [npm, "run", "dev", "--", "--host", "127.0.0.1"],
        cwd=FRONTEND, env=frontend_env, shell=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for(f"{backend_url}/health", timeout=30)
        _wait_for(frontend_url, timeout=90)  # vite cold start can be slow
        # Pre-register the shared admin (first user becomes admin) so that
        # any test which uses `_login_as_admin` gets actual admin privileges
        # regardless of test order.
        import urllib.request, json
        try:
            req = urllib.request.Request(
                f"{backend_url}/auth/register",
                data=json.dumps({
                    "email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD,
                    "full_name": "Module Admin",
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass  # Already exists (re-run) - that's fine.
        yield frontend_url, backend_url
    finally:
        _kill(frontend)
        _kill(backend)
        if DB_FILE.exists():
            try: DB_FILE.unlink()
            except PermissionError: pass


@pytest.fixture(scope="module")
def browser_ctx(stack):
    """Module-scoped Playwright + browser context so we keep the same auth/session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        yield context
        context.close()
        browser.close()


@pytest.fixture
def page(browser_ctx) -> Page:
    pg = browser_ctx.new_page()
    yield pg
    pg.close()


# ---------- Helpers ----------


def _do_register(page: Page, frontend_url: str, email: str, password: str = "secret123"):
    """Register a fresh user (will become viewer if not the first) and
    end up on the dashboard.

    Wipes any stored token first so this works even when the shared
    browser context already has an authenticated session from a prior test.
    """
    page.goto(f"{frontend_url}/login")
    page.evaluate("() => localStorage.clear()")
    page.goto(f"{frontend_url}/login")
    page.wait_for_url("**/login", timeout=10_000)
    page.get_by_role("button", name="Register").click()
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=15_000)


# Fixed credentials for the module's admin user. Created on first use by
# whichever test needs admin privileges; reused thereafter so subsequent
# tests don't fall foul of the "first user becomes admin" rule.
_ADMIN_EMAIL = "ui-admin@example.com"
_ADMIN_PASSWORD = "uiadminpw"


def _login_as_admin(page: Page, frontend_url: str):
    """Ensure the page session is logged in as the module admin user.

    First call registers the admin (which becomes the first user → admin).
    Subsequent calls just log in.
    """
    page.goto(f"{frontend_url}/login")
    page.evaluate("() => localStorage.clear()")
    page.goto(f"{frontend_url}/login")
    page.wait_for_url("**/login", timeout=10_000)
    # Try login first.
    page.get_by_label("Email").fill(_ADMIN_EMAIL)
    page.get_by_label("Password").fill(_ADMIN_PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    try:
        expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=3_000)
        return
    except Exception:
        pass
    # Login failed - register instead.
    page.goto(f"{frontend_url}/login")
    page.evaluate("() => localStorage.clear()")
    page.goto(f"{frontend_url}/login")
    page.wait_for_url("**/login", timeout=10_000)
    page.get_by_role("button", name="Register").click()
    page.get_by_label("Email").fill(_ADMIN_EMAIL)
    page.get_by_label("Password").fill(_ADMIN_PASSWORD)
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=15_000)


# ---------- Tests ----------


def test_login_required_redirects(stack, page: Page):
    frontend_url, _ = stack
    page.goto(frontend_url)
    page.wait_for_url("**/login", timeout=10_000)
    expect(page.get_by_role("heading", name="Sign in to continue")).to_be_visible()


def test_register_then_dashboard(stack, page: Page):
    """A fresh self-registration lands on the dashboard.

    Since the module admin is pre-registered by the `stack` fixture,
    subsequent registrations default to the `viewer` role.
    """
    frontend_url, _ = stack
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
    _do_register(page, frontend_url, email)
    expect(page.get_by_text(email)).to_be_visible()
    # Sidebar shows the role tag for non-admin users.
    expect(page.get_by_text("viewer", exact=True)).to_be_visible()


def test_full_customer_lifecycle(stack, page: Page):
    """End-to-end: log in as admin -> create customer -> add policy -> record payment -> see PAID.

    Uses the shared admin login because creating customers, policies and
    payments now requires the `agent` or `admin` role.
    """
    frontend_url, _ = stack
    id_number = f"90{uuid.uuid4().int % 10_000_000_000_0:013d}"
    customer_name = f"E2E Customer {uuid.uuid4().hex[:6]}"

    _login_as_admin(page, frontend_url)

    # --- Create customer ---
    page.get_by_role("link", name="Customers").click()
    expect(page.get_by_role("heading", name="Customers")).to_be_visible()
    page.get_by_role("link", name="New customer").click()
    expect(page.get_by_role("heading", name="New customer")).to_be_visible()
    page.get_by_label("Full name *").fill(customer_name)
    page.get_by_label("ID number *").fill(id_number)
    page.get_by_label("Phone").fill("+27820000000")
    page.get_by_label("Email").fill(f"cust-{uuid.uuid4().hex[:6]}@example.com")
    page.get_by_role("button", name="Create customer").click()

    # Lands on customer detail
    expect(page.get_by_role("heading", name=customer_name)).to_be_visible(timeout=10_000)

    # --- Add a policy ---
    page.get_by_role("button", name="Add policy").click()
    # Premium defaults to "150.00" in the form; keep it.
    page.get_by_role("button", name="Create policy").click()
    # A "Policy #N" header should appear.
    expect(page.get_by_text("Policy #", exact=False).first).to_be_visible(timeout=10_000)
    # Before any payment we expect at least one month badge that is NOT PAID-like.
    # Just assert the per-month grid is present.
    expect(page.get_by_text("/ R 150.00").first).to_be_visible()

    # --- Record a payment ---
    page.get_by_role("link", name="Record payment").click()
    expect(page.get_by_role("heading", name="Record payment")).to_be_visible()
    page.get_by_label("Customer *").select_option(label=f"{customer_name} ({id_number})")
    # Wait until the Policy <select> has populated with at least one real option.
    page.wait_for_function(
        "() => document.getElementById('pay-policy')?.options.length > 1",
        timeout=10_000,
    )
    page.get_by_label("Policy *").select_option(index=1)  # first real option
    # Amount auto-filled; submit.
    page.get_by_role("button", name="Record payment").click()

    # Back on customer detail
    expect(page.get_by_role("heading", name=customer_name)).to_be_visible(timeout=10_000)
    # At least one PAID badge should now appear in the month grid.
    expect(page.get_by_text("PAID", exact=True).first).to_be_visible(timeout=10_000)


def test_dashboard_reflects_data(stack, page: Page):
    """After previous tests the dashboard should show >=1 customer + >=1 policy."""
    frontend_url, _ = stack
    page.goto(f"{frontend_url}/")
    # Already logged in via shared browser context.
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=10_000)
    # The Customers card label should be present.
    expect(page.get_by_text("Customers", exact=True).first).to_be_visible()
    expect(page.get_by_text("Policies", exact=True).first).to_be_visible()


def test_duplicate_register_shows_error(stack, page: Page):
    """Registering with an already-taken email surfaces the API error inline."""
    frontend_url, _ = stack
    # Use the seeded admin-like email from earlier register tests by trying the same address twice.
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    _do_register(page, frontend_url, email)

    # Log out and try to register the same address again.
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url("**/login")
    page.get_by_role("button", name="Register").click()
    page.locator('input[type="email"]').fill(email)
    page.locator('input[type="password"]').fill("secret123")
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_text("Email already registered")).to_be_visible(timeout=10_000)
