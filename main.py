"""InsightScope API: read-only endpoints over the openFDA NDC data in Postgres.

Run with:  .\\venv\\Scripts\\python.exe -m uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs for the interactive API page.
"""
import logging
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import SQLAlchemyError

from db import active_ingredients, get_engine, packages, products
from schemas import (
    Health, LabelerCount, ProductDetail, ProductPage, ProductSummary,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("insightscope")

app = FastAPI(title="InsightScope", description="Drug product data from the openFDA NDC directory")
engine = get_engine()  # one engine (connection pool) shared by every request

# The NDC table has several label versions per NDC (see CLAUDE.md). Every endpoint that counts or
# looks up by NDC reads from this "latest" view: one row per NDC, the one with the newest
# marketing_start_date. DISTINCT ON keeps the first row of each NDC in the ORDER BY order;
# product_id is a tiebreaker so the result is the same every time.
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

SUMMARY_COLUMNS = [
    latest.c.product_id, latest.c.product_ndc, latest.c.brand_name, latest.c.generic_name,
    latest.c.labeler_name, latest.c.dosage_form, latest.c.route, latest.c.marketing_start_date,
]


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with its status code and how long it took. Handy when debugging issues."""
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms)
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    """If the database is down or a query fails, return a clean 503 instead of a stack trace."""
    log.error("Database error on %s: %s", request.url.path, exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.get("/health", response_model=Health)
def health():
    """Checks that the API is up and can reach the database."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return Health(status="ok", database="reachable")


@app.get("/products", response_model=ProductPage)
def list_products(
    labeler: str | None = Query(None, description="Labeler name contains this text"),
    dosage_form: str | None = Query(None, description="Exact dosage form, e.g. 'TABLET'"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List products (latest label version per NDC), with filters and pagination."""
    conditions = []
    if labeler:
        conditions.append(latest.c.labeler_name.ilike(f"%{labeler}%"))
    if dosage_form:
        conditions.append(func.upper(latest.c.dosage_form) == dosage_form.upper())

    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(latest).where(*conditions)).scalar_one()
        rows = conn.execute(
            select(*SUMMARY_COLUMNS).where(*conditions)
            .order_by(latest.c.brand_name, latest.c.product_ndc)
            .limit(limit).offset(offset)
        ).mappings().all()
    return ProductPage(total=total, limit=limit, offset=offset, items=[dict(r) for r in rows])


@app.get("/products/{ndc}", response_model=ProductDetail)
def get_product(ndc: str):
    """Look up one product by NDC (e.g. 76961-101): latest label version, with ingredients and packages."""
    with engine.connect() as conn:
        product = conn.execute(select(latest).where(latest.c.product_ndc == ndc)).mappings().first()
        if product is None:
            raise HTTPException(status_code=404, detail=f"No product found with NDC {ndc}")
        ingredients = conn.execute(
            select(active_ingredients.c.name, active_ingredients.c.strength)
            .where(active_ingredients.c.product_id == product["product_id"])
            .order_by(active_ingredients.c.id)
        ).mappings().all()
        pkgs = conn.execute(
            select(packages).where(packages.c.product_id == product["product_id"]).order_by(packages.c.id)
        ).mappings().all()
    return ProductDetail(**product, active_ingredients=[dict(i) for i in ingredients],
                         packages=[dict(p) for p in pkgs])


@app.get("/stats/labelers", response_model=list[LabelerCount])
def top_labelers(limit: int = Query(10, ge=1, le=50)):
    """Labelers ranked by number of distinct NDCs (each NDC counted once, via its latest version)."""
    count = func.count().label("product_count")
    with engine.connect() as conn:
        rows = conn.execute(
            select(latest.c.labeler_name, count)
            .where(latest.c.labeler_name.is_not(None))
            .group_by(latest.c.labeler_name)
            .order_by(count.desc(), latest.c.labeler_name)
            .limit(limit)
        ).mappings().all()
    return [dict(r) for r in rows]


@app.get("/search", response_model=list[ProductSummary])
def search(q: str = Query(..., min_length=2, description="Text to find in brand or generic name"),
           limit: int = Query(25, ge=1, le=100)):
    """Search brand and generic names (case-insensitive, matches anywhere in the name)."""
    pattern = f"%{q}%"
    with engine.connect() as conn:
        rows = conn.execute(
            select(*SUMMARY_COLUMNS)
            .where(latest.c.brand_name.ilike(pattern) | latest.c.generic_name.ilike(pattern))
            .order_by(latest.c.brand_name, latest.c.product_ndc)
            .limit(limit)
        ).mappings().all()
    return [dict(r) for r in rows]
