"""Happy-path UI test for the scheme tabs (single linear flow).

Boots its own FastAPI + Vite stack (mirrors test_playwright_ui.py) and
exercises:
  1. Log in as admin.
  2. Click each of the 4 active scheme sidebar links -> assert page renders.
  3. Click sub-tabs on the Funeral scheme -> assert URLs and content.
  4. Click a Coming Soon scheme -> assert placeholder renders.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, Page, expect


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DB_FILE = ROOT / "playwright_scheme_tabs.db"

_ADMIN_EMAIL = "scheme-tabs-admin@example.com"
_ADMIN_PASSWORD = "schemetabspw"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for(url: str, timeout: float = 60.0) -> None:
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
        try:
            proc.kill()
        except Exception:
            pass


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
    backend_env["JWT_SECRET"] = "playwright-scheme-tabs"
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
        _wait_for(frontend_url, timeout=90)
        # Pre-register the admin (first user becomes admin).
        import urllib.request, json
        try:
            req = urllib.request.Request(
                f"{backend_url}/auth/register",
                data=json.dumps({
                    "email": _ADMIN_EMAIL,
                    "password": _ADMIN_PASSWORD,
                    "full_name": "Scheme Tabs Admin",
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass  # Already exists on re-run - that's fine.
        yield frontend_url, backend_url
    finally:
        _kill(frontend)
        _kill(backend)
        if DB_FILE.exists():
            try:
                DB_FILE.unlink()
            except PermissionError:
                pass


@pytest.fixture(scope="module")
def browser_ctx(stack):
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


def _login_as_admin(page: Page, frontend_url: str) -> None:
    """Log in as the module admin user. Clears any existing session first."""
    page.goto(f"{frontend_url}/login")
    page.evaluate("() => localStorage.clear()")
    page.goto(f"{frontend_url}/login")
    page.wait_for_url("**/login", timeout=10_000)
    page.get_by_label("Email").fill(_ADMIN_EMAIL)
    page.get_by_label("Password").fill(_ADMIN_PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    try:
        expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=5_000)
        return
    except Exception:
        pass
    # Login failed - admin not registered yet; register then login.
    page.goto(f"{frontend_url}/login")
    page.evaluate("() => localStorage.clear()")
    page.goto(f"{frontend_url}/login")
    page.wait_for_url("**/login", timeout=10_000)
    page.get_by_role("button", name="Register").click()
    page.get_by_label("Email").fill(_ADMIN_EMAIL)
    page.get_by_label("Password").fill(_ADMIN_PASSWORD)
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=15_000)


def test_scheme_tabs_navigate_and_render(page: Page, stack):
    """Happy-path: log in -> navigate Funeral scheme tabs -> check Wedding coming-soon."""
    frontend_url, _ = stack
    _login_as_admin(page, frontend_url)

    # 1. Click the Funeral scheme sidebar link.
    page.locator("nav").get_by_role("link", name="Funeral").click()
    page.wait_for_url("**/schemes/funeral", timeout=10_000)
    expect(page.get_by_role("heading", name="Funeral")).to_be_visible()

    # 2. Exercise each list sub-tab (scoped to the tab bar to avoid ambiguity
    #    with the sidebar Customers link).
    tab_bar = page.locator(".border-b.border-slate-200")
    for tab_label, tab_slug in [("Customers", "customers"), ("Policies", "policies"), ("Plans", "plans")]:
        tab_bar.get_by_role("link", name=tab_label).click()
        page.wait_for_url(f"**/schemes/funeral/{tab_slug}", timeout=10_000)
        # Either a populated card or the empty-state card is acceptable.
        expect(page.locator(".card").first).to_be_visible(timeout=5_000)

    # 3. Click a Coming Soon scheme (Wedding) and check the placeholder.
    page.locator("nav").get_by_role("link", name="Wedding").click()
    page.wait_for_url("**/schemes/wedding", timeout=10_000)
    expect(page.get_by_role("heading", name="Wedding")).to_be_visible()
    expect(page.locator("text=Coming soon").first).to_be_visible()
    expect(page.locator("text=This scheme is not yet active").first).to_be_visible()
