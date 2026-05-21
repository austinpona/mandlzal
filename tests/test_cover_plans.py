"""Tests for GET /cover-plans (catalog)."""
from app.services.cover_seed import seed_cover_plans


def test_cover_plans_filter_by_scheme_type(client, db):
    """Filter /cover-plans by scheme_type returns only matching plans."""
    seed_cover_plans(db)

    r = client.get("/cover-plans?scheme_type=goat_purchase")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["cover_type"] == "Goat in December"
    assert body[0]["scheme_type"] == "goat_purchase"


def test_cover_plans_unknown_scheme_422(client):
    """Unknown scheme enum value returns 422."""
    r = client.get("/cover-plans?scheme_type=does_not_exist")
    assert r.status_code == 422
