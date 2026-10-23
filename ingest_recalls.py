"""Step 4: pull recent FDA drug recalls from openFDA, clean them with pandas, load them into Postgres.

Run with:  .\\venv\\Scripts\\python.exe ingest_recalls.py [number_of_records]
"""
import logging
import sys
import time

import pandas as pd
import requests

from db import get_engine, recall_ndcs, recalls, recalls_metadata
from ingest import clean_text, to_date  # same cleaning helpers as the products load

log = logging.getLogger("ingest_recalls")

API_URL = "https://api.fda.gov/drug/enforcement.json"
PAGE_SIZE = 1000          # openFDA's maximum records per request
DEFAULT_TOTAL = 10000     # the most recent ~10,000 recalls


def get_page(skip, limit):
    """Fetch one page, newest recalls first. Retries a few times if the API is busy or briefly down."""
    for attempt in range(1, 4):
        resp = requests.get(
            API_URL,
            params={"limit": limit, "skip": skip, "sort": "report_date:desc"},
            timeout=30,
        )
        if resp.status_code == 429 or resp.status_code >= 500:  # rate limited or server trouble
            time.sleep(2 * attempt)
            continue
        resp.raise_for_status()  # any other error (like a bad request) stops the script right away
        return resp.json().get("results", [])
    resp.raise_for_status()  # still failing after 3 tries: raise the error


def fetch_records(total):
    """Download everything into memory. The database is not touched until this has fully succeeded."""
    records = []
    while len(records) < total:
        page = get_page(len(records), min(PAGE_SIZE, total - len(records)))
        if not page:
            break  # ran out of data
        records.extend(page)
        print(f"Fetched {len(records)} records")
        time.sleep(0.3)  # be polite to the free API
    return records


def build_recalls(records):
    rows = [{
        "recall_number": r.get("recall_number"),
        "recalling_firm": r.get("recalling_firm"),
        "product_description": r.get("product_description"),
        "reason_for_recall": r.get("reason_for_recall"),
        "classification": r.get("classification"),
        "status": r.get("status"),
        "voluntary_mandated": r.get("voluntary_mandated"),
        "distribution_pattern": r.get("distribution_pattern"),
        "state": r.get("state"),
        "country": r.get("country"),
        "recall_initiation_date": r.get("recall_initiation_date"),
        "report_date": r.get("report_date"),
    } for r in records]
    df = pd.DataFrame(rows)

    # Cleaning: trim whitespace and turn blanks ("") into real nulls
    for col in ["recall_number", "recalling_firm", "product_description", "reason_for_recall", "classification",
                "status", "voluntary_mandated", "distribution_pattern", "state", "country"]:
        df[col] = clean_text(df[col])
    # Dates arrive as '20240131'. Bad or missing values become null.
    for col in ["recall_initiation_date", "report_date"]:
        df[col] = to_date(df[col])

    # A recall_number is the primary key, so rows without one cannot be loaded. Say so instead of dropping silently.
    missing = int(df["recall_number"].isna().sum())
    if missing:
        log.warning("Dropping %d record(s) with a missing or blank recall_number", missing)
    df = df.dropna(subset=["recall_number"])

    # Two recalls sharing a number would collide on the primary key. Keep the first (the newest, since the
    # download is sorted newest first) and warn, so the data loss is visible.
    counts = df["recall_number"].value_counts()
    for number, times in counts[counts > 1].items():
        log.warning("recall_number %s appears %d times in the fetched data. Keeping the first, dropping %d",
                    number, times, times - 1)
    return df.drop_duplicates(subset="recall_number")


def build_recall_ndcs(records):
    """Flatten openfda.product_ndc (a list that may be missing or hold up to 16 codes) into one row per code."""
    rows = []
    for r in records:
        for ndc in (r.get("openfda") or {}).get("product_ndc") or []:
            rows.append({"recall_number": r.get("recall_number"), "product_ndc": ndc})
    df = pd.DataFrame(rows, columns=["recall_number", "product_ndc"])
    for col in ["recall_number", "product_ndc"]:
        df[col] = clean_text(df[col])
    return df.dropna().drop_duplicates()


def to_rows(df):
    """Convert pandas nulls (NA/NaT/NaN) to None so Postgres stores real NULLs."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def load(engine, recalls_df, ndcs_df):
    """Replace both tables inside ONE transaction: it either fully succeeds or changes nothing.

    Postgres can roll back table drops and creations too, so if anything fails halfway, the old recall
    tables are still there exactly as they were.
    """
    with engine.begin() as conn:
        recalls_metadata.drop_all(conn)
        recalls_metadata.create_all(conn)
        for table, df in [(recalls, recalls_df), (recall_ndcs, ndcs_df)]:  # parent first (foreign key)
            rows = to_rows(df)
            if rows:
                conn.execute(table.insert(), rows)
            print(f"Loaded {len(rows)} rows into {table.name}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    total = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TOTAL
    records = fetch_records(total)
    if not records:
        sys.exit("No records fetched, so the database was left untouched.")
    recalls_df = build_recalls(records)
    ndcs_df = build_recall_ndcs(records)
    # Drop child rows whose parent was removed during cleaning.
    ndcs_df = ndcs_df[ndcs_df["recall_number"].isin(set(recalls_df["recall_number"]))]
    load(get_engine(), recalls_df, ndcs_df)


if __name__ == "__main__":
    main()
