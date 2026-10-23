"""InsightScope API: read-only endpoints over the openFDA NDC data in Postgres.

Run with:  .\\venv\\Scripts\\python.exe -m uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs for the interactive API page.
"""
import logging
import time

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import SQLAlchemyError

from db import active_ingredients, get_engine, packages, products, recall_ndcs, recalls
from schemas import (
    Health, LabelerCount, ProductDetail, ProductPage, ProductRecallPage, ProductSummary,
    RecallDetail, RecallPage,
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


# --- recalls ---

RECALL_SUMMARY_COLUMNS = [
    recalls.c.recall_number, recalls.c.recalling_firm, recalls.c.product_description,
    recalls.c.reason_for_recall, recalls.c.classification, recalls.c.status,
    recalls.c.voluntary_mandated, recalls.c.state, recalls.c.country,
    recalls.c.recall_initiation_date, recalls.c.report_date,
]

# Newest recalls first. Thousands of recalls share a report_date, so recall_number (unique) is the
# tiebreaker. Without it the order of tied rows is not fixed, and paging can repeat some recalls and skip others.
RECALL_ORDER = (recalls.c.report_date.desc().nulls_last(), recalls.c.recall_number.desc())

# An NDC looks like 12345-678: 4-5 digits, a hyphen, then 1-4 digits. Checking the shape stops a typo from
# being answered with "no recalls", which would wrongly look like good news.
NDC_PATTERN = r"^\d{4,5}-\d{1,4}$"


def contains(column, text_value):
    """Case-insensitive 'contains' match where % and _ typed by the user are matched literally, not as wildcards."""
    escaped = text_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


@app.get("/recalls", response_model=RecallPage)
def list_recalls(
    classification: str | None = Query(None, description="Exact class, e.g. 'Class I' (case-insensitive)"),
    status: str | None = Query(None, description="Exact status, e.g. 'Ongoing' (case-insensitive)"),
    recalling_firm: str | None = Query(None, description="Firm name contains this text"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List recalls, newest first, with filters and pagination."""
    conditions = []
    if classification:
        conditions.append(func.lower(recalls.c.classification) == classification.lower())
    if status:
        conditions.append(func.lower(recalls.c.status) == status.lower())
    if recalling_firm:
        conditions.append(contains(recalls.c.recalling_firm, recalling_firm))

    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(recalls).where(*conditions)).scalar_one()
        rows = conn.execute(
            select(*RECALL_SUMMARY_COLUMNS).where(*conditions)
            .order_by(*RECALL_ORDER).limit(limit).offset(offset)
        ).mappings().all()
    return RecallPage(total=total, limit=limit, offset=offset, items=[dict(r) for r in rows])


@app.get("/recalls/{recall_number:path}", response_model=RecallDetail)
def get_recall(recall_number: str):
    """One recall with all its details and the list of NDCs it covers (can be empty).

    The ':path' lets the recall number contain slashes. A normal {recall_number} stops at the first '/',
    so the FDA's real recall number 'N/A' could never be reached.
    """
    with engine.connect() as conn:
        recall = conn.execute(select(recalls).where(recalls.c.recall_number == recall_number)).mappings().first()
        if recall is None:
            raise HTTPException(status_code=404, detail=f"No recall found with recall number {recall_number}")
        ndcs = conn.execute(
            select(recall_ndcs.c.product_ndc)
            .where(recall_ndcs.c.recall_number == recall_number)
            .order_by(recall_ndcs.c.product_ndc)
        ).scalars().all()
    return RecallDetail(**recall, product_ndcs=list(ndcs))


@app.get("/products/{ndc}/recalls", response_model=ProductRecallPage)
def get_product_recalls(
    ndc: str = Path(..., pattern=NDC_PATTERN, description="Product NDC, e.g. 16729-455"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Has this NDC been recalled? Looks in recall_ndcs, not in products, so it works for any recalled NDC
    even if it is not in our products sample. An NDC with no recalls on file returns total 0, not a 404."""
    condition = recalls.c.recall_number.in_(
        select(recall_ndcs.c.recall_number).where(recall_ndcs.c.product_ndc == ndc)
    )
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(recalls).where(condition)).scalar_one()
        rows = conn.execute(
            select(*RECALL_SUMMARY_COLUMNS).where(condition)
            .order_by(*RECALL_ORDER).limit(limit).offset(offset)
        ).mappings().all()
    return ProductRecallPage(product_ndc=ndc, total=total, limit=limit, offset=offset,
                             items=[dict(r) for r in rows])
