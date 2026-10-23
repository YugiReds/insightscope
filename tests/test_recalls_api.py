"""Automated tests for the recall endpoints.

Like test_api.py, these run against the real database and ask the database for the right answer
instead of hard-coding recall numbers. Two kinds of problems get special attention:
  * paging: walking every page must return each recall exactly once (thousands of recalls share a report
    date, so a missing tiebreaker in the sort would repeat some recalls and skip others)
  * null fields: real recalls have gaps (no state, no voluntary/mandated value) and must not cause errors

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from db import get_engine

client = TestClient(main.app)

ORDER_SQL = "ORDER BY report_date DESC NULLS LAST, recall_number DESC"  # the order the API promises


@pytest.fixture(scope="module")
def db():
    """A direct database connection, used to work out the right answer independently of the API."""
    with get_engine().connect() as conn:
        yield conn


def crawl(path, limit, **params):
    """Walk every page of a list endpoint. Returns (reported total, every item in the order received)."""
    items, offset = [], 0
    while True:
        r = client.get(path, params={**params, "limit": limit, "offset": offset})
        assert r.status_code == 200, r.text
        body = r.json()
        items += body["items"]
        offset += limit
        if offset >= body["total"]:
            return body["total"], items


# --- /recalls: totals and paging ---

def test_total_matches_database(db):
    expected = db.execute(text("SELECT COUNT(*) FROM recalls")).scalar()
    assert client.get("/recalls", params={"limit": 1}).json()["total"] == expected


@pytest.mark.parametrize("limit", [100, 37])  # 37 is deliberately awkward so page edges fall in different places
def test_paging_through_everything_returns_each_recall_once(db, limit):
    total, items = crawl("/recalls", limit)
    numbers = [i["recall_number"] for i in items]
    assert len(numbers) == total
    assert len(set(numbers)) == total, "some recalls appeared on more than one page"
    in_db = {row[0] for row in db.execute(text("SELECT recall_number FROM recalls"))}
    assert set(numbers) == in_db, "some recalls never appeared on any page"


def test_order_is_newest_first_with_a_fixed_tiebreak(db):
    _, items = crawl("/recalls", 100)
    expected = [row[0] for row in db.execute(text(f"SELECT recall_number FROM recalls {ORDER_SQL}"))]
    assert [i["recall_number"] for i in items] == expected


# --- /recalls: null fields ---

def test_recalls_with_missing_values_are_returned_not_errors(db):
    # crawl() already fails on any 500. Here we also check the nulls come through as null.
    _, items = crawl("/recalls", 100)
    for column in ("state", "voluntary_mandated"):
        expected = db.execute(text(f"SELECT COUNT(*) FROM recalls WHERE {column} IS NULL")).scalar()
        assert expected > 0, f"test data no longer has a recall with a null {column}"
        assert sum(1 for i in items if i[column] is None) == expected


def test_detail_of_recall_with_null_fields(db):
    number = db.execute(text(
        "SELECT recall_number FROM recalls WHERE voluntary_mandated IS NULL AND state IS NULL "
        "ORDER BY recall_number LIMIT 1")).scalar() or db.execute(text(
        "SELECT recall_number FROM recalls WHERE voluntary_mandated IS NULL ORDER BY recall_number LIMIT 1")).scalar()
    r = client.get(f"/recalls/{number}")
    assert r.status_code == 200
    assert r.json()["voluntary_mandated"] is None


# --- /recalls: filters ---

def test_classification_filter_is_case_insensitive(db):
    expected = db.execute(text("SELECT COUNT(*) FROM recalls WHERE classification = 'Class I'")).scalar()
    body = client.get("/recalls", params={"classification": "class i", "limit": 100}).json()
    assert body["total"] == expected
    assert all(i["classification"] == "Class I" for i in body["items"])


def test_status_filter(db):
    expected = db.execute(text("SELECT COUNT(*) FROM recalls WHERE status = 'Ongoing'")).scalar()
    body = client.get("/recalls", params={"status": "ONGOING", "limit": 100}).json()
    assert body["total"] == expected
    assert all(i["status"] == "Ongoing" for i in body["items"])


def test_firm_filter_matches_part_of_the_name(db):
    firm = db.execute(text("SELECT recalling_firm FROM recalls WHERE recalling_firm IS NOT NULL LIMIT 1")).scalar()
    part = firm[:6].lower()
    body = client.get("/recalls", params={"recalling_firm": part, "limit": 100}).json()
    assert body["total"] >= 1
    assert all(part in i["recalling_firm"].lower() for i in body["items"])


@pytest.mark.parametrize("character", ["%", "_"])
def test_wildcard_characters_in_firm_filter_are_taken_literally(db, character):
    expected = db.execute(text("SELECT COUNT(*) FROM recalls WHERE POSITION(:c IN recalling_firm) > 0"),
                          {"c": character}).scalar()
    assert client.get("/recalls", params={"recalling_firm": character}).json()["total"] == expected


@pytest.mark.parametrize("params", [{"limit": 500}, {"limit": 0}, {"offset": -1}])
def test_bad_paging_values_are_rejected_with_422(params):
    assert client.get("/recalls", params=params).status_code == 422


# --- /recalls/{recall_number} ---

def test_detail_lists_all_the_recalls_ndcs(db):
    number = db.execute(text(
        "SELECT recall_number FROM recall_ndcs GROUP BY recall_number ORDER BY COUNT(*) DESC, recall_number LIMIT 1")).scalar()
    expected = sorted(row[0] for row in db.execute(
        text("SELECT product_ndc FROM recall_ndcs WHERE recall_number = :n"), {"n": number}))
    body = client.get(f"/recalls/{number}").json()
    assert body["product_ndcs"] == expected
    assert len(expected) > 1


def test_detail_of_recall_with_no_ndcs_has_an_empty_list(db):
    number = db.execute(text(
        "SELECT recall_number FROM recalls WHERE recall_number NOT IN (SELECT recall_number FROM recall_ndcs) "
        "ORDER BY recall_number LIMIT 1")).scalar()
    r = client.get(f"/recalls/{number}")
    assert r.status_code == 200
    assert r.json()["product_ndcs"] == []


def test_unknown_recall_returns_404():
    r = client.get("/recalls/X-9999-9999")
    assert r.status_code == 404
    assert "X-9999-9999" in r.json()["detail"]


def test_recall_numbered_na_can_be_fetched(db):
    # The FDA really has a recall numbered 'N/A' (a number not yet assigned). A route that stops at the
    # first '/' can never reach it.
    if not db.execute(text("SELECT COUNT(*) FROM recalls WHERE recall_number = 'N/A'")).scalar():
        pytest.skip("the current data has no recall numbered 'N/A'")
    r = client.get("/recalls/N/A")
    assert r.status_code == 200
    assert r.json()["recall_number"] == "N/A"
    assert r.json()["product_ndcs"] == []


def test_slashes_in_an_unknown_recall_number_reach_our_own_404():
    # Does not depend on the data. The 404 must be OUR message. The framework's generic "Not Found" would
    # mean the URL never reached our code at all.
    r = client.get("/recalls/A/B/C")
    assert r.status_code == 404
    assert r.json()["detail"] == "No recall found with recall number A/B/C"


# --- /products/{ndc}/recalls ---

def test_product_recalls_pages_cover_every_recall_once(db):
    ndc = db.execute(text(
        "SELECT product_ndc FROM recall_ndcs GROUP BY product_ndc ORDER BY COUNT(*) DESC, product_ndc LIMIT 1")).scalar()
    expected = [row[0] for row in db.execute(text(
        f"SELECT recall_number FROM recalls WHERE recall_number IN "
        f"(SELECT recall_number FROM recall_ndcs WHERE product_ndc = :n) {ORDER_SQL}"), {"n": ndc})]
    assert len(expected) > 10, "need an NDC with several recalls to make paging meaningful"
    total, items = crawl(f"/products/{ndc}/recalls", 10)
    assert total == len(expected)
    assert [i["recall_number"] for i in items] == expected


def test_works_for_a_recalled_ndc_that_is_not_in_products(db):
    ndc = db.execute(text(
        "SELECT product_ndc FROM recall_ndcs WHERE product_ndc NOT IN "
        "(SELECT product_ndc FROM products WHERE product_ndc IS NOT NULL) ORDER BY product_ndc LIMIT 1")).scalar()
    body = client.get(f"/products/{ndc}/recalls").json()
    assert body["product_ndc"] == ndc
    assert body["total"] >= 1


def test_valid_ndc_with_no_recalls_returns_empty_not_404():
    r = client.get("/products/99999-999/recalls")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


@pytest.mark.parametrize("ndc", ["abc", "12345", "12345-", "123-456", "12345-67890", "12345_678"])
def test_malformed_ndc_is_rejected_with_422(ndc):
    # A typo must not be answered with "no recalls", which would look like good news.
    assert client.get(f"/products/{ndc}/recalls").status_code == 422
