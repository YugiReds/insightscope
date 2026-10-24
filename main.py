"""InsightScope API: read-only endpoints over the openFDA NDC data in Postgres.

Run with:  .\\venv\\Scripts\\python.exe -m uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs for the interactive API page.
"""
import logging
import pathlib  # a module import, because "Path" below is FastAPI's Path (for route parameters)
import threading
import time
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import SQLAlchemyError

import analytics
import insights
import reports
from db import active_ingredients, get_engine, metadata, packages, products, recall_ndcs, recalls, recalls_metadata
from schemas import (
    DatabaseHealth, Health, LabelerCount, MonthlyRecalls, ProductDetail, ProductPage, ProductRecallPage, ProductSummary,
    ReasonCategories, RecallDetail, RecallPage, SpikeInsights, SpikeReport,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("insightscope")

engine = get_engine()  # one engine (connection pool) shared by every request


def initialize_database(target=None):
    """Create every table that does not exist yet, so a brand-new EMPTY database (for example a fresh Neon one) works.

    It is safe to run on every start: it only creates what is missing and never drops, changes or empties anything.
    The tables stay empty until ingest.py and ingest_recalls.py load the data.
      * metadata and recalls_metadata hold the products and recalls tables (defined in db.py)
      * insight_cache (the saved AI summaries) is not in any metadata, by design, so it is created with its own SQL
    """
    target = target or engine
    metadata.create_all(target)
    recalls_metadata.create_all(target)
    with target.begin() as conn:
        conn.execute(insights.CREATE_CACHE_SQL)


def prepare_database(attempts=5, pause=time.sleep):
    """initialize_database, retried a few times, and it NEVER raises.

    Neon may be asleep when the API starts and take a few seconds to wake. If the database cannot be reached, the API
    must still start and answer /health, so this logs a warning and carries on instead of crashing. Returns True once
    the tables are ready.
    """
    for attempt in range(1, attempts + 1):
        try:
            initialize_database()
            log.info("Database tables are ready")
            return True
        except SQLAlchemyError as error:
            log.warning("Could not prepare the database tables (attempt %d of %d): %s", attempt, attempts, error.__class__.__name__)
            if attempt < attempts:
                pause(attempt * 3)
    log.error("Gave up preparing the database tables. /health/db shows whether the database can be reached.")
    return False


@asynccontextmanager
async def lifespan(application):
    # Done in a background thread so a slow or sleeping database never delays startup: /health must answer at once.
    threading.Thread(target=prepare_database, daemon=True).start()
    yield


app = FastAPI(title="InsightScope", description="Drug product data from the openFDA NDC directory", lifespan=lifespan)

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
    """Is the API process up? Answers at once and never touches the database. Render's health check calls this every
    few seconds, and a database call each time would stop Neon from ever going to sleep."""
    return Health(status="ok")


@app.get("/health/db", response_model=DatabaseHealth)
def health_db():
    """Is the API's database reachable? Runs a trivial query. If the database is down, the 503 handler above answers
    {"detail": "Database unavailable"}."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return DatabaseHealth(status="ok", database="reachable")


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


# --- recall analytics (the logic lives in analytics.py) ---

@app.get("/analytics/recalls/monthly", response_model=MonthlyRecalls)
def recalls_monthly():
    """Recalls per month (by report date), split by classification. A partly covered oldest month is left out."""
    with engine.connect() as conn:
        return analytics.monthly_recalls(conn)


@app.get("/analytics/recalls/reasons", response_model=ReasonCategories)
def recalls_by_reason(
    start: date | None = Query(None, description="Only recalls reported on or after this date (YYYY-MM-DD)"),
    end: date | None = Query(None, description="Only recalls reported on or before this date (YYYY-MM-DD)"),
):
    """Recall counts per reason category, using keyword rules. Reports how much landed in 'Other'."""
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must not be later than end")
    with engine.connect() as conn:
        return analytics.reason_categories(conn, start, end)


@app.get("/analytics/recalls/spikes", response_model=SpikeReport)
def recalls_spikes():
    """Months with unusually many recalls (z-score above 2 against the previous 12 months), with their top reasons and firms."""
    with engine.connect() as conn:
        return analytics.recall_spikes(conn)


# --- AI summaries of the spikes (the logic lives in insights.py) ---

@app.get("/insights/recalls/spikes", response_model=SpikeInsights)
def recall_spike_insights():
    """Each recall spike with its facts and a plain-English summary. The summary is written by an AI from those
    facts only, and falls back to a template if the AI is unavailable or says anything not in the facts."""
    with engine.begin() as conn:  # begin() commits when done, because good AI summaries are saved to the cache table
        return insights.spike_insights(conn, insights.get_client())


# --- CSV reports (the logic lives in reports.py) ---

CSV_RESPONSE = {200: {"description": "A CSV file download (UTF-8 with a byte order mark, so Excel reads accents correctly)", "content": {"text/csv": {}}}}


@app.get("/reports/recalls.csv", responses=CSV_RESPONSE)
def recalls_report(
    start: date | None = Query(None, description="Only recalls reported on or after this date (YYYY-MM-DD)"),
    end: date | None = Query(None, description="Only recalls reported on or before this date (YYYY-MM-DD)"),
    classification: str | None = Query(None, description="Exact class, e.g. 'Class I' (case-insensitive)"),
):
    """Download the recalls as a CSV file: one row per recall, newest first."""
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must not be later than end")
    with engine.connect() as conn:
        content, filename = reports.recalls_csv(conn, start, end, classification)
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=reports.download_headers(filename))


@app.get("/reports/spikes.csv", responses=CSV_RESPONSE)
def spikes_report():
    """Download the spike months with their summaries as a CSV file. Saved (cached) summaries are reused."""
    with engine.begin() as conn:  # begin() commits when done, because new good AI summaries are saved to the cache table
        content, filename = reports.spikes_csv(conn, insights.get_client())
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=reports.download_headers(filename))


# --- the dashboard (React app in frontend/, built into frontend/dist by `npm run build`) ---
# KEEP THIS AT THE VERY END OF THE FILE. A mount at "/" matches every path, and FastAPI checks routes in the order they
# were added, so anything registered after it would never be reached. Every API endpoint above, plus /docs and
# /openapi.json (which FastAPI adds when the app is created), come first and keep working.

DASHBOARD_DIR = pathlib.Path(__file__).parent / "frontend" / "dist"


def mount_dashboard(application, directory):
    """Serve the built dashboard at / (index.html for the root, and the files in assets/)."""
    application.mount("/", StaticFiles(directory=directory, html=True), name="dashboard")


if DASHBOARD_DIR.is_dir():  # not built yet (for example in a fresh clone): the API still works without it
    mount_dashboard(app, DASHBOARD_DIR)
