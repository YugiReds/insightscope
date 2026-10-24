"""Step 6: plain-English summaries of recall spikes, written by an AI but only from facts our own code computed.

How it stays honest:
  1. analytics.recall_spikes() computes every number. The AI is only asked to put them into words.
  2. The prompt tells the model not to add facts, and then a guardrail checks that every number in its answer
     appears in the facts. One invented number and the AI summary is thrown away.
  3. If the AI is unavailable (no token, timeout, error) or fails the guardrail, a plain template written from the
     same facts is used instead. Every result says which one it is, and why if it fell back.
  4. Good AI summaries are cached in Postgres, so the same spike does not call the AI again.

The token (HF_TOKEN) is read from the environment (loaded from .env) and is never printed or logged.
"""
import hashlib
import json
import os
import re
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import text

import analytics

load_dotenv()

HF_URL = "https://router.huggingface.co/v1/chat/completions"   # Hugging Face's OpenAI-style hosted inference API
# A small instruction-tuned model that Hugging Face lists on four different providers (so one provider being down
# does not take it offline). Checked on 2026-10-24 against the real service: all 6 real spikes passed the guardrail in
# 3 separate runs, about 3 seconds for all six. google/gemma-3-4b-it also passed 6/6 (about 8 seconds), and
# Qwen/Qwen3-4B-Instruct-2507 passed 6/6 but was the slowest (about 25 seconds) and has a single provider.
# Override with HF_MODEL, and re-check with `python insights.py` after changing it.
DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
MODEL = os.environ.get("HF_MODEL", DEFAULT_MODEL)
AI_TIMEOUT_SECONDS = 20
MAX_TOKENS = 220
MAX_SUMMARY_CHARS = 700
PROMPT_VERSION = 3       # change this when the prompt changes, so old cached summaries are not reused
# Version history: 1 = first prompt. 2 = added the rules against linking a firm to a reason and against saying
# "products" when the facts count recalls (real version-1 summaries did both). 3 = firm and reasons in separate
# sentences, "accounts for" never "responsible for", no calculated figures, no "the FDA reported" (version 2 still
# produced all of these). "products"/"items" is now also rejected by a code check, not only asked for in the prompt.

# How strongly one firm drove a spike, as the share of that month's recalls its recalls make up.
ONE_FIRM_PERCENT = 50
BIG_FIRM_PERCENT = 25


# ---------------------------------------------------------------------------------------------------------
# Facts: every number the summary may use. All of it is computed by our code, never by the AI.
# ---------------------------------------------------------------------------------------------------------

def build_facts(spike):
    """The spike's numbers from analytics.recall_spikes, plus how much of the month one firm explains."""
    facts = dict(spike)
    firms = spike["top_recalling_firms"]
    share = round(100 * firms[0]["recalls"] / spike["recalls"]) if firms and spike["recalls"] else 0
    facts["top_firm_share_pct"] = share
    if not firms:
        facts["driver"] = "unknown"
    elif share >= ONE_FIRM_PERCENT:
        facts["driver"] = "one_firm"
    elif share >= BIG_FIRM_PERCENT:
        facts["driver"] = "large_share"
    else:
        facts["driver"] = "spread"
    return facts


def month_label(facts):
    return datetime.strptime(facts["month"], "%Y-%m").strftime("%B %Y")


def driver_sentence(facts):
    """One sentence, written by our code, saying who drove the spike. Used in the prompt and in the template."""
    if facts["driver"] == "unknown":
        return "The firm behind these recalls is not recorded."
    firm, share = facts["top_recalling_firms"][0]["recalling_firm"], facts["top_firm_share_pct"]
    if facts["driver"] == "one_firm":
        return f"{firm} accounts for {share}% of the month's recalls, so this spike was mainly one firm's mass recall."
    if facts["driver"] == "large_share":
        return f"{firm} alone accounts for {share}% of the month's recalls, so one firm drove a large part of this spike but not all of it."
    return f"No single firm dominates: the largest, {firm}, accounts for {share}% of the month's recalls."


def facts_text(facts):
    """The facts exactly as the AI sees them. The guardrail allows only numbers that appear in this text."""
    reasons = "; ".join(f"{r['category']} ({r['recalls']} recalls)" for r in facts["top_reason_categories"])
    firms = "; ".join(f"{f['recalling_firm']} ({f['recalls']} recalls)" for f in facts["top_recalling_firms"])
    return "\n".join([
        f"Month: {month_label(facts)} ({facts['month']})",
        f"Recalls reported that month: {facts['recalls']}",
        f"Usual monthly count over the previous {analytics.BASELINE_MONTHS} months: about {round(facts['baseline_mean'])} "
        f"(average {facts['baseline_mean']:g}, standard deviation {facts['baseline_stddev']:g})",
        f"Z-score: {facts['z_score']:g} (about {facts['z_score']:.1f}). A z-score above {analytics.SPIKE_THRESHOLD:g} counts as a spike.",
        f"Top reason categories: {reasons}",
        f"Top recalling firms: {firms}",
        driver_sentence(facts),
    ])


# ---------------------------------------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You write short plain-English summaries of FDA drug recall spikes for a support team. "
    "Use ONLY the facts you are given. Do not add any facts, causes, names, dates or numbers that are not in the facts. "
    "Quote numbers exactly as written. Do not calculate anything: no percentages, differences, increases or ratios "
    "except the ones written in the facts. "
    "Say clearly who drove the spike, using the sentence about the largest firm, and say a firm 'accounts for' a share "
    "of the recalls, never that it is 'responsible for' or 'caused' anything. "
    "The facts list the top reasons and the top firms separately and never say which firm had which reason, so do not "
    "link a firm to a reason, and do not say a firm's recalls were 'due to', 'because of' or 'for' any reason. "
    "Put the largest firm and the top reasons in separate sentences. "
    "Always say 'recalls', never 'products' or 'items', because the facts count recalls. "
    "Do not say who reported the recalls: do not write 'the FDA reported'. Just say how many recalls there were. "
    "Write 2 or 3 sentences, with no lists and no markdown."
)


def user_prompt(facts):
    return f"Facts:\n{facts_text(facts)}\n\nWrite the summary now."


# ---------------------------------------------------------------------------------------------------------
# Guardrail: the AI's answer may only use numbers that are in the facts
# ---------------------------------------------------------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
# Words that state a quantity without a digit ("hundreds of recalls"), which could never be checked against the facts.
_VAGUE_QUANTITY = re.compile(r"\b(hundreds?|thousands?|millions?|dozens?)\b", re.IGNORECASE)


# The facts count RECALLS. Calling them "products" or "items" changes what the numbers mean.
_WRONG_NOUN = re.compile(r"\b(products?|items?)\b", re.IGNORECASE)


def _numbers_in(value):
    return [(match, float(match.replace(",", ""))) for match in _NUMBER.findall(value)]


def _without_names(summary, facts):
    """The summary with the firm and category names taken out, so a word inside a real name
    (for example the firm 'Acme Products Inc.') is not mistaken for the model saying 'products'."""
    names = [f["recalling_firm"] for f in facts["top_recalling_firms"]] + [r["category"] for r in facts["top_reason_categories"]]
    for name in sorted(names, key=len, reverse=True):
        summary = re.sub(re.escape(name), " ", summary, flags=re.IGNORECASE)
    return summary


def check_summary(summary, facts):
    """Return None if the summary passes, otherwise a short reason it was rejected."""
    if not summary or not summary.strip():
        return "the AI returned an empty summary"
    if len(summary) > MAX_SUMMARY_CHARS:
        return f"the AI summary is too long ({len(summary)} characters)"
    allowed = {value for _, value in _numbers_in(facts_text(facts))}
    invented = [shown for shown, value in _numbers_in(summary) if value not in allowed]
    if invented:
        return "it contains numbers that are not in the facts: " + ", ".join(dict.fromkeys(invented))
    vague = _VAGUE_QUANTITY.search(summary)
    if vague:
        return f"it states a quantity without a number ('{vague.group(0)}')"
    wrong_noun = _WRONG_NOUN.search(_without_names(summary, facts))
    if wrong_noun:
        return f"it calls recalls '{wrong_noun.group(0).lower()}', but the facts count recalls"
    return None


# ---------------------------------------------------------------------------------------------------------
# The fallback: a plain template written from the same facts
# ---------------------------------------------------------------------------------------------------------

def template_summary(facts):
    reasons = ", ".join(f"{r['category']} ({r['recalls']})" for r in facts["top_reason_categories"])
    firms = ", ".join(f"{f['recalling_firm']} ({f['recalls']})" for f in facts["top_recalling_firms"])
    parts = [
        f"{month_label(facts)} had {facts['recalls']} recalls, well above the usual {round(facts['baseline_mean'])} a month "
        f"over the previous {analytics.BASELINE_MONTHS} months (z-score {facts['z_score']:g}).",
        driver_sentence(facts),
    ]
    if reasons:
        parts.append(f"The most common reasons were {reasons}.")
    if firms:
        parts.append(f"The firms with the most recalls were {firms}.")
    return " ".join(parts)


# ---------------------------------------------------------------------------------------------------------
# Calling Hugging Face
# ---------------------------------------------------------------------------------------------------------

class AIError(Exception):
    """Calling the AI failed. The message is safe to show to users: it never contains the token or the reply body."""


_HTTP_HINTS = {
    401: "the token was rejected",
    402: "no remaining credits",
    403: "the token lacks permission",
    429: "rate limited",
}


class HuggingFaceClient:
    def __init__(self, token, model=MODEL, timeout=AI_TIMEOUT_SECONDS):
        self._token = token          # kept private and never included in any message
        self.model = model
        self.timeout = timeout

    def complete(self, system_prompt, user_message):
        """Send one chat request and return the model's text."""
        try:
            response = requests.post(
                HF_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                json={
                    "model": self.model,
                    "max_tokens": MAX_TOKENS,
                    "temperature": 0.2,   # low, so it sticks to the facts instead of getting creative
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                },
                timeout=self.timeout,
            )
        except requests.Timeout:
            raise AIError(f"the AI request timed out after {self.timeout} seconds") from None
        except requests.RequestException:
            raise AIError("could not reach Hugging Face") from None
        if response.status_code != 200:
            hint = _HTTP_HINTS.get(response.status_code)
            raise AIError(f"Hugging Face returned HTTP {response.status_code}" + (f" ({hint})" if hint else ""))
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError("Hugging Face sent a response in an unexpected format") from None


def get_client():
    """A client if HF_TOKEN is set, otherwise None (and every summary falls back to the template)."""
    token = os.environ.get("HF_TOKEN", "").strip()
    return HuggingFaceClient(token) if token else None


# ---------------------------------------------------------------------------------------------------------
# The cache: a Postgres table
# ---------------------------------------------------------------------------------------------------------
# Good AI summaries are stored in the table insight_cache in the same database as everything else. That means it
# survives API restarts, is shared by every worker process, and can be inspected in pgAdmin. The key is a hash of
# the prompt version, the model and every fact, so a changed number, model or prompt automatically means a fresh
# summary (old rows are simply never used again). Template summaries are NOT cached: they are cheap, and not
# caching them means the next request tries the AI again. To clear the cache: DELETE FROM insight_cache;
CACHE_COLUMNS_SQL = """
    cache_key  TEXT PRIMARY KEY,
    summary    TEXT NOT NULL,
    model      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
"""
CREATE_CACHE_SQL = text(f"CREATE TABLE IF NOT EXISTS insight_cache ({CACHE_COLUMNS_SQL})")
GET_CACHED_SQL = text("SELECT summary FROM insight_cache WHERE cache_key = :key")
PUT_CACHED_SQL = text("""
    INSERT INTO insight_cache (cache_key, summary, model) VALUES (:key, :summary, :model)
    ON CONFLICT (cache_key) DO UPDATE SET summary = EXCLUDED.summary, model = EXCLUDED.model, created_at = now()
""")


def cache_key(facts, model):
    payload = json.dumps({"prompt_version": PROMPT_VERSION, "model": model, "facts": facts}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------------------------------------

def summarize_spikes(conn, spikes, client):
    """One result per spike: its facts, a summary, where the summary came from ('ai' or 'template') and why."""
    conn.execute(CREATE_CACHE_SQL)
    model = getattr(client, "model", MODEL)
    ai_down = None                 # set after the first failed call, so one outage costs one timeout, not one per spike
    results = []
    for spike in spikes:
        facts = build_facts(spike)
        key = cache_key(facts, model)
        result = {"month": facts["month"], "facts": facts, "cached": False}

        cached = conn.execute(GET_CACHED_SQL, {"key": key}).scalar()
        if cached is not None:
            results.append({**result, "summary": cached, "source": "ai", "fallback_reason": None, "cached": True})
            continue

        reason = None
        if client is None:
            reason = "HF_TOKEN is not set, so the AI was not called"
        elif ai_down:
            reason = f"the AI call was skipped after an earlier failure in this request ({ai_down})"
        else:
            try:
                answer = client.complete(SYSTEM_PROMPT, user_prompt(facts))
            except AIError as error:
                ai_down = str(error)
                reason = f"the AI call failed: {error}"
            else:
                problem = check_summary(answer, facts)
                if problem:
                    reason = f"the AI summary was rejected: {problem}"
                else:
                    summary = answer.strip()
                    conn.execute(PUT_CACHED_SQL, {"key": key, "summary": summary, "model": model})
                    results.append({**result, "summary": summary, "source": "ai", "fallback_reason": None})
                    continue

        results.append({**result, "summary": template_summary(facts), "source": "template", "fallback_reason": reason})
    return results


def spike_insights(conn, client):
    """Every recall spike with its facts and a summary. Needs a connection that commits (for the cache)."""
    spikes = analytics.recall_spikes(conn)["spikes"]
    return {"model": getattr(client, "model", MODEL), "spikes": summarize_spikes(conn, spikes, client)}


if __name__ == "__main__":
    # A one-command check once the Hugging Face account has credits:  .\venv\Scripts\python.exe insights.py
    # It prints each spike's summary, whether it came from the AI, and why not if it did not. The token is never printed.
    from db import get_engine
    with get_engine().begin() as connection:
        output = spike_insights(connection, get_client())
    print("model:", output["model"])
    for item in output["spikes"]:
        print(f"\n[{item['month']}] source={item['source']} cached={item['cached']}"
              + (f"\n  reason: {item['fallback_reason']}" if item["fallback_reason"] else ""))
        print("  " + item["summary"])
