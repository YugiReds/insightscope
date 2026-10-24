# `insights.py`: AI-written spike summaries

**Job:** turns each spike from `analytics.recall_spikes()` into a plain-English summary. The AI writes the words; the code supplies and checks every number.

**Run it:** `.\venv\Scripts\python.exe insights.py` prints each spike's summary, `source` and any fallback reason.
**Endpoint:** `GET /insights/recalls/spikes`

> The snippets below are simplified to show the idea. Open `insights.py` in VS Code for the exact code.

## The flow for one spike

```
spike facts (from analytics.py)
   │
   ├─ already in insight_cache?  → return the cached AI summary
   │
   ├─ no HF_TOKEN, or an earlier call in this request failed?  → template
   │
   ├─ call Hugging Face with the facts + "don't add anything"
   │      ├─ error / timeout / HTTP 402  → template (reason recorded)
   │      └─ text comes back
   │
   ├─ fact-checker: every number in the text must be in the facts
   │      ├─ fails  → template (reason: "contains numbers that are not in the facts")
   │      └─ passes → save to insight_cache, return it as source = ai
```

## 1. The prompt: facts in, words out

The model receives the spike's numbers (month, count, usual monthly level, z-score, top reasons, top firms and the top firm's share). A low temperature keeps it close to the facts. The prompt is versioned (`PROMPT_VERSION`, currently 3); changing it changes the cache key, so every summary regenerates.

| Version | Rules added |
| --- | --- |
| 1 | Don't add any facts, causes, names, dates or numbers |
| 2 | Don't link a firm to a reason; always say "recalls," never "products" or "items" |
| 3 | Firm and reasons in separate sentences; "accounts for," never "responsible for"; no self-computed percentages or differences; no "the FDA reported" |

## 2. The fact-checker (the guardrail)

Simplified idea:

```python
allowed = set(all numbers that appear in the facts)
found = set(all numbers that appear in the AI's text)
if found - allowed:
    reject("contains numbers that are not in the facts: ...")
if "hundreds of" or similar vague amounts appear:
    reject(...)
remove firm and category names from the text, then
if "products" or "items" still appears:
    reject(...)
```

This is why the June 2021 summary fell back to a template on the first real run: the model wrote a "4" that wasn't in the facts.

**What it can't catch:** claims built from correct numbers, like linking a firm to a reason, or a true-but-derived statement ("the majority"). Those are handled by prompt rules (below) and documented as a known limit.

## 3. The template backup

Built from the same facts, so it's always accurate, for example:

> April 2025 had 97 recalls, well above the usual 47 a month over the previous 12 months (z-score 2.5). Glenmark Pharmaceuticals Inc., USA alone accounts for 41% of the month's recalls, so one firm drove a large part of this spike but not all of it.

How it describes the top firm depends on its share of the month (labels like `one_firm`, `large_share` or `spread`), so the wording never overstates one firm's role.

## 4. The cache (`insight_cache` table)

- Key: a hash of the prompt version + model + facts. Change any number and the key changes, so a fresh summary is generated.
- Only summaries that passed the fact-checker are stored.
- Lives in PostgreSQL, so it survives restarts and is visible in pgAdmin.

## 5. Settings it reads from `.env`

| Setting | Meaning |
| --- | --- |
| `HF_TOKEN` | Your Hugging Face token (required for AI; without it, templates are used) |
| `HF_MODEL` | Optional; defaults to `meta-llama/Llama-3.1-8B-Instruct` (verified fastest and most consistent of three models tested) |

The token is never printed, and a test checks that it can't leak into an error message.

## Why it matters

It shows a careful way to use AI: the model never decides any fact, every output is checked, and failures degrade to an accurate answer instead of an error.
