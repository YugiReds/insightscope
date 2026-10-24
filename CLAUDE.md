# InsightScope

Portfolio project for a Technical Support Engineer application at Medidata. Goal: a small, well-explained
data service over public drug data. Lean scope on purpose.

## Stack
- Python, FastAPI (API layer, not built yet), PostgreSQL (database `insightscope`), SQLAlchemy 2.x with the psycopg v3 driver, pandas for cleaning.
- Data source: openFDA NDC drug directory API (`https://api.fda.gov/drug/ndc.json`).
- No frontend and no AI features yet.

## Rules
- Always run Python with `.\venv\Scripts\python.exe` (Windows, PowerShell).
- `.env` holds `DATABASE_URL`. Never print, read out, or commit it.
- Ask before installing any new package; keep `requirements.txt` in sync.
- The owner must be able to explain every file in an interview, so keep code simple and add plain-language
  comments/docstrings. Explain each new file when creating it.

## Layout
- `db.py` - database connection (engine) and table definitions.
- `ingest.py` - step 1 script: fetch from openFDA, clean with pandas, load into Postgres.
- `ingest_recalls.py` - step 4 script: same pattern for the openFDA drug enforcement (recalls) API. Fetches everything before touching the database, then replaces both recall tables in one transaction.
- `main.py` - FastAPI app (step 2): `/health`, `/products`, `/products/{ndc}`, `/stats/labelers`, `/search`, `/recalls`, `/recalls/{recall_number}`, `/products/{ndc}/recalls`. All NDC reads go through the `latest` subquery (one row per NDC, newest `marketing_start_date`).
- `schemas.py` - Pydantic response models for the API.
- `insights.py` - step 6 AI summaries of the recall spikes (Hugging Face, with guardrail, template fallback and a Postgres cache table `insight_cache`). Called by `/insights/recalls/spikes`.
- `analytics.py` - step 5 recall analytics (monthly counts, reason categories, spike detection). Plain SQL via `text()`, called by the `/analytics/recalls/*` endpoints in `main.py`.
- `tests/test_api.py`, `tests/test_recalls_api.py`, `tests/test_analytics.py`, `tests/test_insights.py`, `tests/test_ingest_recalls.py`, `pytest.ini` - tests. `README.md` - public-facing overview with troubleshooting scenarios.
- `checks.sql` / `run_checks.py` - integrity checks (orphans, duplicates) and a runner that prints PASS/WARN/FAIL.

## Data model
- `products` - one row per drug product (`product_id` primary key).
- `active_ingredients` - many per product (flattened from the nested `active_ingredients` list).
- `packages` - many per product (flattened from the nested `packaging` list).
- `recalls` - one row per FDA recall (`recall_number` primary key). Loaded by `ingest_recalls.py`.
- `recall_ndcs` - many per recall (from `openfda.product_ndc`, up to 16; only ~24% of recalls have any). No foreign key to `products`, because `products` is only a sample, so most recall NDCs do not match a product.

The recall tables use their own `recalls_metadata` in `db.py`, separate from `metadata`. `ingest.py` drops and recreates `metadata`, so keeping them separate means reloading products never wipes recalls (and vice versa). Do not merge them. One FDA recall with a blank `recall_number` is dropped on purpose (it cannot be a primary key), and `ingest_recalls.py` logs a warning for it and for any repeated recall number.

## Data quirk: repeated NDCs
`product_ndc` is NOT unique in `products`. openFDA keeps several label versions per NDC, and
`product_id` = `<product_ndc>_<spl_id>` (verified for all 33 repeated NDCs, 75 rows, some with 3-4 versions).
`run_checks.py` reports this as WARN, not FAIL. Any endpoint that counts or looks up by NDC (step 2) must use
only the row with the latest `marketing_start_date` for each NDC, otherwise it will overcount or return stale labels.

## API rules (learned the hard way)
- Every list endpoint must sort by a UNIQUE tiebreaker as the last sort key (`product_ndc` for products, `recall_number` for recalls). Many rows tie on brand name or report date, and without a tiebreaker paging repeats some rows and skips others.
- Response fields that can be null in the data must be `| None = None` in `schemas.py`, or one null row turns a whole page into a 500.
- The recall detail route is `/recalls/{recall_number:path}` on purpose. One real FDA recall is numbered `N/A`, and a plain `{recall_number}` stops at the slash and returns a generic 404 before reaching our code. Keep the `:path`.
- `/products/{ndc}/recalls` reads `recall_ndcs`, not `products`, because `products` is only a sample. A valid NDC with no recalls returns total 0, and a malformed NDC returns 422 (a typo must not look like "no recalls").

## Recall analytics rules (analytics.py)
- The recalls table holds only the newest ~10,000 recalls, so the OLDEST month may be partial. Reports are weekly, so a full month must have a report dated in its first 7 days. If the oldest recall is dated after the 7th, that month is excluded. `tests` fail loudly if report dates stop being on one weekday.
- Spike = z-score above 2 against the previous 12 months (mean and sample stdev, month itself not included). Months with no recalls count as 0. Fewer than 12 months of history, or a flat history (stdev 0), means not scored. Ties in the top-3 reasons/firms are broken by name.
- Reason categories come from `REASON_RULES`, checked in order, first match wins (specific problems first, the broad CGMP bucket after them, catch-alls last). Never use the keyword `potent` (it matches "potential"). `Other` was 2.5% when written, and a test fails if it passes 10%.
- Tests with made-up data use a TEMP table named `recalls` that shadows the real one for one connection and is rolled back, so real data is never touched. Every rule above has a test that was proven to fail when the code was deliberately broken.

## AI summary rules (insights.py)
- `HF_TOKEN` lives in `.env`. Never print it, log it, or put it in an error message (`AIError` messages are written to be safe). No extra package: the client uses `requests` against `https://router.huggingface.co/v1/chat/completions`.
- The AI only rephrases facts our code computed. The guardrail (`check_summary`) rejects any number not in the facts text, vague words like "hundreds", and "products"/"items" used for the recalls (names of firms and categories are excluded from that check), and then the template (`template_summary`) is used. Every result carries `source` ("ai" or "template") and `fallback_reason`. Do not weaken the guardrail to get more AI output.
- After the first failed AI call in a request, the remaining spikes skip the AI (one outage = one timeout).
- Cache = Postgres table `insight_cache` (created on first use with `CREATE TABLE IF NOT EXISTS`, not in any MetaData, so reloads never wipe it). Key = hash of prompt version + model + facts. Only validated AI summaries are cached. Bump `PROMPT_VERSION` when the prompt changes.
- Tests must NEVER call the real AI: `tests/test_insights.py` has an autouse fixture that makes any real `requests.post` fail, uses a fake client, and uses a TEMP `insight_cache`. Keep it that way.
- The default model (`meta-llama/Llama-3.1-8B-Instruct`) was checked on 2026-10-24: 6/6 real spikes passed the guardrail in 3 runs (about 3 s for all six). After changing the model or prompt, re-check with `.\venv\Scripts\python.exe insights.py`.
- KNOWN LIMIT: the guardrail checks numbers, not claims. A model can link two separate facts (e.g. a firm and a reason) into a statement the facts never make. Fixing that means tightening the prompt and bumping `PROMPT_VERSION`, not loosening the guardrail. `PROMPT_VERSION` is 3. Version 1 linked a firm to a reason and said "products". Version 2 still put reasons and a firm in one sentence, wrote "the FDA reported" (10 of 24 samples) and sometimes computed its own figures. Version 3 forbids all of that (24 of 24 real samples were clean). The guardrail still cannot catch true-but-derived statements (e.g. "the majority of the recalls"), repetition, or "significant spike" being read as statistical.
- Changing the prompt: bump `PROMPT_VERSION`, run `.\venv\Scripts\python.exe insights.py`, and read every summary against its facts. Old cache rows stay in `insight_cache` but are never used again.

## Commands
- Run the tests: `.\venv\Scripts\python.exe -m pytest` (143 tests in `tests/`, most run against the real database).
- Run the API: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`, then open http://127.0.0.1:8000/docs.
- Load data: `.\venv\Scripts\python.exe ingest.py` (drops and recreates the tables each run, so it is safe to re-run).
- Load recalls: `.\venv\Scripts\python.exe ingest_recalls.py [number_of_records]` (default 10,000 newest by `report_date`; safe to re-run).
- Check data integrity: `.\venv\Scripts\python.exe run_checks.py` (SQL in `checks.sql`; exits 1 only on FAIL, not WARN).

## Roadmap
1. Ingest openFDA NDC data into Postgres (done in step 1).
2. FastAPI endpoints over the data (built and covered by pytest). Endpoints that count or look up by NDC use the latest
   `marketing_start_date` per NDC (see "Data quirk" above).
