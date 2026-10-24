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


# --- recall analytics ---

class Coverage(BaseModel):
    """Which months the data covers fully. The recalls table holds only the newest ~10,000 recalls."""
    oldest_report_date: date
    newest_report_date: date
    first_full_month: str                      # "YYYY-MM": the first month included in the analysis
    excluded_oldest_month: str | None = None   # set when the oldest month is only partly covered
    newest_month_may_be_incomplete: bool       # more weekly reports may still arrive for the newest month


class MonthlyRecallCount(BaseModel):
    month: str                                 # "YYYY-MM"
    total: int
    by_classification: dict[str, int]


class MonthlyRecalls(BaseModel):
    coverage: Coverage | None = None
    classifications: list[str]
    months: list[MonthlyRecallCount]


class CategoryCount(BaseModel):
    category: str
    recalls: int
    share: float                               # fraction of all recalls in the range, 0 to 1


class OtherReason(BaseModel):
    reason: str
    recalls: int


class ReasonCategories(BaseModel):
    start: date | None = None
    end: date | None = None
    total: int
    categories: list[CategoryCount]
    other_share: float                         # how much landed in "Other": the yardstick for the keyword rules
    top_other_reasons: list[OtherReason]       # most common reasons no rule matched


class ReasonTotal(BaseModel):
    category: str
    recalls: int


class FirmTotal(BaseModel):
    recalling_firm: str
    recalls: int


class Spike(BaseModel):
    month: str
    recalls: int
    baseline_mean: float                       # average monthly count over the previous 12 months
    baseline_stddev: float
    z_score: float
    top_reason_categories: list[ReasonTotal]
    top_recalling_firms: list[FirmTotal]


class SpikeFacts(Spike):
    """A spike's numbers plus how much of the month one firm explains. Computed by our code, never by the AI."""
    top_firm_share_pct: int                    # the top firm's recalls as a percent of the month's recalls
    driver: str                                # one_firm (50% or more), large_share (25-49%), spread, or unknown


class InsightSpike(BaseModel):
    month: str
    facts: SpikeFacts
    summary: str
    source: str                                # "ai" or "template"
    fallback_reason: str | None = None         # why the template was used, when source is "template"
    cached: bool                               # true if an earlier AI summary was reused


class SpikeInsights(BaseModel):
    model: str
    spikes: list[InsightSpike]


class SpikeReport(BaseModel):
    method: str
    threshold: float
    baseline_months: int
    months_scored: int                         # months that had a usable 12-month baseline
    coverage: Coverage | None = None
    spikes: list[Spike]
