"""Tests for observability: /metrics endpoint + request access log."""
import logging
import re

import pytest


def test_metrics_endpoint_returns_prometheus_text(client):
    """`/metrics` returns Prometheus exposition format."""
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "# HELP" in body or "# TYPE" in body
    # Standard FastAPI HTTP metrics installed by the instrumentator
    assert "http_requests_total" in body or "http_request_duration_seconds" in body


def test_metrics_records_request_counters(client):
    """Hitting an endpoint bumps the HTTP request counter."""
    # Generate some traffic. Health is excluded from the sample (see
    # `excluded_handlers` in `setup_metrics`), so use /docs which is real.
    for _ in range(3):
        client.get("/customers")

    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Find the /customers row in the http_requests_total family. The
    # exact label syntax is determined by the instrumentator.
    matches = re.findall(r'http_requests_total\{[^}]*handler="/customers"[^}]*\}\s+([0-9.]+)', body)
    assert matches, f"expected /customers request counter in /metrics, got:\n{body[:2000]}"
    # We made at least 3 requests; allow >=3 because of test ordering.
    assert float(matches[-1]) >= 3.0


def test_health_endpoint_excluded_from_metrics(client):
    """Health checks shouldn't pollute the request histogram (high cardinality
    + uninteresting traffic).
    """
    client.get("/health")
    client.get("/health")
    body = client.get("/metrics").text
    assert 'handler="/health"' not in body


def test_metrics_business_gauges_after_sweep(auth_client):
    """Running the billing sweep populates the business-level gauges."""
    # Seed one customer + policy so the gauges have something to count.
    cust = auth_client.post("/customers", json={
        "full_name": "G Auge", "id_number": "9001015009099",
    }).json()
    auth_client.post("/policies", json={
        "customer_id": cust["id"], "policy_type": "individual",
        "premium_amount": "100.00", "currency": "ZAR",
    })

    # Run the sweep (admin-only endpoint - auth_client is admin).
    r = auth_client.post("/admin/run-billing-sweep")
    assert r.status_code == 200

    body = auth_client.get("/metrics").text
    assert "mandlzi_active_policies" in body
    assert "mandlzi_lapsed_policies" in body
    # The new active policy should be reflected.
    m = re.search(r"^mandlzi_active_policies\s+([0-9.]+)\s*$", body, re.MULTILINE)
    assert m and float(m.group(1)) >= 1.0, body


def test_request_log_middleware_emits_one_line(client, caplog):
    """One INFO log per request on the `mandlzi.access` logger."""
    with caplog.at_level(logging.INFO, logger="mandlzi.access"):
        client.get("/health")

    access_records = [r for r in caplog.records if r.name == "mandlzi.access"]
    assert len(access_records) >= 1
    msg = access_records[-1].getMessage()
    assert "method=GET" in msg
    assert "path=/health" in msg
    assert "status=200" in msg
    assert re.search(r"dur_ms=[0-9.]+", msg)


def test_request_log_extracts_user_id_from_bearer(auth_client, caplog):
    """When a valid bearer token is present, the access log includes the user id."""
    with caplog.at_level(logging.INFO, logger="mandlzi.access"):
        auth_client.get("/auth/me")

    access_records = [r for r in caplog.records if r.name == "mandlzi.access"]
    assert access_records, "expected at least one access log record"
    # `sub` is the user id; for the conftest's seed user that's "1".
    last = access_records[-1].getMessage()
    assert re.search(r"user=\d+", last), last


def test_request_log_anonymous_request_marks_user_dash(client, caplog):
    """Unauthenticated requests log `user=-` instead of a numeric id."""
    with caplog.at_level(logging.INFO, logger="mandlzi.access"):
        client.get("/health")

    access_records = [r for r in caplog.records if r.name == "mandlzi.access"]
    assert access_records
    assert "user=-" in access_records[-1].getMessage()
