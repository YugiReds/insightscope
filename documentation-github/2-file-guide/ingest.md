# `ingest.py`: loading the drug products

**Job:** downloads drug records from the openFDA NDC directory, cleans them with pandas and loads them into the `products`, `active_ingredients` and `packages` tables.

**Run it:** `.\venv\Scripts\python.exe ingest.py` (or add a number, e.g. `ingest.py 3000`). Safe to re-run: it recreates its tables.

## The flow

```
fetch_records → build_products / build_active_ingredients / build_packages → load
```

## Key lines

**Downloading page by page**

```python
API_URL = "https://api.fda.gov/drug/ndc.json"
PAGE_SIZE = 1000          # openFDA's maximum records per request
DEFAULT_TOTAL = 5000

resp = requests.get(API_URL, params={"limit": limit, "skip": len(records)}, timeout=30)
resp.raise_for_status()
```

`skip` tells the FDA how many records to jump over, so each request gets the next 1,000. `raise_for_status()` stops the script if the FDA returns an error.

**Cleaning helpers** (also reused by `ingest_recalls.py`)

```python
def clean_text(series):
    """Trim whitespace and turn empty strings into proper nulls."""
    return series.astype("string").str.strip().replace("", pd.NA)

def to_date(series):
    """openFDA dates look like '20221018'. Bad or missing values become NaT (null)."""
    return pd.to_datetime(series, format="%Y%m%d", errors="coerce").dt.date
```

`errors="coerce"` is what keeps one bad date from crashing the whole load.

**Flattening nested lists into child rows**

```python
def build_children(records, key, columns):
    rows = []
    for r in records:
        for item in r.get(key) or []:
            rows.append({"product_id": r.get("product_id"), **item})
```

Each ingredient or package row carries its parent's `product_id`, which is how the tables link.

**Loading**

```python
metadata.drop_all(engine)
metadata.create_all(engine)
for table, df in [(products, products_df), (active_ingredients, ingredients_df), (packages, packages_df)]:
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    with engine.begin() as conn:  # one transaction per table
        conn.execute(table.insert(), rows)
```

- Products load first so the foreign keys are satisfied.
- `.where(df.notna(), None)` turns pandas' empty values into real database NULLs.

## Known weaknesses

| Weakness | Risk | Fixed in recalls loader? |
| --- | --- | --- |
| No retries | One FDA hiccup crashes the run | Yes |
| One transaction per table | A failure can leave half-loaded data | Yes |
| `print` instead of logging | Harder to debug | Partly (recalls uses logging warnings) |

The data is downloaded before the database is touched, so an FDA outage can't wipe existing data.
