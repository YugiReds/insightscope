"""Database connection and table definitions for InsightScope."""
import os

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, MetaData, String, Table, Text,
    UniqueConstraint, create_engine,
)

# Read DATABASE_URL from the .env file into environment variables.
load_dotenv()


def get_engine():
    url = os.environ["DATABASE_URL"]
    # We use the psycopg v3 driver; SQLAlchemy needs the scheme to say so.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return create_engine(url)


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
