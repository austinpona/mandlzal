"""RBAC tests: viewer/agent/admin enforcement on write endpoints."""
from fastapi.testclient import TestClient

from app.main import app


def _register(client: TestClient, email: str, password: str = "secret123") -> dict:
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def _login(client: TestClient, email: str, password: str = "secret123") -> str:
    r = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_first_user_is_admin_subsequent_are_viewer():
    """Bootstrap rule: only the very first registration is granted admin."""
    c = TestClient(app)
    first = _register(c, "admin@example.com")
    second = _register(c, "viewer@example.com")
    assert first["role"] == "admin" and first["is_admin"] is True
    assert second["role"] == "viewer" and second["is_admin"] is False


def test_viewer_cannot_write_admin_can():
    c = TestClient(app)
    _register(c, "admin@example.com")
    _register(c, "viewer@example.com")
    admin_token = _login(c, "admin@example.com")
    viewer_token = _login(c, "viewer@example.com")

    payload = {"full_name": "X Y", "id_number": "9001015009088"}

    # Viewer: 403 on create
    r = c.post("/customers", json=payload, headers=_auth(viewer_token))
    assert r.status_code == 403
    assert "role" in r.json()["detail"].lower()

    # Viewer can still READ the (empty) list
    r = c.get("/customers", headers=_auth(viewer_token))
    assert r.status_code == 200 and r.json() == []

    # Admin: 201 on create
    r = c.post("/customers", json=payload, headers=_auth(admin_token))
    assert r.status_code == 201
    customer_id = r.json()["id"]

    # Viewer can read the new customer
    r = c.get(f"/customers/{customer_id}", headers=_auth(viewer_token))
    assert r.status_code == 200

    # Viewer cannot patch or delete
    assert c.patch(f"/customers/{customer_id}", json={"phone": "+27820000000"},
                   headers=_auth(viewer_token)).status_code == 403
    assert c.delete(f"/customers/{customer_id}",
                    headers=_auth(viewer_token)).status_code == 403


def test_agent_can_write_but_not_delete():
    """Agents can create/update but only admins can delete or manage roles."""
    c = TestClient(app)
    _register(c, "admin@example.com")
    viewer = _register(c, "agent@example.com")
    admin_token = _login(c, "admin@example.com")

    # Promote viewer -> agent via admin endpoint
    r = c.patch(
        f"/auth/users/{viewer['id']}/role",
        json={"role": "agent"}, headers=_auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "agent" and r.json()["is_admin"] is False

    agent_token = _login(c, "agent@example.com")

    # Agent can create a customer
    r = c.post("/customers", json={"full_name": "A", "id_number": "9001015009089"},
               headers=_auth(agent_token))
    assert r.status_code == 201
    cid = r.json()["id"]

    # Agent can update
    r = c.patch(f"/customers/{cid}", json={"phone": "+27821111111"},
                headers=_auth(agent_token))
    assert r.status_code == 200

    # Agent cannot delete (admin-only)
    r = c.delete(f"/customers/{cid}", headers=_auth(agent_token))
    assert r.status_code == 403


def test_only_admin_can_promote_users_and_not_self_demote():
    c = TestClient(app)
    admin = _register(c, "admin@example.com")
    target = _register(c, "viewer@example.com")
    admin_token = _login(c, "admin@example.com")
    viewer_token = _login(c, "viewer@example.com")

    # Non-admins cannot list users or change roles
    assert c.get("/auth/users", headers=_auth(viewer_token)).status_code == 403
    r = c.patch(f"/auth/users/{target['id']}/role",
                json={"role": "admin"}, headers=_auth(viewer_token))
    assert r.status_code == 403

    # Admin can list
    r = c.get("/auth/users", headers=_auth(admin_token))
    assert r.status_code == 200 and len(r.json()) == 2

    # Admin cannot demote themselves
    r = c.patch(f"/auth/users/{admin['id']}/role",
                json={"role": "viewer"}, headers=_auth(admin_token))
    assert r.status_code == 400
    assert "demote yourself" in r.json()["detail"].lower()

    # Admin can promote target to admin
    r = c.patch(f"/auth/users/{target['id']}/role",
                json={"role": "admin"}, headers=_auth(admin_token))
    assert r.status_code == 200
    assert r.json()["role"] == "admin" and r.json()["is_admin"] is True

    # Newly-promoted user can now use admin endpoints
    new_admin_token = _login(c, "viewer@example.com")
    assert c.get("/auth/users", headers=_auth(new_admin_token)).status_code == 200


def test_unauthenticated_requests_are_401():
    """Bearer token is required even for read endpoints."""
    c = TestClient(app)
    assert c.get("/customers").status_code == 401
    assert c.post("/customers", json={}).status_code == 401


def test_invalid_role_value_rejected():
    c = TestClient(app)
    admin = _register(c, "admin@example.com")
    admin_token = _login(c, "admin@example.com")
    r = c.patch(f"/auth/users/{admin['id']}/role",
                json={"role": "superuser"}, headers=_auth(admin_token))
    assert r.status_code == 422

