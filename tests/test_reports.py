"""Tests for the CSV reports (reports.py and the /reports endpoints).

Real-data tests ask the database for the right answer and check the file agrees. Made-up-data tests use a TEMP
table called `recalls` (and a TEMP `insight_cache`) that shadow the real ones for one connection and are rolled back,
so real data and the real summary cache are never touched. NOTHING here can call the real AI.

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import contextlib
import csv
import io
from collections import Counter
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import analytics
import insights
import main
import reports
from db import get_engine

ENGINE = get_engine()
client = TestClient(main.app)
BOM = b"\xef\xbb\xbf"
RECALL_HEADER = ["recall_number", "report_date", "classification", "status", "recalling_firm",
                 "product_description", "reason_for_recall", "reason_category"]
SPIKE_HEADER = ["month", "recalls", "baseline_average", "z_score", "top_firm", "top_firm_share_pct",
                "top_reasons", "summary", "source", "fallback_reason"]


def parse(response):
    """The CSV in a response as (header, rows). Decoding with utf-8-sig drops the byte order mark."""
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))
    return rows[0], rows[1:]


@pytest.fixture(autouse=True)
def never_call_the_real_ai(monkeypatch):
    """Safety net: if anything tries to reach Hugging Face, fail the test."""
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to make a real network call")
    monkeypatch.setattr(insights.requests, "post", refuse)


@pytest.fixture(scope="module")
def db():
    with ENGINE.connect() as connection:
        yield connection


# ---------------------------------------------------------------------------------------------------------
# The injection guard on its own
# ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\tindented", "\rreturn", '=HYPERLINK("http://x","y")'])
def test_a_text_cell_that_could_run_as_a_formula_gets_an_apostrophe(value):
    assert reports.neutralize(value) == "'" + value


@pytest.mark.parametrize("value", ["Acme Pharma", "D-0123-2026", "N/A", "Class I", "1+1=2", "a=b", "'already quoted", "", " =leading space"])
def test_ordinary_text_is_left_alone(value):
    assert reports.neutralize(value) == value


@pytest.mark.parametrize("value", [None, 12, -3.5, date(2026, 1, 1)])
def test_numbers_dates_and_empty_cells_are_not_text_so_they_are_left_alone(value):
    assert reports.neutralize(value) == value


def test_the_file_starts_with_a_byte_order_mark_and_uses_windows_line_endings():
    content = reports.build_csv(["a", "b"], [["x", "y"]])
    assert content.startswith(BOM)
    assert content.decode("utf-8-sig") == "a,b\r\nx,y\r\n"


# ---------------------------------------------------------------------------------------------------------
# /reports/recalls.csv on the real data
# ---------------------------------------------------------------------------------------------------------

def test_the_recalls_file_is_a_utf8_download_with_the_right_columns():
    response = client.get("/reports/recalls.csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="insightscope-recalls_all-dates.csv"'
    assert response.content.startswith(BOM)
    header, rows = parse(response)
    assert header == RECALL_HEADER
    assert all(len(row) == 8 for row in rows)


def test_one_row_per_recall(db):
    _, rows = parse(client.get("/reports/recalls.csv"))
    assert len(rows) == db.execute(text("SELECT COUNT(*) FROM recalls")).scalar()
    assert len({row[0] for row in rows}) == len(rows)          # each recall exactly once


def test_newest_first_with_recall_number_as_the_tiebreaker(db):
    _, rows = parse(client.get("/reports/recalls.csv"))
    expected = [r[0] for r in db.execute(text("SELECT recall_number FROM recalls ORDER BY report_date DESC NULLS LAST, recall_number DESC"))]
    assert [row[0] for row in rows] == expected


def test_a_date_range_includes_both_ends(db):
    response = client.get("/reports/recalls.csv", params={"start": "2025-01-01", "end": "2025-12-31"})
    _, rows = parse(response)
    expected = db.execute(text("SELECT COUNT(*) FROM recalls WHERE report_date BETWEEN '2025-01-01' AND '2025-12-31'")).scalar()
    assert len(rows) == expected > 0
    assert all("2025-01-01" <= row[1] <= "2025-12-31" for row in rows)
    assert response.headers["content-disposition"] == 'attachment; filename="insightscope-recalls_2025-01-01_to_2025-12-31.csv"'


def test_start_only_and_end_only(db):
    start_only = client.get("/reports/recalls.csv", params={"start": "2026-01-01"})
    end_only = client.get("/reports/recalls.csv", params={"end": "2019-12-31"})
    assert len(parse(start_only)[1]) == db.execute(text("SELECT COUNT(*) FROM recalls WHERE report_date >= '2026-01-01'")).scalar()
    assert len(parse(end_only)[1]) == db.execute(text("SELECT COUNT(*) FROM recalls WHERE report_date <= '2019-12-31'")).scalar()
    assert 'filename="insightscope-recalls_from-2026-01-01.csv"' in start_only.headers["content-disposition"]
    assert 'filename="insightscope-recalls_until-2019-12-31.csv"' in end_only.headers["content-disposition"]


def test_the_classification_filter_ignores_upper_and_lower_case(db):
    response = client.get("/reports/recalls.csv", params={"classification": "class i"})
    _, rows = parse(response)
    assert len(rows) == db.execute(text("SELECT COUNT(*) FROM recalls WHERE classification = 'Class I'")).scalar() > 0
    assert {row[2] for row in rows} == {"Class I"}
    assert response.headers["content-disposition"] == 'attachment; filename="insightscope-recalls_all-dates_class-i.csv"'


def test_filters_work_together(db):
    response = client.get("/reports/recalls.csv", params={"start": "2025-01-01", "end": "2025-12-31", "classification": "Class I"})
    _, rows = parse(response)
    expected = db.execute(text("SELECT COUNT(*) FROM recalls WHERE classification = 'Class I' AND report_date BETWEEN '2025-01-01' AND '2025-12-31'")).scalar()
    assert len(rows) == expected > 0
    assert 'insightscope-recalls_2025-01-01_to_2025-12-31_class-i.csv' in response.headers["content-disposition"]


def test_a_class_that_does_not_exist_gives_a_file_with_only_the_header():
    response = client.get("/reports/recalls.csv", params={"classification": "Class IV"})
    assert response.status_code == 200
    header, rows = parse(response)
    assert header == RECALL_HEADER and rows == []


def test_a_backwards_range_is_a_422_with_the_same_message_as_the_other_endpoints():
    response = client.get("/reports/recalls.csv", params={"start": "2025-12-31", "end": "2025-01-01"})
    assert response.status_code == 422
    assert response.json() == {"detail": "start must not be later than end"}
    assert "content-disposition" not in response.headers      # an error is not a download


@pytest.mark.parametrize("params", [{"start": "not-a-date"}, {"end": "2025-13-45"}, {"start": "yesterday"}])
def test_an_invalid_date_is_a_422(params):
    assert client.get("/reports/recalls.csv", params=params).status_code == 422


def test_the_reason_category_column_agrees_with_the_analytics_endpoint(db):
    params = {"start": "2025-01-01", "end": "2025-12-31"}
    _, rows = parse(client.get("/reports/recalls.csv", params=params))
    in_file = Counter(row[7] for row in rows)
    in_analytics = {c["category"]: c["recalls"] for c in analytics.reason_categories(db, date(2025, 1, 1), date(2025, 12, 31))["categories"] if c["recalls"]}
    assert dict(in_file) == in_analytics
    assert set(in_file) <= set(analytics.CATEGORY_NAMES)


def test_real_cells_that_start_with_a_formula_character_are_made_safe(db):
    risky = db.execute(text("SELECT recall_number, product_description FROM recalls WHERE product_description ~ '^[=+@\t\r-]'")).all()
    if not risky:
        pytest.skip("the current data has no cell that starts with a formula character")
    _, rows = parse(client.get("/reports/recalls.csv"))
    by_number = {row[0]: row for row in rows}
    for number, description in risky:
        assert by_number[number][5] == "'" + description


def test_commas_and_quotes_in_real_text_survive_a_round_trip(db):
    sample = db.execute(text("SELECT recall_number, recalling_firm, reason_for_recall FROM recalls WHERE recalling_firm LIKE '%,%' AND reason_for_recall LIKE '%\"%' LIMIT 1")).first()
    if sample is None:
        sample = db.execute(text("SELECT recall_number, recalling_firm, reason_for_recall FROM recalls WHERE recalling_firm LIKE '%,%' LIMIT 1")).first()
    _, rows = parse(client.get("/reports/recalls.csv"))
    row = next(r for r in rows if r[0] == sample[0])
    assert row[4] == sample[1] and row[6] == sample[2]


# ---------------------------------------------------------------------------------------------------------
# Made-up data: the cases the real data does not contain
# ---------------------------------------------------------------------------------------------------------

class FakeEngine:
    """Stands in for main.engine so the endpoints run on the connection we prepared."""
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return contextlib.nullcontext(self.connection)

    def begin(self):
        return contextlib.nullcontext(self.connection)


@pytest.fixture
def conn():
    """A connection with an empty temporary insight_cache. Rolled back afterwards."""
    connection = ENGINE.connect()
    transaction = connection.begin()
    connection.execute(text(f"CREATE TEMP TABLE insight_cache ({insights.CACHE_COLUMNS_SQL})"))
    yield connection
    transaction.rollback()
    connection.close()


@pytest.fixture
def fake_recalls(conn, monkeypatch):
    """An empty temporary `recalls` table, and the API pointed at it."""
    conn.execute(text("CREATE TEMP TABLE recalls (LIKE public.recalls INCLUDING ALL)"))
    monkeypatch.setattr(main, "engine", FakeEngine(conn))
    return conn


def add_recall(conn, number, firm="Acme", description="Tablets", reason="Some other thing", classification="Class II",
               status="Ongoing", report_date=date(2024, 1, 3)):
    conn.execute(text(
        "INSERT INTO recalls (recall_number, recalling_firm, product_description, reason_for_recall, classification, status, report_date) "
        "VALUES (:n, :f, :d, :r, :c, :s, :rd)"),
        {"n": number, "f": firm, "d": description, "r": reason, "c": classification, "s": status, "rd": report_date})


DANGEROUS = ['=HYPERLINK("http://evil.example","click")', "+1+1", "-2+3", "@SUM(A1:A9)", "\tTAB", "\rCR"]


def test_every_dangerous_cell_in_every_text_column_gets_an_apostrophe(fake_recalls):
    for value in DANGEROUS:
        add_recall(fake_recalls, value, firm=value, description=value, reason=value)
    _, rows = parse(client.get("/reports/recalls.csv"))
    assert len(rows) == len(DANGEROUS)
    for row in rows:
        original = row[0].lstrip("'")
        assert original in DANGEROUS
        for column in (0, 4, 5, 6):                       # recall_number, firm, description, reason
            assert row[column] == "'" + original, f"column {column} was not made safe"


def test_ordinary_text_with_accents_commas_quotes_and_newlines_comes_through_exactly(fake_recalls):
    firm, description, reason = "Müller-Lääke Oy, Åbo", 'He said "stop", then left', "line one\nline two"
    add_recall(fake_recalls, "S-1", firm=firm, description=description, reason=reason)
    add_recall(fake_recalls, "S-2", firm="'already has an apostrophe")
    response = client.get("/reports/recalls.csv")
    assert response.content.startswith(BOM)
    assert "Müller-Lääke".encode("utf-8") in response.content          # the accents are stored as real UTF-8
    _, rows = parse(response)
    by_number = {row[0]: row for row in rows}
    assert by_number["S-1"][4:7] == [firm, description, reason]
    assert by_number["S-2"][4] == "'already has an apostrophe"           # no second apostrophe


def test_missing_values_become_empty_cells(fake_recalls):
    fake_recalls.execute(text("INSERT INTO recalls (recall_number) VALUES ('E-1')"))
    _, rows = parse(client.get("/reports/recalls.csv"))
    assert rows == [["E-1", "", "", "", "", "", "", "Other"]]


def test_order_newest_first_ties_by_recall_number_and_missing_dates_last(fake_recalls):
    add_recall(fake_recalls, "A-1", report_date=date(2024, 1, 3))
    add_recall(fake_recalls, "B-1", report_date=date(2024, 1, 10))
    add_recall(fake_recalls, "C-1", report_date=date(2024, 1, 10))
    fake_recalls.execute(text("INSERT INTO recalls (recall_number) VALUES ('Z-1')"))
    _, rows = parse(client.get("/reports/recalls.csv"))
    assert [row[0] for row in rows] == ["C-1", "B-1", "A-1", "Z-1"]


def test_range_ends_are_inclusive_in_a_small_dataset(fake_recalls):
    for number, day in [("D1", date(2024, 1, 2)), ("D2", date(2024, 1, 3)), ("D3", date(2024, 1, 4)), ("D4", date(2024, 1, 5))]:
        add_recall(fake_recalls, number, report_date=day)
    _, rows = parse(client.get("/reports/recalls.csv", params={"start": "2024-01-03", "end": "2024-01-04"}))
    assert [row[0] for row in rows] == ["D3", "D2"]


# ---------------------------------------------------------------------------------------------------------
# /reports/spikes.csv
# ---------------------------------------------------------------------------------------------------------

class CountingClient:
    """A fake AI. It quotes two lines of the facts, so every number it uses is in the facts and passes the guardrail."""
    model = "fake/model"

    def __init__(self):
        self.calls = 0

    def complete(self, system_prompt, user_message):
        self.calls += 1
        return " ".join(user_message.splitlines()[1:3])


class ForbiddenClient:
    """A fake AI that fails the test if it is asked for anything."""
    model = "fake/model"

    def complete(self, system_prompt, user_message):
        raise AssertionError("the AI was called, but every summary should have come from the cache")


@pytest.fixture
def api(conn, monkeypatch):
    """The real recalls, but a TEMP summary cache, so the real cache is never read or written."""
    monkeypatch.setattr(main, "engine", FakeEngine(conn))
    return conn


def use_client(monkeypatch, client_or_none):
    monkeypatch.setattr(insights, "get_client", lambda: client_or_none)


def test_the_spikes_file_matches_the_json_endpoint_row_for_row(api, monkeypatch):
    use_client(monkeypatch, CountingClient())
    response = client.get("/reports/spikes.csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.content.startswith(BOM)
    header, rows = parse(response)
    assert header == SPIKE_HEADER

    spikes = client.get("/insights/recalls/spikes").json()["spikes"]
    assert len(rows) == len(spikes) > 0
    for row, spike in zip(rows, spikes):
        facts = spike["facts"]
        assert row[0] == spike["month"]
        assert int(row[1]) == facts["recalls"]
        assert float(row[2]) == facts["baseline_mean"]
        assert float(row[3]) == facts["z_score"]
        firm = facts["top_recalling_firms"][0]["recalling_firm"]
        assert row[4] == ("'" + firm if firm.startswith(("=", "+", "-", "@", "\t", "\r")) else firm)
        assert int(row[5]) == facts["top_firm_share_pct"]
        assert row[6] == "; ".join(f"{r['category']} ({r['recalls']})" for r in facts["top_reason_categories"])
        assert row[7] == spike["summary"]
        assert row[8] == spike["source"]
        assert row[9] == (spike["fallback_reason"] or "")


def test_the_download_name_includes_the_first_and_last_spike_month(api, monkeypatch):
    use_client(monkeypatch, None)
    months = [s["month"] for s in client.get("/analytics/recalls/spikes").json()["spikes"]]
    response = client.get("/reports/spikes.csv")
    assert response.headers["content-disposition"] == f'attachment; filename="insightscope-spikes_{months[0]}_to_{months[-1]}.csv"'


def test_no_ai_calls_when_every_summary_is_already_cached(api, monkeypatch):
    # First request: nothing is cached, so the AI writes each summary once and they are saved.
    counting = CountingClient()
    use_client(monkeypatch, counting)
    first = client.get("/reports/spikes.csv")
    spike_count = len(parse(first)[1])
    assert counting.calls == spike_count > 0
    # Second request: everything is cached. A client that fails if it is called must never be called.
    use_client(monkeypatch, ForbiddenClient())
    second = client.get("/reports/spikes.csv")
    assert second.status_code == 200
    assert second.content == first.content                      # identical file, from the cache
    assert counting.calls == spike_count


def test_a_summary_cached_by_the_json_endpoint_is_reused_by_the_csv(api, monkeypatch):
    counting = CountingClient()
    use_client(monkeypatch, counting)
    client.get("/insights/recalls/spikes")                      # fills the cache
    calls_after_json = counting.calls
    client.get("/reports/spikes.csv")
    assert counting.calls == calls_after_json                   # the CSV added no calls


def test_without_a_token_every_row_is_a_template_that_says_why(api, monkeypatch):
    use_client(monkeypatch, None)
    _, rows = parse(client.get("/reports/spikes.csv"))
    assert rows
    for row in rows:
        assert row[8] == "template"
        assert "HF_TOKEN is not set" in row[9]
        assert row[7]                                           # there is always a summary, even from the template


def test_no_spikes_gives_a_file_with_only_the_header(fake_recalls, monkeypatch):
    use_client(monkeypatch, None)
    for i, n in enumerate([9, 11] * 7):                        # 14 calm months: no spike
        for k in range(n):
            add_recall(fake_recalls, f"C-{i}-{k}", report_date=date(2023 + i // 12, i % 12 + 1, 4))
    response = client.get("/reports/spikes.csv")
    assert response.status_code == 200
    header, rows = parse(response)
    assert header == SPIKE_HEADER and rows == []
    assert response.headers["content-disposition"] == 'attachment; filename="insightscope-spikes.csv"'


def test_a_firm_name_that_starts_with_equals_is_made_safe_in_the_spikes_file(fake_recalls, monkeypatch):
    use_client(monkeypatch, None)
    for i, n in enumerate([9, 11] * 6):                        # a calm 2023...
        for k in range(n):
            add_recall(fake_recalls, f"C-{i}-{k}", firm="Filler Inc", report_date=date(2023, i + 1, 4))
    for k in range(30):                                        # ...then a spike in January 2024 caused by one odd firm name
        add_recall(fake_recalls, f"S-{k}", firm="=EVIL()", reason="Lack of Assurance of Sterility", report_date=date(2024, 1, 10))
    _, rows = parse(client.get("/reports/spikes.csv"))
    assert [row[0] for row in rows] == ["2024-01"]
    assert rows[0][4] == "'=EVIL()"
    assert rows[0][5] == "100"                                  # the top firm's share, as a plain number


# ---------------------------------------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------------------------------------

def test_both_endpoints_are_in_the_api_docs_and_come_before_any_dashboard_mount():
    paths = main.app.openapi()["paths"]
    assert "/reports/recalls.csv" in paths and "/reports/spikes.csv" in paths
    names = [getattr(route, "path", "") for route in main.app.routes]
    if main.app.routes[-1].name == "dashboard":                # present only when frontend/dist has been built
        assert names.index("/reports/recalls.csv") < len(names) - 1
        assert names.index("/reports/spikes.csv") < len(names) - 1
    assert client.get("/reports/recalls.csv").status_code == 200   # and the dashboard mount does not swallow them
