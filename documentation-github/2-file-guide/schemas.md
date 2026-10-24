# `schemas.py`: the shape of every response

**Job:** describes exactly which fields each API response contains and what type each one is. FastAPI uses these to check responses and to build the `/docs` page automatically.

These are **Pydantic models**: Python classes that describe data.

## Example

```python
class ProductSummary(BaseModel):
    product_id: str
    product_ndc: str | None = None
    brand_name: str | None = None
    ...

class ProductDetail(ProductSummary):
    ...
    active_ingredients: list[Ingredient]
    packages: list[Package]
```

| Syntax | Meaning |
| --- | --- |
| `product_id: str` | Required text field |
| `brand_name: str \| None = None` | Optional: can be text or empty |
| `class ProductDetail(ProductSummary)` | Detail has every Summary field, plus more |
| `list[Ingredient]` | A list of Ingredient objects |

## Why optional fields matter

```python
# Every field except recall_number is optional: the FDA data has gaps (for example 176 recalls with no state),
# and a required field here would turn any such row into a 500 error.
class RecallSummary(BaseModel):
    recall_number: str
    recalling_firm: str | None = None
    state: str | None = None
    ...
```

If a field were required and a real record had it empty, the API would crash with a 500 error. Claude Code proved this by making `state` required: 7 tests failed.

## The models, grouped

| Group | Models |
| --- | --- |
| Products | `Ingredient`, `Package`, `ProductSummary`, `ProductDetail`, `ProductPage`, `LabelerCount` |
| Health | `Health` |
| Recalls | `RecallSummary`, `RecallDetail`, `RecallPage`, `ProductRecallPage` |
| Insights | Spike facts plus `summary`, `source` (`ai` or `template`) and `fallback_reason` |
| Analytics | `Coverage`, `MonthlyRecallCount`, `MonthlyRecalls`, `CategoryCount`, `OtherReason`, `ReasonCategories`, `ReasonTotal`, `FirmTotal`, `Spike`, `SpikeReport` |

## Page models

```python
class ProductPage(BaseModel):
    total: int   # how many products match the filters (not just this page)
    limit: int
    offset: int
    items: list[ProductSummary]
```

`total` lets a client know how many pages exist; `items` is just the current page.
