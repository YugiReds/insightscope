# `db.py`: the database connection and tables

**Job:** connects Python to PostgreSQL and describes every table.

**Used by:** every other Python file. Nothing talks to the database without going through `db.py`.

## 1. Reading the password safely

```python
from dotenv import load_dotenv
load_dotenv()

def get_engine():
    url = os.environ["DATABASE_URL"]
    ...
    return create_engine(url)
```

- `load_dotenv()` reads `.env` into environment variables.
- `os.environ["DATABASE_URL"]` grabs the connection string by name. The password itself is never written in the code.
- `create_engine(url)` builds the **engine**: a pool of database connections the rest of the code borrows from.

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

## If you change this file

Changing a table here doesn't change the database until the matching loader is re-run (`ingest.py` or `ingest_recalls.py`), because the loaders drop and recreate their tables.
