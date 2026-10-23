"""Database connection and table definitions for InsightScope."""
import os

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, MetaData, String, Table, Text,
    create_engine,
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
