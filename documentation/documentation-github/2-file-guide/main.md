# `main.py`: the API

**Job:** defines every endpoint. When someone visits a URL like `/products/76961-101`, the matching function in this file runs and returns the answer.

**Start it:** `.\venv\Scripts\python.exe -m uvicorn main:app --reload`, then open http://127.0.0.1:8000/docs.

## Top of the file: setup

```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("insightscope")

app = FastAPI(title="InsightScope", description="Drug product data from the openFDA NDC directory")
engine = get_engine()  # one engine (connection pool) shared by every request
```

- `app` is the API itself. `uvicorn main:app` points at this line.
- `engine` comes from `db.py` and is shared by all endpoints.

## The "latest version" view (the duplicate-NDC rule)

```python
latest = (
    select(products)
    .ext(distinct_on(products.c.product_ndc))
    .order_by(
        products.c.product_ndc,
        products.c.marketing_start_date.desc().nulls_last(),
        products.c.product_id,
    )
    .subquery("latest")
)
```

This keeps **one row per NDC**: the newest label version, with `product_id` breaking ties. Every product endpoint reads from `latest`, which is why the API counts 4,958 drugs instead of 5,000 rows.

## Logging every request

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms)
    return response
```

**Middleware** runs around every request. This produces log lines like `GET /products/0000-0000 -> 404 (4 ms)` in the terminal where the API runs. It's the first place to look when something is slow or failing.

## The safety net (503)

```python
@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    log.error("Database error on %s: %s", request.url.path, exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})
```

Any database error, anywhere, becomes a clean 503 for the user, while the real error goes to the log.

## Anatomy of an endpoint

```python
@app.get("/products/{ndc}", response_model=ProductDetail)
def get_product(ndc: str):
    with engine.connect() as conn:
        product = conn.execute(select(latest).where(latest.c.product_ndc == ndc)).mappings().first()
        if product is None:
            raise HTTPException(status_code=404, detail=f"No product found with NDC {ndc}")
        ...
    return ProductDetail(**product, active_ingredients=[...], packages=[...])
```

| Line | What it means |
| --- | --- |
| `@app.get("/products/{ndc}")` | This function answers GET requests to `/products/<something>` |
| `response_model=ProductDetail` | The answer must match the `ProductDetail` shape in `schemas.py` |
| `ndc: str` | The `{ndc}` part of the URL arrives as a text variable |
| `if product is None: raise HTTPException(404)` | **The 404 is literally an if statement** |
| `return ProductDetail(...)` | Returning normally sends a 200 |

## Where 422s come from (no if statement needed)

```python
limit: int = Query(25, ge=1, le=100),
offset: int = Query(0, ge=0),
```

`ge` = greater than or equal, `le` = less than or equal. FastAPI checks these rules **before** your function runs, and sends 422 on its own if a request breaks them. Search uses `min_length=2` the same way.

## All endpoints in this file

| Endpoint | Function's job |
| --- | --- |
| `GET /health` | Runs `SELECT 1` to prove the database answers |
| `GET /products` | Filtered, paged list from `latest` |
| `GET /products/{ndc}` | One product plus ingredients and packages |
| `GET /stats/labelers` | `GROUP BY` labeler, most products first |
| `GET /search?q=` | Case-insensitive match on brand or generic name |
| `GET /recalls` | Filtered, paged recalls, newest first, `recall_number` as tiebreaker |
| `GET /recalls/{recall_number:path}` | One recall; `:path` lets IDs like `N/A` work |
| `GET /products/{ndc}/recalls` | Recalls listing a drug code; 422 for a malformed NDC |
| `GET /analytics/recalls/monthly` | Calls `analytics.monthly_recalls` |
| `GET /analytics/recalls/reasons` | Calls `analytics.reason_categories`; 422 if start is after end |
| `GET /analytics/recalls/spikes` | Calls `analytics.recall_spikes` |
| `GET /insights/recalls/spikes` | Calls `insights.py`: each spike's facts plus an AI or template summary |
| `GET /reports/recalls.csv` | Calls `reports.recalls_csv`; optional start, end, classification; 422 for a bad range; sent as a download |
| `GET /reports/spikes.csv` | Calls `reports.spikes_csv`; reuses cached AI summaries |

The recall, analytics and insights endpoints follow the same patterns shown above. Open `main.py` and search for `@app.get` to jump between them.

## The dashboard mount (the very end of the file)

```python
import pathlib  # a module import, because "Path" below is FastAPI's Path

DASHBOARD_DIR = pathlib.Path(__file__).parent / "frontend" / "dist"

def mount_dashboard(application, directory):
    application.mount("/", StaticFiles(directory=directory, html=True), name="dashboard")
```

- Serves the built React files (`npm run build`) at `/`. `html=True` sends `index.html` for `/`.
- It only mounts if `frontend/dist/` exists, so the API still starts on a fresh clone.
- **It must stay last.** A mount at `/` matches every path, and FastAPI checks routes in order, so any route added after it would never be reached. A test in `tests/test_dashboard.py` proves this.
- **Why `import pathlib`:** `from pathlib import Path` would replace FastAPI's `Path` (used for route parameters) and break every test. This actually happened in step 7.

## Status codes at a glance

| Code | Comes from |
| --- | --- |
| 200 | The function returned normally |
| 404 | `raise HTTPException(status_code=404, ...)` in your code, or no route matched at all (FastAPI's generic "Not Found"; still JSON, even with the dashboard mounted) |
| 422 | `Query(...)` rules, or an explicit check like start-after-end |
| 503 | The `SQLAlchemyError` exception handler |
