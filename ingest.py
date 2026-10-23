"""Step 1: pull NDC drug records from openFDA, clean them with pandas, load into Postgres.

Run with:  .\\venv\\Scripts\\python.exe ingest.py [number_of_records]
"""
import sys
import time

import pandas as pd
import requests

from db import active_ingredients, get_engine, metadata, packages, products

API_URL = "https://api.fda.gov/drug/ndc.json"
PAGE_SIZE = 1000          # openFDA's maximum records per request
DEFAULT_TOTAL = 5000      # "a few thousand"


def fetch_records(total):
    """Download records page by page. `skip` says how many records to jump over."""
    records = []
    while len(records) < total:
        limit = min(PAGE_SIZE, total - len(records))
        resp = requests.get(API_URL, params={"limit": limit, "skip": len(records)}, timeout=30)
        resp.raise_for_status()
        page = resp.json().get("results", [])
        if not page:
            break  # ran out of data
        records.extend(page)
        print(f"Fetched {len(records)} records")
        time.sleep(0.3)  # be polite to the free API (rate limited without a key)
    return records


def clean_text(series):
    """Trim whitespace and turn empty strings into proper nulls."""
    return series.astype("string").str.strip().replace("", pd.NA)


def to_date(series):
    """openFDA dates look like '20221018'. Bad or missing values become NaT (null)."""
    return pd.to_datetime(series, format="%Y%m%d", errors="coerce").dt.date


def build_products(records):
    rows = []
    for r in records:
        rows.append({
            "product_id": r.get("product_id"),
            "product_ndc": r.get("product_ndc"),
            "brand_name": r.get("brand_name"),
            "generic_name": r.get("generic_name"),
            "labeler_name": r.get("labeler_name"),
            "dosage_form": r.get("dosage_form"),
            # route and pharm_class are lists, so join them into one readable string
            "route": ", ".join(r.get("route") or []) or None,
            "product_type": r.get("product_type"),
            "marketing_category": r.get("marketing_category"),
            "application_number": r.get("application_number"),
            "finished": r.get("finished"),
            "marketing_start_date": r.get("marketing_start_date"),
            "marketing_end_date": r.get("marketing_end_date"),
            "pharm_class": ", ".join(r.get("pharm_class") or []) or None,
        })
    df = pd.DataFrame(rows)

    # Cleaning
    for col in ["product_ndc", "brand_name", "generic_name", "labeler_name", "dosage_form",
                "route", "product_type", "marketing_category", "application_number", "pharm_class"]:
        df[col] = clean_text(df[col])
    for col in ["marketing_start_date", "marketing_end_date"]:
        df[col] = to_date(df[col])
    df = df.dropna(subset=["product_id"]).drop_duplicates(subset="product_id")
    return df


def build_children(records, key, columns):
    """Flatten a nested list (e.g. 'packaging') into one row per list item.

    Each output row carries the parent's product_id so the tables can be joined.
    """
    rows = []
    for r in records:
        for item in r.get(key) or []:
            rows.append({"product_id": r.get("product_id"), **item})
    df = pd.DataFrame(rows, columns=["product_id", *columns])
    return df


def build_active_ingredients(records):
    df = build_children(records, "active_ingredients", ["name", "strength"])
    for col in ["name", "strength"]:
        df[col] = clean_text(df[col])
    return df.dropna(subset=["product_id", "name"]).drop_duplicates()


def build_packages(records):
    df = build_children(
        records, "packaging",
        ["package_ndc", "description", "marketing_start_date", "marketing_end_date", "sample"],
    )
    for col in ["package_ndc", "description"]:
        df[col] = clean_text(df[col])
    for col in ["marketing_start_date", "marketing_end_date"]:
        df[col] = to_date(df[col])
    return df.dropna(subset=["product_id"]).drop_duplicates(subset=["product_id", "package_ndc"])


def load(engine, products_df, ingredients_df, packages_df):
    """Recreate the tables, then insert. Parent table first so foreign keys are satisfied."""
    metadata.drop_all(engine)
    metadata.create_all(engine)
    # Convert pandas nulls (NA/NaT/NaN) to None so Postgres stores real NULLs.
    for table, df in [(products, products_df), (active_ingredients, ingredients_df), (packages, packages_df)]:
        rows = df.astype(object).where(df.notna(), None).to_dict("records")
        with engine.begin() as conn:  # one transaction per table
            conn.execute(table.insert(), rows)
        print(f"Loaded {len(rows)} rows into {table.name}")


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TOTAL
    records = fetch_records(total)
    products_df = build_products(records)
    ingredients_df = build_active_ingredients(records)
    packages_df = build_packages(records)
    # Drop child rows whose parent was removed during cleaning.
    valid = set(products_df["product_id"])
    ingredients_df = ingredients_df[ingredients_df["product_id"].isin(valid)]
    packages_df = packages_df[packages_df["product_id"].isin(valid)]
    load(get_engine(), products_df, ingredients_df, packages_df)


if __name__ == "__main__":
    main()
