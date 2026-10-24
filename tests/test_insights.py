"""Tests for the AI summaries (insights.py and /insights/recalls/spikes).

THESE TESTS NEVER CALL THE REAL AI. The AI is always a fake object, and an automatic safety net makes any attempt
to reach Hugging Face fail the test. The summary cache is a temporary table that is rolled back after each test,
so the real insight_cache table is never touched either.

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import contextlib

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import text

import analytics
import insights
import main
from db import get_engine

ENGINE = get_engine()
client = TestClient(main.app)
SECRET = "hf_THIS_MUST_NEVER_APPEAR_ANYWHERE"


@pytest.fixture(autouse=True)
def never_call_the_real_ai(monkeypatch):
    """Safety net: if any test (or the code under test) tries to reach Hugging Face, fail loudly."""
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to make a real network call")
    monkeypatch.setattr(insights.requests, "post", refuse)


@pytest.fixture
def conn():
    """A connection with an empty temporary insight_cache. Rolled back afterwards."""
    connection = ENGINE.connect()
    transaction = connection.begin()
    connection.execute(text(f"CREATE TEMP TABLE insight_cache ({insights.CACHE_COLUMNS_SQL})"))
    yield connection
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------------------------------------
# Made-up spikes and a fake AI
# ---------------------------------------------------------------------------------------------------------

def make_spike(month="2019-03", recalls=535, mean=96.58, sd=43.5, z=10.08, reasons=None, firms=None):
    if reasons is None:
        reasons = [("Sterility / contamination", 494), ("Impurities", 25), ("Failed specifications", 8)]
    if firms is None:                      # an empty list is allowed and means "no firm is recorded"
        firms = [("King Bio Inc.", 465), ("Advanced Pharma Inc.", 19), ("Aurobindo Pharma USA Inc.", 5)]
    return {
        "month": month, "recalls": recalls, "baseline_mean": mean, "baseline_stddev": sd, "z_score": z,
        "top_reason_categories": [{"category": c, "recalls": n} for c, n in reasons],
        "top_recalling_firms": [{"recalling_firm": f, "recalls": n} for f, n in firms],
    }


SPIKE_A = make_spike()
GOOD_TEXT_A = ("March 2019 had 535 recalls, far above the usual 97 a month (z-score 10.1). King Bio Inc. accounts for "
               "87% of the month's recalls, so this was mainly one firm's mass recall, mostly for Sterility / "
               "contamination (494 recalls).")

SPIKE_B = make_spike(month="2021-06", recalls=236, mean=58.42, sd=24.09, z=7.37,
                     reasons=[("CGMP violations", 198), ("Other", 10), ("Potency", 8)],
                     firms=[("Cardinal Health Inc.", 198), ("Fresenius Medical Care Holdings, Inc.", 8), ("Acella Pharmaceuticals, LLC", 5)])
GOOD_TEXT_B = "June 2021 had 236 recalls, well above the usual 58 a month (z-score 7.4). Cardinal Health Inc. accounts for 84% of the month's recalls."


class FakeClient:
    """Stands in for the AI. `replies` is a list used in order (the last one repeats), or a function(system, user)."""
    def __init__(self, replies=None, error=None, model="fake/model"):
        self.replies = replies if callable(replies) else list(replies or [])
        self.error = error
        self.model = model
        self.calls = 0
        self.prompts = []

    def complete(self, system_prompt, user_message):
        self.calls += 1
        self.prompts.append((system_prompt, user_message))
        if self.error:
            raise self.error
        if callable(self.replies):
            return self.replies(system_prompt, user_message)
        return self.replies[min(self.calls, len(self.replies)) - 1]


def one(conn, spike, client):
    return insights.summarize_spikes(conn, [spike], client)[0]


# ---------------------------------------------------------------------------------------------------------
# A good summary
# ---------------------------------------------------------------------------------------------------------

def test_a_good_summary_is_used_and_labelled_ai(conn):
    fake = FakeClient([GOOD_TEXT_A])
    result = one(conn, SPIKE_A, fake)
    assert result["source"] == "ai"
    assert result["fallback_reason"] is None
    assert result["summary"] == GOOD_TEXT_A
    assert result["cached"] is False
    assert fake.calls == 1


def test_the_prompt_gives_the_facts_and_forbids_adding_any(conn):
    fake = FakeClient([GOOD_TEXT_A])
    one(conn, SPIKE_A, fake)
    system, user = fake.prompts[0]
    assert "Do not add any facts" in system
    assert "Quote numbers exactly" in system
    for fact in ["535", "King Bio Inc.", "494", "Sterility / contamination", "March 2019", "87%"]:
        assert fact in user
    assert "mainly one firm's mass recall" in user     # our code decided that, and told the AI


# ---------------------------------------------------------------------------------------------------------
# The guardrail: a made-up number falls back to the template
# ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("reply, invented", [
    ("March 2019 had 9999 recalls, mainly from King Bio Inc.", "9999"),
    ("March 2019 had 535 recalls, about 100 more than usual. King Bio Inc. drove it.", "100"),
    ("March 2019 had 535 recalls (z-score 12.5). King Bio Inc. drove it.", "12.5"),
    ("March 2019 had 535 recalls, up 450% on the usual. King Bio Inc. drove it.", "450"),
])
def test_a_made_up_number_falls_back_to_the_template(conn, reply, invented):
    fake = FakeClient([reply])
    result = one(conn, SPIKE_A, fake)
    assert result["source"] == "template"
    assert "not in the facts" in result["fallback_reason"]
    assert invented in result["fallback_reason"]
    assert result["summary"] == insights.template_summary(result["facts"])
    assert reply not in result["summary"]


def test_a_quantity_without_a_number_falls_back(conn):
    result = one(conn, SPIKE_A, FakeClient(["March 2019 saw hundreds of recalls, mainly from King Bio Inc."]))
    assert result["source"] == "template"
    assert "hundreds" in result["fallback_reason"]


@pytest.mark.parametrize("reply", ["", "   ", "No numbers here. " * 60])
def test_an_empty_or_overlong_reply_falls_back(conn, reply):
    result = one(conn, SPIKE_A, FakeClient([reply]))
    assert result["source"] == "template"
    assert "empty" in result["fallback_reason"] or "too long" in result["fallback_reason"]


def test_a_rejected_summary_is_not_cached(conn):
    one(conn, SPIKE_A, FakeClient(["March 2019 had 9999 recalls."]))
    assert conn.execute(text("SELECT COUNT(*) FROM insight_cache")).scalar() == 0


# --- the guardrail function on its own ---

def test_numbers_that_are_in_the_facts_are_accepted_in_any_listed_form():
    facts = insights.build_facts(make_spike(recalls=1234, mean=96.58, z=10.08,
                                            firms=[("King Bio Inc.", 617)]))
    ok = ("2019-03: 1,234 recalls vs about 97 (average 96.58, standard deviation 43.5). z-score 10.08, about 10.1. "
          "King Bio Inc. is 50% of 617 recalls. The 12 months before it set a threshold of 2.")
    assert insights.check_summary(ok, facts) is None


def test_a_number_that_is_not_in_the_facts_is_rejected():
    facts = insights.build_facts(SPIKE_A)
    assert "98" in insights.check_summary("March 2019 had 535 recalls versus a usual 98.", facts)
    assert insights.check_summary("March 2019 had 535 recalls versus a usual 97.", facts) is None


def test_the_template_always_passes_its_own_guardrail():
    spikes = [SPIKE_A, SPIKE_B, make_spike(recalls=1500, mean=210.5, sd=33.25, z=3.9, firms=[("Tiny Co", 30)]),
              make_spike(firms=[])]
    for spike in spikes:
        facts = insights.build_facts(spike)
        assert insights.check_summary(insights.template_summary(facts), facts) is None


@pytest.mark.parametrize("top_firm_recalls, driver, wording", [
    (465, "one_firm", "mainly one firm's mass recall"),      # 87%
    (270, "one_firm", "mainly one firm's mass recall"),      # 50.5% rounds to 50 or more
    (200, "large_share", "drove a large part of this spike"),  # 37%
    (100, "spread", "No single firm dominates"),             # 19%
])
def test_the_summary_says_how_much_one_firm_drove_the_spike(top_firm_recalls, driver, wording):
    facts = insights.build_facts(make_spike(firms=[("Big Firm", top_firm_recalls)]))
    assert facts["driver"] == driver
    assert wording in insights.driver_sentence(facts)
    assert wording in insights.template_summary(facts)


def test_a_spike_with_no_known_firm():
    facts = insights.build_facts(make_spike(firms=[]))
    summary = insights.template_summary(facts)
    assert facts["driver"] == "unknown" and facts["top_firm_share_pct"] == 0
    assert "not recorded" in summary
    assert "firms with the most recalls" not in summary          # no dangling empty sentence
    assert insights.check_summary(summary, facts) is None


# ---------------------------------------------------------------------------------------------------------
# Falling back when the AI cannot be used
# ---------------------------------------------------------------------------------------------------------

def test_a_timeout_falls_back_to_the_template(conn):
    fake = FakeClient(error=insights.AIError("the AI request timed out after 20 seconds"))
    result = one(conn, SPIKE_A, fake)
    assert result["source"] == "template"
    assert "timed out" in result["fallback_reason"]
    assert result["summary"] == insights.template_summary(result["facts"])


def test_after_one_failure_the_other_spikes_are_not_tried(conn):
    # One outage should cost one timeout, not one per spike.
    fake = FakeClient(error=insights.AIError("the AI request timed out after 20 seconds"))
    first, second = insights.summarize_spikes(conn, [SPIKE_A, SPIKE_B], fake)
    assert fake.calls == 1
    assert "timed out" in first["fallback_reason"]
    assert "skipped" in second["fallback_reason"] and "timed out" in second["fallback_reason"]
    assert first["source"] == second["source"] == "template"


def test_a_http_error_falls_back_and_says_why(conn):
    fake = FakeClient(error=insights.AIError("Hugging Face returned HTTP 402 (no remaining credits)"))
    result = one(conn, SPIKE_A, fake)
    assert result["source"] == "template"
    assert "402" in result["fallback_reason"] and "no remaining credits" in result["fallback_reason"]


def test_a_missing_token_falls_back_to_the_template(conn, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert insights.get_client() is None
    result = one(conn, SPIKE_A, insights.get_client())
    assert result["source"] == "template"
    assert "HF_TOKEN is not set" in result["fallback_reason"]


def test_a_blank_token_counts_as_missing(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "   ")
    assert insights.get_client() is None


def test_a_token_gives_a_client_that_does_not_expose_it(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", SECRET)
    made = insights.get_client()
    assert isinstance(made, insights.HuggingFaceClient)
    assert made.model == insights.MODEL
    assert SECRET not in repr(made) and SECRET not in str(vars(made).get("model"))


# ---------------------------------------------------------------------------------------------------------
# The Hugging Face client itself (with a pretend network)
# ---------------------------------------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status=200, body=None, text_body=""):
        self.status_code = status
        self._body = body
        self.text = text_body

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def pretend_network(monkeypatch, response=None, error=None):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        if error:
            raise error
        return response
    monkeypatch.setattr(insights.requests, "post", fake_post)
    return seen


def test_the_client_sends_the_prompt_and_returns_the_reply(monkeypatch):
    seen = pretend_network(monkeypatch, FakeResponse(200, {"choices": [{"message": {"content": "hello"}}]}))
    answer = insights.HuggingFaceClient(SECRET, model="some/model", timeout=7).complete("SYS", "USER")
    assert answer == "hello"
    assert seen["headers"] == {"Authorization": f"Bearer {SECRET}"}
    assert seen["timeout"] == 7
    assert seen["json"]["model"] == "some/model"
    assert seen["json"]["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert SECRET not in str(seen["json"])             # the token goes in the header only


@pytest.mark.parametrize("error, expected", [
    (requests.Timeout("slow"), "timed out after 7 seconds"),
    (requests.ConnectionError(f"failed, header Authorization: Bearer {SECRET}"), "could not reach Hugging Face"),
])
def test_network_failures_become_safe_messages(monkeypatch, error, expected):
    pretend_network(monkeypatch, error=error)
    with pytest.raises(insights.AIError) as caught:
        insights.HuggingFaceClient(SECRET, timeout=7).complete("S", "U")
    assert expected in str(caught.value)
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize("status, expected", [(401, "token was rejected"), (402, "no remaining credits"),
                                              (403, "lacks permission"), (429, "rate limited"), (500, "HTTP 500")])
def test_http_errors_become_safe_messages(monkeypatch, status, expected):
    pretend_network(monkeypatch, FakeResponse(status, text_body=f"body that echoes {SECRET}"))
    with pytest.raises(insights.AIError) as caught:
        insights.HuggingFaceClient(SECRET).complete("S", "U")
    assert expected in str(caught.value)
    assert SECRET not in str(caught.value)


def test_an_unexpected_reply_format_is_an_error(monkeypatch):
    pretend_network(monkeypatch, FakeResponse(200, {"unexpected": True}))
    with pytest.raises(insights.AIError, match="unexpected format"):
        insights.HuggingFaceClient(SECRET).complete("S", "U")


# ---------------------------------------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------------------------------------

def test_the_same_spike_does_not_call_the_ai_twice(conn):
    fake = FakeClient([GOOD_TEXT_A])
    first = one(conn, SPIKE_A, fake)
    second = one(conn, SPIKE_A, fake)
    assert fake.calls == 1                       # the second answer came from the cache
    assert first["cached"] is False and second["cached"] is True
    assert second["source"] == "ai" and second["summary"] == first["summary"]
    assert conn.execute(text("SELECT COUNT(*) FROM insight_cache")).scalar() == 1


def test_different_numbers_get_a_fresh_summary(conn):
    fake = FakeClient([GOOD_TEXT_A, GOOD_TEXT_B])
    first = one(conn, SPIKE_A, fake)
    second = one(conn, SPIKE_B, fake)
    assert fake.calls == 2
    assert first["summary"] == GOOD_TEXT_A and second["summary"] == GOOD_TEXT_B
    assert conn.execute(text("SELECT COUNT(*) FROM insight_cache")).scalar() == 2


def test_a_different_model_does_not_reuse_another_models_summary(conn):
    one(conn, SPIKE_A, FakeClient([GOOD_TEXT_A], model="fake/one"))
    other = FakeClient([GOOD_TEXT_A], model="fake/two")
    result = one(conn, SPIKE_A, other)
    assert other.calls == 1 and result["cached"] is False


def test_a_failure_is_not_cached_so_the_next_request_tries_the_ai_again(conn):
    one(conn, SPIKE_A, FakeClient(error=insights.AIError("the AI request timed out after 20 seconds")))
    recovered = FakeClient([GOOD_TEXT_A])
    result = one(conn, SPIKE_A, recovered)
    assert recovered.calls == 1
    assert result["source"] == "ai"


def test_the_cache_key_depends_on_the_facts_and_the_model():
    facts_a, facts_b = insights.build_facts(SPIKE_A), insights.build_facts(SPIKE_B)
    assert insights.cache_key(facts_a, "m") == insights.cache_key(insights.build_facts(make_spike()), "m")
    assert insights.cache_key(facts_a, "m") != insights.cache_key(facts_b, "m")
    assert insights.cache_key(facts_a, "m") != insights.cache_key(facts_a, "other")
    nudged = insights.build_facts(make_spike(recalls=536))
    assert insights.cache_key(facts_a, "m") != insights.cache_key(nudged, "m")


# ---------------------------------------------------------------------------------------------------------
# The endpoint, on the real spikes (the AI is still fake)
# ---------------------------------------------------------------------------------------------------------

class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return contextlib.nullcontext(self.connection)

    def begin(self):
        return contextlib.nullcontext(self.connection)


@pytest.fixture
def api(conn, monkeypatch):
    monkeypatch.setattr(main, "engine", FakeEngine(conn))
    return conn


def test_endpoint_without_a_token_gives_a_template_for_every_real_spike(api, monkeypatch):
    monkeypatch.setattr(insights, "get_client", lambda: None)
    body = client.get("/insights/recalls/spikes").json()
    spikes = client.get("/analytics/recalls/spikes").json()["spikes"]
    assert [s["month"] for s in body["spikes"]] == [s["month"] for s in spikes]
    assert len(body["spikes"]) > 0
    for item, spike in zip(body["spikes"], spikes):
        assert item["source"] == "template"
        assert "HF_TOKEN is not set" in item["fallback_reason"]
        assert item["facts"]["recalls"] == spike["recalls"] and item["facts"]["z_score"] == spike["z_score"]
        assert item["facts"]["driver"] in {"one_firm", "large_share", "spread", "unknown"}
        assert insights.check_summary(item["summary"], item["facts"]) is None


def test_endpoint_drivers_match_the_real_firm_shares(api, monkeypatch):
    monkeypatch.setattr(insights, "get_client", lambda: None)
    for item in client.get("/insights/recalls/spikes").json()["spikes"]:
        facts = item["facts"]
        share = round(100 * facts["top_recalling_firms"][0]["recalls"] / facts["recalls"])
        assert facts["top_firm_share_pct"] == share
        expected = "one_firm" if share >= 50 else "large_share" if share >= 25 else "spread"
        assert facts["driver"] == expected


def test_endpoint_uses_the_ai_when_it_passes_the_guardrail_and_then_caches(api, monkeypatch):
    # The fake AI quotes the first two fact lines, so its numbers are always in the facts.
    fake = FakeClient(lambda system, user: " ".join(user.splitlines()[1:3]))
    monkeypatch.setattr(insights, "get_client", lambda: fake)
    first = client.get("/insights/recalls/spikes").json()
    spike_count = len(first["spikes"])
    assert first["model"] == "fake/model"
    assert all(s["source"] == "ai" and not s["cached"] for s in first["spikes"])
    assert fake.calls == spike_count
    second = client.get("/insights/recalls/spikes").json()
    assert all(s["source"] == "ai" and s["cached"] for s in second["spikes"])
    assert fake.calls == spike_count                    # nothing new was sent to the AI
    assert [s["summary"] for s in second["spikes"]] == [s["summary"] for s in first["spikes"]]


def test_endpoint_survives_an_ai_outage(api, monkeypatch):
    fake = FakeClient(error=insights.AIError("could not reach Hugging Face"))
    monkeypatch.setattr(insights, "get_client", lambda: fake)
    response = client.get("/insights/recalls/spikes")
    assert response.status_code == 200
    assert fake.calls == 1
    assert all(s["source"] == "template" and "could not reach" in s["fallback_reason"] for s in response.json()["spikes"])
