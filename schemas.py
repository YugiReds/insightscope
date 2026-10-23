"""Response models: they describe the JSON shape each endpoint returns.

FastAPI uses them to validate responses and to generate the /docs page automatically.
"""
from datetime import date

from pydantic import BaseModel


class Ingredient(BaseModel):
    name: str
    strength: str | None = None


class Package(BaseModel):
    package_ndc: str | None = None
    description: str | None = None
    marketing_start_date: date | None = None
    marketing_end_date: date | None = None
    sample: bool | None = None


class ProductSummary(BaseModel):
    product_id: str
    product_ndc: str | None = None
    brand_name: str | None = None
    generic_name: str | None = None
    labeler_name: str | None = None
    dosage_form: str | None = None
    route: str | None = None
    marketing_start_date: date | None = None


class ProductDetail(ProductSummary):
    product_type: str | None = None
    marketing_category: str | None = None
    application_number: str | None = None
    finished: bool | None = None
    marketing_end_date: date | None = None
    pharm_class: str | None = None
    active_ingredients: list[Ingredient]
    packages: list[Package]


class ProductPage(BaseModel):
    total: int       # how many products match the filters (not just this page)
    limit: int
    offset: int
    items: list[ProductSummary]


class LabelerCount(BaseModel):
    labeler_name: str
    product_count: int


class Health(BaseModel):
    status: str
    database: str
