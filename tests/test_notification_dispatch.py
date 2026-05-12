"""Tests for notification providers + dispatcher + admin trigger."""
from datetime import datetime

import pytest

from app.models.notification import Notification
from app.services.notification_dispatcher import dispatch_pending_notifications
from app.services.notification_providers import (
    LogProvider, NotificationProvider, WebhookProvider, build_provider,
)


# ---------- helpers ----------


def _make_notification(db, customer_id=1, policy_id=1, type_="MISSED_PAYMENT",
                       message="test"):
    n = Notification(
        customer_id=customer_id, policy_id=policy_id,
        type=type_, message=message,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


class _FakeProvider(NotificationProvider):
    """In-test provider that records calls and can be forced to fail."""
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[Notification] = []
    def send(self, n):
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append(n)


# ---------- providers ----------


def test_log_provider_does_not_raise(caplog):
    n = Notification(customer_id=1, policy_id=1, type="X", message="hello",
                     created_at=datetime.utcnow())
    LogProvider().send(n)  # must not raise


def test_webhook_provider_requires_url():
    with pytest.raises(ValueError):
        WebhookProvider(url="")


def test_webhook_provider_raises_on_unreachable():
    # Reserved unassigned port should fail fast.
    p = WebhookProvider(url="http://127.0.0.1:1/never", timeout=0.5)
    n = Notification(customer_id=1, policy_id=1, type="X", message="hello",
                     created_at=datetime.utcnow())
    with pytest.raises(RuntimeError):
        p.send(n)


def test_build_provider_log_default(monkeypatch):
    monkeypatch.setattr("app.services.notification_providers.settings.NOTIFICATION_PROVIDER", "log")
    assert isinstance(build_provider(), LogProvider)


def test_build_provider_unknown_raises(monkeypatch):
    monkeypatch.setattr("app.services.notification_providers.settings.NOTIFICATION_PROVIDER", "nope")
    with pytest.raises(ValueError):
        build_provider()


# ---------- dispatcher ----------


def test_dispatch_marks_sent_on_success(db):
    n = _make_notification(db)
    provider = _FakeProvider()
    report = dispatch_pending_notifications(db, provider=provider)
    assert report.scanned == 1
    assert report.sent == 1
    assert report.failed == 0
    db.refresh(n)
    assert n.is_sent is True
    assert n.sent_at is not None
    assert n.delivery_attempts == 1
    assert n.last_error is None
    assert provider.sent == [n] or len(provider.sent) == 1


def test_dispatch_records_failure_and_does_not_mark_sent(db):
    n = _make_notification(db)
    report = dispatch_pending_notifications(db, provider=_FakeProvider(fail=True))
    assert report.failed == 1
    assert report.sent == 0
    db.refresh(n)
    assert n.is_sent is False
    assert n.delivery_attempts == 1
    assert "boom" in (n.last_error or "")


def test_dispatch_skips_already_sent(db):
    n = _make_notification(db)
    n.is_sent = True
    db.commit()
    provider = _FakeProvider()
    report = dispatch_pending_notifications(db, provider=provider)
    assert report.scanned == 0
    assert report.sent == 0
    assert provider.sent == []


def test_dispatch_skips_after_max_attempts(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.notification_dispatcher.settings.NOTIFICATION_MAX_ATTEMPTS", 2,
    )
    n = _make_notification(db)
    n.delivery_attempts = 2
    db.commit()
    report = dispatch_pending_notifications(db, provider=_FakeProvider(fail=True))
    assert report.skipped_max_attempts == 1
    assert report.failed == 0
    db.refresh(n)
    # Attempts unchanged, still not sent.
    assert n.delivery_attempts == 2
    assert n.is_sent is False


def test_dispatch_continues_past_a_failing_row(db):
    n1 = _make_notification(db, message="ok")
    n2 = _make_notification(db, message="will-fail")

    class FlakeyProvider(NotificationProvider):
        def send(self, n):
            if n.message == "will-fail":
                raise RuntimeError("nope")
    report = dispatch_pending_notifications(db, provider=FlakeyProvider())
    assert report.scanned == 2
    assert report.sent == 1
    assert report.failed == 1
    db.refresh(n1); db.refresh(n2)
    assert n1.is_sent and not n2.is_sent


# ---------- admin endpoint ----------


def test_admin_dispatch_endpoint(auth_client, db):
    _make_notification(db)
    r = auth_client.post("/admin/dispatch-notifications")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scanned"] == 1
    assert body["sent"] == 1


def test_admin_dispatch_requires_admin(client):
    client.post("/auth/register", json={"email": "first@example.com", "password": "secret123"})
    client.post("/auth/register", json={"email": "second@example.com", "password": "secret123"})
    r = client.post("/auth/login",
                    data={"username": "second@example.com", "password": "secret123"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = r.json()["access_token"]
    r = client.post("/admin/dispatch-notifications",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_dispatch_unauthenticated(client):
    r = client.post("/admin/dispatch-notifications")
    assert r.status_code == 401
