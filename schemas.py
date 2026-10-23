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


# --- recalls ---
# Every field except recall_number is optional: the FDA data has gaps (for example 176 recalls with no state),
# and a required field here would turn any such row into a 500 error.

class RecallSummary(BaseModel):
    recall_number: str
    recalling_firm: str | None = None
    product_description: str | None = None
    reason_for_recall: str | None = None
    classification: str | None = None
    status: str | None = None
    voluntary_mandated: str | None = None
    state: str | None = None
    country: str | None = None
    recall_initiation_date: date | None = None
    report_date: date | None = None


class RecallDetail(RecallSummary):
    distribution_pattern: str | None = None
    product_ndcs: list[str]   # empty for the many recalls that list no NDC


class RecallPage(BaseModel):
    total: int       # how many recalls match the filters (not just this page)
    limit: int
    offset: int
    items: list[RecallSummary]


class ProductRecallPage(RecallPage):
    product_ndc: str
