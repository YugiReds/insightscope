"""Tests for the recall analytics (analytics.py and the /analytics endpoints).

Two kinds of test:
  * Made-up data. A TEMP table called `recalls` is created for one test's database connection. It shadows the
    real table for that connection only, and is thrown away by a rollback, so the real data is never touched.
    The datasets are tiny and the right answer is obvious (a known spike month, a known partial month...).
  * Real data. These ask the database for the right answer and check the API agrees, like the other test files.

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import contextlib
import itertools
import statistics
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import analytics
import main
from db import get_engine

ENGINE = get_engine()
client = TestClient(main.app)


# ---------------------------------------------------------------------------------------------------------
# Helpers for made-up data
# ---------------------------------------------------------------------------------------------------------

@pytest.fixture
def fake():
    """A connection whose `recalls` table is an empty temporary copy. Rolled back after the test."""
    conn = ENGINE.connect()
    trans = conn.begin()
    conn.execute(text("CREATE TEMP TABLE recalls (LIKE public.recalls INCLUDING ALL)"))
    yield conn
    trans.rollback()
    conn.close()


_ids = itertools.count(1)


def add(conn, report_date, n=1, classification="Class II", reason="Some other thing", firm="Acme"):
    """Insert n made-up recalls reported on report_date."""
    rows = [{"num": f"T-{next(_ids):05d}", "firm": firm, "reason": reason, "cls": classification, "d": report_date}
            for _ in range(n)]
    conn.execute(text(
        "INSERT INTO recalls (recall_number, recalling_firm, reason_for_recall, classification, report_date) "
        "VALUES (:num, :firm, :reason, :cls, :d)"), rows)


class FakeEngine:
    """Stands in for main.engine so the API endpoints run against the made-up data."""
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return contextlib.nullcontext(self.conn)


@pytest.fixture
def api_on_fake_data(fake, monkeypatch):
    monkeypatch.setattr(main, "engine", FakeEngine(fake))
    return fake


# A calm year (Jan to Dec 2023) of 9, 11, 9, 11... recalls a month: mean 10, standard deviation about 1.04.
CALM_YEAR = [9, 11] * 6


def build_spike_world(conn):
    """Calm 2023, then a spike in Jan 2024 (30 recalls), then two normal months."""
    for i, n in enumerate(CALM_YEAR):
        add(conn, date(2023, i + 1, 4), n, firm="Filler Inc")
    reasons = (["Lack of Assurance of Sterility"] * 12 + ["CGMP Deviations"] * 9
               + ["Labeling: label mix-up"] * 6 + ["Subpotent Drug"] * 3)
    firms = ["Acme"] * 14 + ["Bolt"] * 8 + ["Charlie Co"] * 4 + ["Delta Co"] * 4  # Charlie and Delta tie at 4
    for reason, firm in zip(reasons, firms):
        add(conn, date(2024, 1, 10), reason=reason, firm=firm)
    add(conn, date(2024, 2, 7), 10, firm="Filler Inc")
    add(conn, date(2024, 3, 6), 11, firm="Filler Inc")


# ---------------------------------------------------------------------------------------------------------
# Reason categories: the keyword rules (made-up data)
# ---------------------------------------------------------------------------------------------------------

RULE_CASES = [
    ("Lack of Assurance of Sterility", "Sterility / contamination"),
    ("Microbial contamination", "Sterility / contamination"),
    ("CGMP Deviations", "CGMP violations"),
    # A specific problem beats the broad CGMP bucket:
    ("CGMP Deviations: carcinogen impurity detected in API", "Impurities"),
    ("Labeling: label mix-up", "Labeling"),
    ("Subpotent Drug", "Potency"),
    ("SUPERPOTENT DRUG", "Potency"),                                    # matching ignores upper/lower case
    ("Defective container", "Packaging"),
    # An incidental word inside a CGMP reason must not drag it into Packaging:
    ("CGMP Deviations: products repackaged in clear bottles", "CGMP violations"),
    ("Failed Dissolution Specifications", "Failed specifications"),
    ("Failed Impurities/Degradation Specifications", "Impurities"),     # first matching rule wins
    ("Marketed without an approved NDA/ANDA", "Unapproved drug"),
    ("Potential problem with the product", "Other"),                    # "potential" must NOT match potency
    ("", "Other"),
    (None, "Other"),
]


@pytest.mark.parametrize("reason, expected", RULE_CASES)
def test_keyword_rules_put_each_reason_in_the_right_category(fake, reason, expected):
    add(fake, date(2024, 1, 3), reason=reason)
    counts = {c["category"]: c["recalls"] for c in analytics.reason_categories(fake)["categories"]}
    assert counts[expected] == 1
    assert sum(counts.values()) == 1, f"{reason!r} was counted in more than one category"


def test_every_category_name_is_covered_by_the_rule_cases():
    # If someone adds a rule, they must add a test case for it.
    assert {expected for _, expected in RULE_CASES} == set(analytics.CATEGORY_NAMES)


def test_shares_and_other_share(fake):
    add(fake, date(2024, 1, 3), 4, reason="Lack of Assurance of Sterility")
    add(fake, date(2024, 1, 3), 1, reason="Something nobody wrote a rule for")
    result = analytics.reason_categories(fake)
    assert result["total"] == 5
    assert result["other_share"] == 0.2
    shares = {c["category"]: c["share"] for c in result["categories"]}
    assert shares["Sterility / contamination"] == 0.8
    assert round(sum(shares.values()), 6) == 1.0


def test_categories_are_listed_biggest_first_with_a_fixed_order_for_ties(fake):
    add(fake, date(2024, 1, 3), 2, reason="Subpotent Drug")
    add(fake, date(2024, 1, 3), 1, reason="Lack of Assurance of Sterility")
    names = [c["category"] for c in analytics.reason_categories(fake)["categories"]]
    assert names[:2] == ["Potency", "Sterility / contamination"]
    zeros = names[2:]
    assert zeros == sorted(zeros)           # the categories with 0 recalls are in name order
    assert len(names) == len(analytics.CATEGORY_NAMES)


def test_top_other_reasons_show_what_no_rule_matched(fake):
    add(fake, date(2024, 1, 3), 3, reason="Unusual thing A")
    add(fake, date(2024, 1, 3), 2, reason="Unusual thing B")
    add(fake, date(2024, 1, 3), 1, reason="Unusual thing C")
    add(fake, date(2024, 1, 3), 9, reason="Subpotent Drug")          # matched by a rule, so not listed
    top = analytics.reason_categories(fake)["top_other_reasons"]
    assert [(t["reason"], t["recalls"]) for t in top] == [("Unusual thing A", 3), ("Unusual thing B", 2), ("Unusual thing C", 1)]


def test_date_range_is_inclusive_at_both_ends(fake):
    add(fake, date(2024, 1, 3))
    add(fake, date(2024, 2, 7))
    add(fake, date(2024, 3, 6))
    assert analytics.reason_categories(fake, date(2024, 2, 7), date(2024, 2, 7))["total"] == 1
    assert analytics.reason_categories(fake, date(2024, 2, 1), date(2024, 3, 6))["total"] == 2
    assert analytics.reason_categories(fake, start=date(2024, 2, 8))["total"] == 1
    assert analytics.reason_categories(fake, end=date(2024, 2, 6))["total"] == 1
    assert analytics.reason_categories(fake)["total"] == 3


def test_no_recalls_gives_zero_not_a_division_error(fake):
    result = analytics.reason_categories(fake)
    assert result["total"] == 0
    assert result["other_share"] == 0.0


# ---------------------------------------------------------------------------------------------------------
# Coverage and monthly counts (made-up data)
# ---------------------------------------------------------------------------------------------------------

def test_oldest_month_is_dropped_when_its_first_weekly_report_is_missing(fake):
    add(fake, date(2024, 1, 17), 2)                            # oldest recall is on the 17th: weeks 1 and 2 are missing
    add(fake, date(2024, 2, 7), 2, classification="Class I")
    add(fake, date(2024, 2, 14), 1, classification="Class II")
    add(fake, date(2024, 4, 3), 1)
    result = analytics.monthly_recalls(fake)
    assert result["coverage"]["excluded_oldest_month"] == "2024-01"
    assert [m["month"] for m in result["months"]] == ["2024-02", "2024-03", "2024-04"]
    assert result["months"][0]["by_classification"] == {"Class I": 2, "Class II": 1}
    assert result["months"][1]["total"] == 0                   # a month with no recalls is still listed, as 0


def test_oldest_month_is_kept_when_a_report_falls_in_its_first_7_days(fake):
    add(fake, date(2024, 1, 3), 2)
    add(fake, date(2024, 2, 7), 1)
    result = analytics.monthly_recalls(fake)
    assert result["coverage"]["excluded_oldest_month"] is None
    assert [m["month"] for m in result["months"]] == ["2024-01", "2024-02"]


@pytest.mark.parametrize("day, kept", [(7, True), (8, False)])
def test_the_7_day_boundary(fake, day, kept):
    add(fake, date(2024, 1, day))
    add(fake, date(2024, 3, 6))
    months = [m["month"] for m in analytics.monthly_recalls(fake)["months"]]
    assert ("2024-01" in months) is kept


def test_newest_month_is_flagged_when_more_weekly_reports_could_follow(fake):
    add(fake, date(2024, 1, 3))
    add(fake, date(2024, 10, 9))
    assert analytics.monthly_recalls(fake)["coverage"]["newest_month_may_be_incomplete"] is True   # Oct 16 would still be October


def test_newest_month_is_not_flagged_when_it_is_over(fake):
    add(fake, date(2024, 1, 3))
    add(fake, date(2024, 10, 30))
    assert analytics.monthly_recalls(fake)["coverage"]["newest_month_may_be_incomplete"] is False  # next report is in November


def test_data_that_is_only_a_partial_month_gives_no_months(fake):
    add(fake, date(2024, 1, 17), 3)
    result = analytics.monthly_recalls(fake)
    assert result["months"] == []
    assert result["coverage"]["excluded_oldest_month"] == "2024-01"


def test_no_recalls_at_all(fake):
    assert analytics.monthly_recalls(fake) == {"coverage": None, "classifications": [], "months": []}
    assert analytics.recall_spikes(fake)["spikes"] == []


# ---------------------------------------------------------------------------------------------------------
# Spike detection (made-up data)
# ---------------------------------------------------------------------------------------------------------

def test_a_known_spike_month_is_flagged_and_nothing_else(fake):
    build_spike_world(fake)
    result = analytics.recall_spikes(fake)
    assert [s["month"] for s in result["spikes"]] == ["2024-01"]
    spike = result["spikes"][0]
    expected_z = (30 - 10) / statistics.stdev(CALM_YEAR)           # worked out by hand: about 19.15
    assert spike["recalls"] == 30
    assert spike["baseline_mean"] == 10.0
    assert spike["z_score"] == round(expected_z, 2)


def test_spike_lists_top_3_reason_categories_and_top_3_firms(fake):
    build_spike_world(fake)
    spike = analytics.recall_spikes(fake)["spikes"][0]
    assert spike["top_reason_categories"] == [
        {"category": "Sterility / contamination", "recalls": 12},
        {"category": "CGMP violations", "recalls": 9},
        {"category": "Labeling", "recalls": 6},
    ]
    # Charlie Co and Delta Co tie at 4 for third place. The name order decides, every time.
    assert spike["top_recalling_firms"] == [
        {"recalling_firm": "Acme", "recalls": 14},
        {"recalling_firm": "Bolt", "recalls": 8},
        {"recalling_firm": "Charlie Co", "recalls": 4},
    ]


def test_calm_data_has_no_spikes_even_when_a_month_is_a_bit_busy(fake):
    # Month 13 has 12 recalls against a baseline of mean 10 and stdev 1.04: z is about 1.9, just under the
    # threshold of 2. It is busier than usual but not a spike, so it must NOT be flagged. (This is what catches
    # a threshold set too low.)
    for i, n in enumerate(CALM_YEAR + [12, 10]):
        add(fake, date(2023 + (i // 12), i % 12 + 1, 4), n)
    result = analytics.recall_spikes(fake)
    assert (12 - 10) / statistics.stdev(CALM_YEAR) == pytest.approx(1.91, abs=0.01)   # check the setup itself
    assert result["spikes"] == []
    assert result["months_scored"] == 2                             # months 13 and 14 had a full baseline


def test_too_little_history_means_nothing_is_scored(fake):
    for month in range(1, 7):
        add(fake, date(2023, month, 4), 10 if month < 6 else 90)    # a huge month, but only 5 months before it
    result = analytics.recall_spikes(fake)
    assert result["months_scored"] == 0
    assert result["spikes"] == []


def test_a_flat_history_cannot_be_scored(fake):
    for month in range(1, 13):
        add(fake, date(2023, month, 4), 10)                          # exactly 10 every month: standard deviation 0
    add(fake, date(2024, 1, 10), 40)
    result = analytics.recall_spikes(fake)
    assert result["spikes"] == []
    assert result["months_scored"] == 0                              # z would be a division by zero, so it is skipped


def test_a_month_with_no_recalls_counts_as_zero_in_the_baseline(fake):
    counts = [10, 12, 10, 12, 10, 0, 12, 10, 12, 10, 12, 10]       # June 2023 has no recalls at all
    for month, n in enumerate(counts, start=1):
        if n:
            add(fake, date(2023, month, 4), n)
    add(fake, date(2024, 1, 10), 40)
    spike = analytics.recall_spikes(fake)["spikes"][0]
    expected_z = (40 - statistics.mean(counts)) / statistics.stdev(counts)
    assert spike["month"] == "2024-01"
    assert spike["z_score"] == round(expected_z, 2)                  # the gap was used as a 0, not skipped


def test_a_partly_covered_oldest_month_is_not_used_as_baseline(fake):
    # Same data as the known-spike test, but the oldest month starts on the 17th, so Jan 2023 is dropped.
    # Jan 2024 then has only 11 months before it and cannot be scored.
    add(fake, date(2023, 1, 17), 9)
    for i, n in enumerate(CALM_YEAR[1:], start=2):
        add(fake, date(2023, i, 4), n)
    add(fake, date(2024, 1, 10), 30)
    add(fake, date(2024, 2, 7), 10)
    add(fake, date(2024, 3, 6), 11)
    result = analytics.recall_spikes(fake)
    assert result["coverage"]["excluded_oldest_month"] == "2023-01"
    assert result["spikes"] == []
    assert result["months_scored"] == 2                              # only Feb 2024 and Mar 2024 have 12 months behind them


# ---------------------------------------------------------------------------------------------------------
# The endpoints on made-up data
# ---------------------------------------------------------------------------------------------------------

def test_spikes_endpoint_returns_the_known_spike(api_on_fake_data):
    build_spike_world(api_on_fake_data)
    body = client.get("/analytics/recalls/spikes").json()
    assert body["threshold"] == 2.0
    assert body["baseline_months"] == 12
    assert [s["month"] for s in body["spikes"]] == ["2024-01"]
    assert body["spikes"][0]["top_recalling_firms"][0] == {"recalling_firm": "Acme", "recalls": 14}


def test_monthly_endpoint_shape_on_made_up_data(api_on_fake_data):
    add(api_on_fake_data, date(2024, 1, 3), 2, classification="Class I")
    add(api_on_fake_data, date(2024, 2, 7), 3, classification="Class III")
    body = client.get("/analytics/recalls/monthly").json()
    assert body["classifications"] == ["Class I", "Class III"]
    assert body["months"][0] == {"month": "2024-01", "total": 2, "by_classification": {"Class I": 2, "Class III": 0}}


def test_reasons_endpoint_rejects_a_backwards_date_range():
    r = client.get("/analytics/recalls/reasons", params={"start": "2025-12-31", "end": "2025-01-01"})
    assert r.status_code == 422


def test_reasons_endpoint_rejects_a_bad_date():
    assert client.get("/analytics/recalls/reasons", params={"start": "not-a-date"}).status_code == 422


# ---------------------------------------------------------------------------------------------------------
# Real data
# ---------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    with ENGINE.connect() as conn:
        yield conn


def test_real_report_dates_are_all_on_the_same_weekday(db):
    # The partial-month rule assumes weekly reports. If the FDA changes its schedule, this fails loudly.
    weekdays = db.execute(text("SELECT COUNT(DISTINCT EXTRACT(dow FROM report_date)) FROM recalls")).scalar()
    assert weekdays == 1


def test_real_monthly_counts_add_up_to_the_database(db):
    body = client.get("/analytics/recalls/monthly").json()
    first = body["coverage"]["first_full_month"]
    expected = db.execute(text("SELECT COUNT(*) FROM recalls WHERE report_date >= :d"), {"d": first + "-01"}).scalar()
    assert sum(m["total"] for m in body["months"]) == expected
    assert all(sum(m["by_classification"].values()) == m["total"] for m in body["months"])


def test_real_months_are_consecutive_and_start_at_the_first_full_month():
    body = client.get("/analytics/recalls/monthly").json()
    months = [datetime.strptime(m["month"], "%Y-%m") for m in body["months"]]
    assert body["months"][0]["month"] == body["coverage"]["first_full_month"]
    assert all((b.year * 12 + b.month) - (a.year * 12 + a.month) == 1 for a, b in zip(months, months[1:]))


def test_real_oldest_month_is_excluded_exactly_when_it_starts_after_the_7th(db):
    oldest = db.execute(text("SELECT MIN(report_date) FROM recalls")).scalar()
    coverage = client.get("/analytics/recalls/monthly").json()["coverage"]
    if oldest.day > 7:
        assert coverage["excluded_oldest_month"] == oldest.strftime("%Y-%m")
    else:
        assert coverage["excluded_oldest_month"] is None


def test_real_reason_counts_add_up_and_other_stays_small(db):
    body = client.get("/analytics/recalls/reasons").json()
    assert body["total"] == db.execute(text("SELECT COUNT(*) FROM recalls")).scalar()
    assert sum(c["recalls"] for c in body["categories"]) == body["total"]
    assert abs(sum(c["share"] for c in body["categories"]) - 1) < 0.001
    # A guard on rule quality: if "Other" grows past 10%, the keyword rules need attention.
    assert body["other_share"] < 0.10, body["top_other_reasons"]


def test_real_reason_date_range_matches_the_database(db):
    start, end = "2025-01-01", "2025-12-31"
    expected = db.execute(text("SELECT COUNT(*) FROM recalls WHERE report_date BETWEEN :s AND :e"), {"s": start, "e": end}).scalar()
    body = client.get("/analytics/recalls/reasons", params={"start": start, "end": end}).json()
    assert body["total"] == expected
    assert sum(c["recalls"] for c in body["categories"]) == expected


def test_real_spikes_match_an_independent_calculation():
    monthly = client.get("/analytics/recalls/monthly").json()["months"]
    totals = [m["total"] for m in monthly]
    expected_spikes, scored = set(), 0
    for i in range(12, len(totals)):
        prior = totals[i - 12:i]
        sd = statistics.stdev(prior)
        if sd == 0:
            continue
        scored += 1
        if (totals[i] - statistics.mean(prior)) / sd > 2:
            expected_spikes.add(monthly[i]["month"])
    body = client.get("/analytics/recalls/spikes").json()
    assert {s["month"] for s in body["spikes"]} == expected_spikes
    assert body["months_scored"] == scored


def test_real_spike_details_are_well_formed():
    body = client.get("/analytics/recalls/spikes").json()
    monthly = {m["month"]: m["total"] for m in client.get("/analytics/recalls/monthly").json()["months"]}
    for spike in body["spikes"]:
        assert spike["z_score"] > body["threshold"]
        assert spike["recalls"] == monthly[spike["month"]]
        for key in ("top_reason_categories", "top_recalling_firms"):
            counts = [x["recalls"] for x in spike[key]]
            assert 1 <= len(counts) <= 3
            assert counts == sorted(counts, reverse=True)
            assert sum(counts) <= spike["recalls"]
