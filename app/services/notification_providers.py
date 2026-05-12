"""Pluggable notification providers.

A *provider* turns a `Notification` row into an external side effect
(log line, webhook POST, SMS, email...). The dispatcher (see
``app.services.notification_dispatcher``) takes care of persistence,
retries and idempotency; providers only need to implement ``send``.

The factory below picks an implementation based on
``settings.NOTIFICATION_PROVIDER``. Adding a real Twilio/SES provider
is a matter of writing one more subclass and registering it here.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from app.config import settings
from app.models.notification import Notification


log = logging.getLogger(__name__)


class NotificationProvider(ABC):
    """Abstract provider. Implementations should raise on transient
    failure so the dispatcher can track an error / retry, and return
    normally on success."""

    @abstractmethod
    def send(self, n: Notification) -> None: ...


class LogProvider(NotificationProvider):
    """Default provider - just emits a log line. Useful for dev and tests."""

    def send(self, n: Notification) -> None:
        log.info(
            "Notification[id=%s type=%s customer=%s policy=%s]: %s",
            n.id, n.type, n.customer_id, n.policy_id, n.message,
        )


class WebhookProvider(NotificationProvider):
    """POST the notification payload as JSON to a configured URL.

    Designed to plug into Slack incoming webhooks, a custom backend, or
    a serverless function that fans out to SMS/email providers.
    """

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        if not url:
            raise ValueError("WebhookProvider requires a non-empty url")
        self.url = url
        self.timeout = timeout

    def send(self, n: Notification) -> None:
        payload = {
            "id": n.id,
            "type": n.type,
            "customer_id": n.customer_id,
            "policy_id": n.policy_id,
            "message": n.message,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": "mandlzi-notifier/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"webhook returned HTTP {resp.status}")
        except urllib.error.URLError as e:
            # Surface a clean message for the dispatcher's `last_error` column.
            raise RuntimeError(f"webhook unreachable: {e}") from e


def build_provider() -> NotificationProvider:
    """Factory: pick a provider based on settings."""
    name = (settings.NOTIFICATION_PROVIDER or "log").lower()
    if name == "log":
        return LogProvider()
    if name == "webhook":
        return WebhookProvider(url=settings.NOTIFICATION_WEBHOOK_URL or "")
    # Future: "twilio", "ses", ...
    raise ValueError(f"Unknown NOTIFICATION_PROVIDER: {name!r}")
