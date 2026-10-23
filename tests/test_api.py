"""Automated tests for the InsightScope API.

They run against the real database loaded by ingest.py. Instead of hard-coding drug names (which could
change if the data is reloaded), most tests ask the database directly and check that the API agrees.

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import main
from db import get_engine

client = TestClient(main.app)  # calls the app in-process, no server needed


@pytest.fixture(scope="module")
def db():
    """A direct database connection, used to work out the 'right answer' independently of the API."""
    with get_engine().connect() as conn:
        yield conn


@pytest.fixture(scope="module")
def repeated_ndc(db):
    """An NDC that has several label versions, to test the 'latest version' rule."""
    ndc = db.execute(text(
        "SELECT product_ndc FROM products GROUP BY product_ndc HAVING COUNT(*) > 1 ORDER BY product_ndc LIMIT 1"
    )).scalar()
    assert ndc, "test data has no repeated NDCs"
    return ndc


# --- health ---

def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "reachable"}


def test_health_returns_503_when_database_is_down(monkeypatch):
    # Point the app at a database that does not exist: the API should answer 503, not crash.
    dead = create_engine("postgresql+psycopg://nobody:nopass@127.0.0.1:1/none", connect_args={"connect_timeout": 2})
    monkeypatch.setattr(main, "engine", dead)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"detail": "Database unavailable"}


# --- products list ---

def test_total_counts_each_ndc_once(db):
    distinct_ndcs = db.execute(text("SELECT COUNT(DISTINCT product_ndc) FROM products")).scalar()
    assert client.get("/products", params={"limit": 1}).json()["total"] == distinct_ndcs


def test_pagination_respects_limit_and_offset():
    first = client.get("/products", params={"limit": 3, "offset": 0}).json()
    second = client.get("/products", params={"limit": 3, "offset": 3}).json()
    assert len(first["items"]) == 3
    ndcs = [i["product_ndc"] for i in first["items"] + second["items"]]
    assert len(set(ndcs)) == 6  # pages do not overlap


def test_labeler_filter_only_returns_matching_labelers(db):
    labeler = db.execute(text("SELECT labeler_name FROM products WHERE labeler_name IS NOT NULL LIMIT 1")).scalar()
    body = client.get("/products", params={"labeler": labeler.lower(), "limit": 100}).json()
    assert body["total"] >= 1
    assert all(labeler.lower() in i["labeler_name"].lower() for i in body["items"])


@pytest.mark.parametrize("params", [{"limit": 500}, {"limit": 0}, {"offset": -1}])
def test_bad_pagination_is_rejected_with_422(params):
    assert client.get("/products", params=params).status_code == 422


# --- product detail ---

def test_detail_returns_latest_label_version(db, repeated_ndc):
    expected = db.execute(text(
        "SELECT product_id FROM products WHERE product_ndc = :ndc "
        "ORDER BY marketing_start_date DESC NULLS LAST, product_id LIMIT 1"
    ), {"ndc": repeated_ndc}).scalar()
    r = client.get(f"/products/{repeated_ndc}")
    assert r.status_code == 200
    assert r.json()["product_id"] == expected


def test_detail_includes_ingredients_and_packages(db):
    ndc = db.execute(text("SELECT product_ndc FROM products WHERE product_ndc IS NOT NULL LIMIT 1")).scalar()
    body = client.get(f"/products/{ndc}").json()
    assert isinstance(body["active_ingredients"], list)
    assert isinstance(body["packages"], list)


def test_unknown_ndc_returns_404():
    r = client.get("/products/0000-0000")
    assert r.status_code == 404
    assert "0000-0000" in r.json()["detail"]


# --- stats ---

def test_top_labelers_sorted_and_counted(db):
    body = client.get("/stats/labelers", params={"limit": 5}).json()
    counts = [row["product_count"] for row in body]
    assert len(body) == 5
    assert counts == sorted(counts, reverse=True)
    # Cross-check the top labeler's count against the database (each NDC counted once).
    top = body[0]
    expected = db.execute(text(
        "SELECT COUNT(*) FROM (SELECT DISTINCT ON (product_ndc) labeler_name FROM products "
        "ORDER BY product_ndc, marketing_start_date DESC NULLS LAST, product_id) x WHERE labeler_name = :n"
    ), {"n": top["labeler_name"]}).scalar()
    assert top["product_count"] == expected


# --- search ---

def test_search_matches_brand_or_generic_name(db):
    term = db.execute(text("SELECT generic_name FROM products WHERE generic_name IS NOT NULL LIMIT 1")).scalar()[:5]
    results = client.get("/search", params={"q": term, "limit": 50}).json()
    assert results
    for item in results:
        names = f"{item['brand_name']} {item['generic_name']}".lower()
        assert term.lower() in names


def test_search_requires_at_least_two_characters():
    assert client.get("/search", params={"q": "a"}).status_code == 422
    assert client.get("/search").status_code == 422
