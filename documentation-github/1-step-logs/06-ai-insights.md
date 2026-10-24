# Step 6: AI insights (Hugging Face)

**Result:** each detected recall spike gets a plain-English summary written by a real AI model, checked against the computed facts by code, with a template fallback and a database cache. After three prompt versions, all six live summaries are AI-written and contain no false or invented statements. Tests grew to 143.

**Date:** October 24, 2026 (overnight)

## The goal

Turn each spike from step 5 into a sentence a non-technical reader understands, without letting the AI state anything the data doesn't support.

## The design: a writer, a fact-checker and a backup

1. **Our code does all the math** (step 5): month, count, usual monthly level, z-score, top reasons and firms, and the top firm's share of the month.
2. **The AI only writes it up.** It gets those facts and strict rules about what it may not add.
3. **Code checks the result** (the guardrail):
   - every number in the text must appear in the facts;
   - vague amounts like "hundreds of" are rejected;
   - "products" or "items" are rejected when the facts say "recalls" (firm names like "Acme Products Inc." are removed first, so they don't trigger it).
4. **A template is the backup**, written from the same facts. It's used if the token is missing, the call fails or times out, or the guardrail rejects the AI text.

Every result says `source: ai` or `source: template`, plus a `fallback_reason` when it fell back.

## What was built

| File | Job |
| --- | --- |
| `insights.py` | Builds the prompt, calls Hugging Face, runs the guardrail, falls back to the template, manages the cache |
| `tests/test_insights.py` | 50 tests; none call the real AI |
| `main.py`, `schemas.py` | The new endpoint and its response shape |
| Postman collection | New "Spike insights (AI summaries)" request (26 total) |
| README, CLAUDE.md | Endpoint docs, a "how they stay honest" section with the guardrail's limits, troubleshooting |

**New endpoint:** `GET /insights/recalls/spikes` returns each spike's facts, summary, source and any fallback reason.

**From the terminal:** `.\venv\Scripts\python.exe insights.py` prints each spike's summary, source, cache status and reason.

No new package was installed. Hugging Face offers an OpenAI-style web API, and the `requests` library already in the project calls it.

## Timeline of the step

### 1. Built with fakes, blocked by credits

The first build worked end to end with a fake AI in the tests, but every real call returned **HTTP 402 "no remaining credits."** Hugging Face gives free accounts no monthly credits for hosted models, so every summary fell back to the template. The template path was proven to work this way.

**Fix:** a small prepaid credit on Hugging Face, with automatic recharge off.

### 2. First real run: the guardrail caught a real invented number

Five of six summaries were AI-written. **June 2021 was rejected**: the model wrote a "4" that wasn't in the facts, so the template was used. That was the guardrail working on a real model, not just in tests.

### 3. Model comparison

Each model was run through the real pipeline (real guardrail, 20-second timeout) on all six spikes:

| Model | Passed the guardrail | Time for all six |
| --- | --- | --- |
| **meta-llama/Llama-3.1-8B-Instruct** (chosen) | 6/6 in three separate runs | 2.8–3.6 s |
| google/gemma-3-4b-it | 6/6 | 8.1 s |
| Qwen/Qwen3-4B-Instruct-2507 | 6/6 | 24.6 s (30 s on one probe, past the timeout) |

Llama was chosen for speed, consistency across runs, and having four providers (one going down doesn't take it offline). It can be changed with `HF_MODEL` in `.env`.

### 4. Cache verified

A second run answered all six spikes from the cache in 0.6 seconds, with no AI calls (`cached=True`).

### 5. Prompt version 2: the guardrail's blind spot

Every number was correct, but the model was joining true facts into claims the facts never make. Examples:
- "Cardinal Health's 198 recalls were **due to CGMP violations**." The facts list top firms and top reasons separately and never link them.
- "465 **products**," when the facts say 465 recalls.

**The lesson:** a number checker can't catch an invented *connection* between correct numbers. Version 2 told the model not to link firms to reasons and to always say "recalls."

### 6. Prompt version 3 plus a code check

Version 2 still allowed loose phrasing. Version 3 added: firm and reasons in separate sentences; "accounts for," never "responsible for"; no percentages or differences the model computes itself; no "the FDA reported." A deterministic code check for "products"/"items" was added, since a rule that can be written as code beats a prompt instruction.

Measured on 24 real summaries per version:

| Behavior | v1 | v2 | v3 |
| --- | --- | --- | --- |
| Said "products" or "items" | 1 | 0 | 0 |
| Firm and reasons in one sentence | 4 | 5 | 0 |
| Wrote "the FDA reported" | not measured | 10 | 0 |
| Rejected for a self-computed number (e.g. "304% increase") | 1 | 1–4 | 0 |

Each version bump changes the cache key, so all six summaries were regenerated automatically. Old-version cache rows were then deleted (18 rows → 6).

## The six live summaries (prompt v3)

| Month | Verdict |
| --- | --- |
| 2019-03 | Correct. Style: four sentences instead of two or three, and it repeats King Bio's role |
| 2021-06 | Correct. Says CGMP violations were "the majority" (true, 198 of 236, but derived; the facts don't say it) |
| 2021-11 | Clean |
| 2022-06 | Clean |
| 2025-04 | Clean (this was the v2 problem case) |
| 2025-10 | Clean |

**Limits the checks still can't catch** (documented in the README): true-but-derived statements like "the majority," repetition and wording, and "significant" being read as a statistical claim. These were judged not worth more tuning; catching derived claims needs a different kind of check.

## The cache

- PostgreSQL table `insight_cache`; survives restarts, visible in pgAdmin.
- Key = hash of prompt version + model + facts. A changed number or a new prompt version produces a fresh summary.
- Only summaries that passed the guardrail are cached. Rejected or failed summaries try the AI again next time.
- After the first failed call in a request, the remaining spikes skip the AI, so an outage costs one timeout, not six.

## Testing the tests

A safety net makes any real network call fail a test. Deliberate breaks, each caught:

| Deliberate break | Tests that failed |
| --- | --- |
| Number check switched off | 6 |
| Guardrail never called | 9 |
| "hundreds of" allowed | 1 |
| Cache key ignores the facts | 3 |
| Keeps calling the AI after a failure | 2 |
| "products"/"items" check switched off | 4 |

Breaking things also exposed a bug in a test helper (an empty firm list silently replaced by a default) and a dangling "...were ." sentence in the template. Both were fixed.

## Problems hit and fixed

| Problem | Cause | Fix |
| --- | --- | --- |
| Token visible in a screenshot | Token shared before saving it | Deleted it, created a new one, pasted it straight into `.env` |
| Every call returned HTTP 402 | Free accounts have $0 inference credits | Small prepaid credit, automatic recharge off |
| One summary rejected on the first real run | Model invented a "4" | Nothing; the guardrail worked. Later prompt versions reduced self-computed numbers to 0 |
| Correct numbers, unsupported claims | Number checks can't see claims | Prompt v2 and v3, plus a code check for "products"/"items" |
| Docs folder and zips untracked in the project | Zips extracted inside the project | Markdown docs moved to `documentation-github/`, PDFs to `Documents`, zips deleted |

## Git commits in this step

| Commit | Message |
| --- | --- |
| `7929040` | Add AI spike summaries with fact-check guardrail and template fallback; add project documentation |
| `19e8f26` | Tighten AI summary prompt (v3) and add products/items wording check |

## Interview lines

- "The AI never calculates anything. SQL finds the spikes, the model only phrases them, and code rejects any summary with a number that isn't in the computed facts. On the first real run it caught an invented number and fell back automatically."
- "I then found the checker's blind spot: correct numbers joined into unsupported claims. I measured behavior on 24 real summaries per prompt version and took firm-reason linking from 5 of 24 to 0, added a code check for what a rule could catch, and documented what still can't be caught."
