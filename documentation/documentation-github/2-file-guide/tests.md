# `tests/`: automated tests

**Job:** code that calls your API and checks the answers are correct. 153 Python tests, plus 38 dashboard tests in `frontend/`.

**Run them all:**

```powershell
.\venv\Scripts\python.exe -m pytest
```

Add `-q` for shorter output. You want to see something like `149 passed, 4 skipped` before you build the dashboard, and `153 passed` after `npm run build`.

Dashboard tests (inside `frontend`): `npm test`. See [frontend.md](frontend.md).

## The test files

| File | Tests | What they cover |
| --- | --- | --- |
| `tests/test_api.py` | 14 | Health, product list, detail, labelers, search |
| `tests/test_recalls_api.py` | 28 | Recall endpoints, full paging, null fields, the N/A recall |
| `tests/test_ingest_recalls.py` | 3 | Duplicate and blank recall-number warnings, no database needed |
| `tests/test_analytics.py` | 48 | Spike math, partial months, keyword rules, real-data cross-checks |
| `tests/test_dashboard.py` | 10 | FastAPI serves the built dashboard; API routes and `/docs` still win; unknown paths stay 404; why the mount must be last. Four of them skip until `npm run build` |
| `tests/test_insights.py` | 50 | AI summaries with a fake client: good text, invented numbers, "products"/"items", timeouts, missing token, cache and prompt versions, no token leaks |

## Key patterns

**Calling the API without starting a server**

```python
client = TestClient(main.app)  # calls the app in-process, no server needed

def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "reachable"}
```

`assert` means "this must be true, or the test fails."

**Faking a database outage**

```python
def test_health_returns_503_when_database_is_down(monkeypatch):
    dead = create_engine("postgresql+psycopg://nobody:nopass@127.0.0.1:1/none", connect_args={"connect_timeout": 2})
    monkeypatch.setattr(main, "engine", dead)
    r = client.get("/health")
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

The insights tests never call the real AI: a safety net fails any test that tries to reach the network. The analytics tests use made-up data in a temporary table that's rolled back, so real data is never touched.
