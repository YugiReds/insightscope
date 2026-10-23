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
- `main.py` - FastAPI app (step 2): `/health`, `/products`, `/products/{ndc}`, `/stats/labelers`, `/search`. All NDC reads go through the `latest` subquery (one row per NDC, newest `marketing_start_date`).
- `schemas.py` - Pydantic response models for the API.
- `tests/test_api.py`, `pytest.ini` - API tests. `README.md` - public-facing overview with troubleshooting scenarios.
- `checks.sql` / `run_checks.py` - integrity checks (orphans, duplicates) and a runner that prints PASS/WARN/FAIL.

## Data model
- `products` - one row per drug product (`product_id` primary key).
- `active_ingredients` - many per product (flattened from the nested `active_ingredients` list).
- `packages` - many per product (flattened from the nested `packaging` list).

## Data quirk: repeated NDCs
`product_ndc` is NOT unique in `products`. openFDA keeps several label versions per NDC, and
`product_id` = `<product_ndc>_<spl_id>` (verified for all 33 repeated NDCs, 75 rows, some with 3-4 versions).
`run_checks.py` reports this as WARN, not FAIL. Any endpoint that counts or looks up by NDC (step 2) must use
only the row with the latest `marketing_start_date` for each NDC, otherwise it will overcount or return stale labels.

## Commands
- Run the tests: `.\venv\Scripts\python.exe -m pytest` (14 tests in `tests/test_api.py`, run against the real database).
- Run the API: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`, then open http://127.0.0.1:8000/docs.
- Load data: `.\venv\Scripts\python.exe ingest.py` (drops and recreates the tables each run, so it is safe to re-run).
- Check data integrity: `.\venv\Scripts\python.exe run_checks.py` (SQL in `checks.sql`; exits 1 only on FAIL, not WARN).

## Roadmap
1. Ingest openFDA NDC data into Postgres (done in step 1).
2. FastAPI endpoints over the data (built and covered by pytest). Endpoints that count or look up by NDC use the latest
   `marketing_start_date` per NDC (see "Data quirk" above).
