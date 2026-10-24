# `db.py`: the database connection and tables

**Job:** connects Python to PostgreSQL and describes every table.

**Used by:** every other Python file. Nothing talks to the database without going through `db.py`.

## 1. Reading the password safely

```python
load_dotenv()

def get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. ...")
    return create_engine(
        normalize_database_url(url),
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
    )
```

- `load_dotenv()` reads `.env` into environment variables, but **doesn't override** one that's already set. So a `DATABASE_URL` set in PowerShell (to load data into Neon) or by Render wins, and `.env` is only the local fallback.
- `os.environ.get("DATABASE_URL")` grabs the connection string by name. The password itself is never written in the code.
- `create_engine(...)` builds the **engine**: a pool of database connections the rest of the code borrows from.

| Setting | Why (added in step 8b for Neon) |
| --- | --- |
| `pool_pre_ping=True` | Tests each connection with a tiny query before using it, and quietly replaces a dead one. Neon drops connections when it sleeps |
| `pool_recycle=300` | Replaces any connection older than 5 minutes |
| `connect_timeout=10` | A request gives up after 10 seconds instead of hanging if the database can't be reached |

## 1b. Fixing the address format (`normalize_database_url`)

```python
_ACCEPTED_SCHEMES = ("postgres://", "postgresql://", "postgresql+psycopg://")
_DRIVER_SCHEME = "postgresql+psycopg://"
```

Neon shows `postgresql://...`, older hosts use `postgres://`, and SQLAlchemy needs the driver named (`postgresql+psycopg://`). This function swaps only the part before `://` and keeps everything after it, including `?sslmode=require&channel_binding=require`.

If the value starts with anything else, it raises `ValueError: DATABASE_URL must start with ... but it starts with (no scheme)`. The message **never repeats the address**, because it contains the password. (This exact error happened in step 8b when a command got pasted instead of the URL.)

## 2. Defining a table

```python
products = Table(
    "products", metadata,
    Column("product_id", String, primary_key=True),
    Column("product_ndc", String, index=True),
    Column("brand_name", String),
    ...
)
```

- `primary_key=True`: every product_id must be unique and present. Duplicate products are impossible.
- `index=True`: makes lookups by NDC fast.

## 3. Linking tables (foreign keys)

```python
active_ingredients = Table(
    "active_ingredients", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("product_id", String, ForeignKey("products.product_id"), index=True, nullable=False),
    Column("name", String),
    Column("strength", String),
)
```

- `ForeignKey("products.product_id")`: PostgreSQL refuses any ingredient that doesn't point to a real product. That's why the "orphan" checks always pass.
- `packages` uses the same pattern.

## The tables

| Table | Key | Links to | Registry |
| --- | --- | --- | --- |
| `products` | `product_id` | none | `metadata` |
| `active_ingredients` | `id` | products | `metadata` |
| `packages` | `id` | products | `metadata` |
| `recalls` | `recall_number` | none | `recalls_metadata` |
| `recall_ndcs` | one row per recall + drug code pair | recalls | `recalls_metadata` |

## Why there are two registries (`metadata` and `recalls_metadata`)

A **registry** is a list of tables that can be created or dropped together. `ingest.py` drops and recreates everything in `metadata`. If recalls were in the same list, reloading the drugs would silently wipe the recalls. So recalls have their own list, and each loader only touches its own tables.

## Who creates the tables on an empty database

On startup, `main.py` calls `metadata.create_all` and `recalls_metadata.create_all` (plus the `insight_cache` SQL). That only creates tables that are **missing**; it never drops or empties anything. That's how the fresh Neon database got its tables before any data was loaded.

## If you change this file

Changing a table here doesn't change the database until the matching loader is re-run (`ingest.py` or `ingest_recalls.py`), because the loaders drop and recreate their tables.
