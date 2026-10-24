"""Database connection and table definitions for InsightScope."""
import os

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, MetaData, String, Table, Text,
    UniqueConstraint, create_engine,
)

# Read DATABASE_URL from the .env file into environment variables.
# load_dotenv() does NOT override a variable that is already set in the real environment (its `override` setting
# is off by default). So a DATABASE_URL set in the shell (for example in PowerShell, to run ingest.py against Neon)
# or by Render wins over the value in .env, and .env is only the fallback for local development.
load_dotenv()

# The three ways a Postgres address is commonly written. Neon and Render show postgresql://, older tools and
# some hosts give postgres://, and SQLAlchemy needs the driver named: postgresql+psycopg://.
_ACCEPTED_SCHEMES = ("postgres://", "postgresql://", "postgresql+psycopg://")
_DRIVER_SCHEME = "postgresql+psycopg://"


def normalize_database_url(url):
    """Turn any accepted way of writing a Postgres address into the one form SQLAlchemy needs (postgresql+psycopg://).

    Only the scheme (the part before "://") is changed. Everything after it is kept exactly as written: the user,
    password, host, database name and every ?query parameter, such as Neon's ?sslmode=require&channel_binding=require.
    The error message never repeats the address, because it contains the password.
    """
    cleaned = (url or "").strip()
    for scheme in _ACCEPTED_SCHEMES:
        if cleaned.startswith(scheme):
            return _DRIVER_SCHEME + cleaned[len(scheme):]
    shown = cleaned.split("://", 1)[0] + "://" if "://" in cleaned else "(no scheme)"
    raise ValueError(
        "DATABASE_URL must start with postgres://, postgresql:// or postgresql+psycopg:// "
        f"but it starts with {shown}"
    )


def get_engine():
    """The connection pool for the database named in DATABASE_URL.

    Neon (the hosted Postgres) suspends its compute when it is idle and then drops the connections we were holding.
    A pooled connection that has died would make the next request fail, so:
      * pool_pre_ping=True tests each connection with a tiny query before using it, and quietly replaces a dead one
      * pool_recycle=300 replaces any connection older than 5 minutes, so we never keep one for long enough to be dropped
      * connect_timeout=10 stops a request waiting forever if the database cannot be reached at all
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Put it in .env (local) or in the environment (Render, or your shell).")
    return create_engine(
        normalize_database_url(url),
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
    )


metadata = MetaData()

# One row per drug product.
products = Table(
    "products", metadata,
    Column("product_id", String, primary_key=True),
    Column("product_ndc", String, index=True),
    Column("brand_name", String),
    Column("generic_name", String),
    Column("labeler_name", String),
    Column("dosage_form", String),
    Column("route", String),  # list flattened to "ORAL, TOPICAL"
    Column("product_type", String),
    Column("marketing_category", String),
    Column("application_number", String),
    Column("finished", Boolean),
    Column("marketing_start_date", Date),
    Column("marketing_end_date", Date),
    Column("pharm_class", Text),  # list flattened to a single string
)

# Many per product: a product can contain several active ingredients.
active_ingredients = Table(
    "active_ingredients", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("product_id", String, ForeignKey("products.product_id"), index=True, nullable=False),
    Column("name", String),
    Column("strength", String),
)

# Many per product: a product can be sold in several package sizes.
packages = Table(
    "packages", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("product_id", String, ForeignKey("products.product_id"), index=True, nullable=False),
    Column("package_ndc", String),
    Column("description", Text),
    Column("marketing_start_date", Date),
    Column("marketing_end_date", Date),
    Column("sample", Boolean),
)

# The recall tables get their OWN MetaData (their own table registry). ingest.py drops and recreates
# everything in `metadata` above, so keeping recalls separate means reloading products never wipes the
# recalls, and reloading recalls never touches products.
recalls_metadata = MetaData()

# One row per recall (a recall of one product by one firm).
recalls = Table(
    "recalls", recalls_metadata,
    Column("recall_number", String, primary_key=True),
    Column("recalling_firm", String),
    Column("product_description", Text),
    Column("reason_for_recall", Text),
    Column("classification", String),       # Class I (most serious), Class II, Class III
    Column("status", String),               # Ongoing, Completed, Terminated
    Column("voluntary_mandated", String),
    Column("distribution_pattern", Text),
    Column("state", String),
    Column("country", String),
    Column("recall_initiation_date", Date),
    Column("report_date", Date, index=True),
)

# Many per recall: one recall can list several NDCs (up to 16 in the data), and many recalls list none.
# There is deliberately no foreign key to products: our products table is only a sample, so most recall
# NDCs will not exist there.
recall_ndcs = Table(
    "recall_ndcs", recalls_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("recall_number", String, ForeignKey("recalls.recall_number"), index=True, nullable=False),
    Column("product_ndc", String, index=True, nullable=False),
    UniqueConstraint("recall_number", "product_ndc"),
)
