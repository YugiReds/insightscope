# `tests/`: automated tests

**Job:** code that calls your API and checks the answers are correct. 270 Python tests, plus 73 dashboard tests in `frontend/`. GitHub Actions runs all of them on every push (see [config-files.md](config-files.md)).

**Run them all:**

```powershell
.\venv\Scripts\python.exe -m pytest
```

Add `-q` for shorter output. You want to see something like `270 passed` once the dashboard is built. In CI it says `269 passed, 1 skipped`: the `.env` fallback test skips there because CI has no `.env`. Before `npm run build`, 4 dashboard tests show as skipped.

Dashboard tests (inside `frontend`): `npm test`. See [frontend.md](frontend.md).

## The test files

| File | Tests | What they cover |
| --- | --- | --- |
| `tests/test_api.py` | 14 | Health (`/health` and `/health/db`), product list, detail, labelers, search |
| `tests/test_recalls_api.py` | 28 | Recall endpoints, full paging, null fields, the N/A recall |
| `tests/test_ingest_recalls.py` | 3 | Duplicate and blank recall-number warnings, no database needed |
| `tests/test_analytics.py` | 48 | Spike math, partial months, keyword rules, real-data cross-checks |
| `tests/test_dashboard.py` | 10 | FastAPI serves the built dashboard; API routes and `/docs` still win; unknown paths stay 404; why the mount must be last. Four of them skip until `npm run build` |
| `tests/test_reports.py` | 49 | Both CSVs: headers, row counts vs. the database, filters, 422s, download header, CSV-injection guard, byte order mark, no AI calls when cached |
| `tests/test_deploy_ready.py` | about 35 | Step 8b: address normalization (all three prefixes, query parameters kept, password never in the error), engine settings, `/health` never touching the database, `/health/db` 503, startup table creation and retries, `.env` not overriding the shell, `render.yaml` build command |
| `tests/test_ci_setup.py` | 31 | Step 9: the seed's safety guard, the shape of the made-up data, and the workflow file (versions match `render.yaml`, no secrets, actions pinned to commit SHAs) |
| `tests/test_insights.py` | 50 | AI summaries with a fake client: good text, invented numbers, "products"/"items", timeouts, missing token, cache and prompt versions, no token leaks |

## Key patterns

**Calling the API without starting a server**

```python
client = TestClient(main.app)  # calls the app in-process, no server needed

def test_health_db_ok():
    r = client.get("/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "reachable"}
```

`assert` means "this must be true, or the test fails."

**Faking a database outage**

```python
def test_health_db_returns_503_when_database_is_down(monkeypatch):
    dead = create_engine("postgresql+psycopg://nobody:nopass@127.0.0.1:1/none", connect_args={"connect_timeout": 2})
    monkeypatch.setattr(main, "engine", dead)
    r = client.get("/health/db")
    assert r.status_code == 503
```

`monkeypatch` swaps the real database for one that doesn't exist, for this test only.

**Asking the database for the right answer**

```python
def test_total_counts_each_ndc_once(db):
    distinct_ndcs = db.execute(text("SELECT COUNT(DISTINCT product_ndc) FROM products")).scalar()
    assert client.get("/products", params={"limit": 1}).json()["total"] == distinct_ndcs
```

Instead of hard-coding "4,958," the test computes it with SQL. The tests keep working after a reload.

**Testing one rule against many inputs**

```python
@pytest.mark.parametrize("params", [{"limit": 500}, {"limit": 0}, {"offset": -1}])
def test_bad_pagination_is_rejected_with_422(params):
    assert client.get("/products", params=params).status_code == 422
```

## "Testing the tests"

A test that can never fail is useless. Each round, Claude Code broke the code on purpose to prove the tests catch it:

| Deliberate break | Tests that failed |
| --- | --- |
| Removed the recall sort tiebreaker | 4 |
| Made `state` required | 7 |
| Reverted the N/A route fix | 2 |
| Included a month in its own baseline | 7 |
| Disabled the partial-month rule | 5 |
| Used the keyword "potent" | 1 |
| AI number check switched off | 6 |
| AI guardrail never called | 9 |
| AI cache key ignores the facts | 3 |
| AI "products"/"items" check switched off | 4 |
| Dashboard: AI/Template badge swapped | 7 |
| Dashboard: 422 shown as a generic error | 1 |
| Dashboard: "no recalls" shown as found | 2 |
| Dashboard: unreachable API reported as a database problem | 1 |
| Reports: CSV-injection guard removed | 10 |
| Reports: end-date filter ignored | 5 |
| Reports: byte order mark removed | 4 |
| Reports: summary cache ignored | 2 |
| Dashboard: chart-collapsing print rule put back | 1 |
| Deploy: tables dropped or startup blocked, `/health/db` broken, and 9 more (step 8b) | all caught |
| Dashboard: database-check throttle and outage-recovery reset broken | all caught |

The insights tests never call the real AI: a safety net fails any test that tries to reach the network. The analytics tests use made-up data in a temporary table that's rolled back, so real data is never touched.

## `tests/seed_ci_data.py`: the CI database's made-up data

GitHub's machine starts with an empty Postgres, so this script creates the tables and fills them: 18 products, 412 recalls, 141 recall–NDC links. Every name is invented ("Example Pharma Inc"), and there's no randomness or "today", so every run gives the same rows.

```python
CI_DATABASE_NAME = "insightscope_ci"
...
    if name != CI_DATABASE_NAME:
        raise SeedRefused("Refusing to run: the database name in DATABASE_URL must be exactly 'insightscope_ci' ...")
```

**The guard:** the script deletes every product and recall row before inserting, so it refuses any database not named exactly `insightscope_ci`, and it never reads `.env`. Its error messages never show the address, because the address holds the password.

**Why made-up data and not real openFDA data:** real data changes every week and the download can be rate limited, so a test could go red with no code change. Fixed data means red always means "the code broke". The data is shaped to contain what the tests look for: repeated NDCs, weekly Wednesday reports, two spikes, the `N/A` recall, cells starting with `+` or `=`, and a firm name with a comma.
