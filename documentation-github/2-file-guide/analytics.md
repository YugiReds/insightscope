# `analytics.py`: trends, reasons and spikes

**Job:** the math behind the three analytics endpoints. Each function takes a database connection and returns plain data; `main.py` just calls them. Queries are written as plain SQL with `text()` so they read top to bottom.

## 1. Reason categories (keyword rules)

```python
REASON_RULES = [
    ("Sterility / contamination",
     "steril|microbial|contaminat|bacteri|mold|fung|endotoxin|particulate|foreign|insanitary|burkholderia"),
    ("Impurities", "impurit|degradation|nitrosamine|ndma|nmba|ndea|carcinogen|benzene"),
    ("Potency", "potency|subpotent|superpotent|sub-potent|super-potent|assay"),
    ("Labeling", "labeling|mislabel|incorrect.{0,20}lot"),
    ("CGMP violations", "gmp|good manufacturing|processing control"),
    ("Packaging", "packag|container|closure|child.resistant|blister|leak"),
    ("Failed specifications", "dissolution|stability|specification|content uniformity"),
    ("Unapproved drug", "without an approved|without approved|unapproved|nda/anda|tainted"),
]
```

- Rules are checked **in order** and the **first match wins**. Specific problems come before the broad CGMP bucket.
- `|` means "or". `steril` matches "sterile" and "sterility".
- Anything that matches nothing is "Other". The reasons endpoint reports the Other share (2.5%) and the top unmatched reasons, so you can judge the rules.
- The word `potent` is deliberately not used, because it matches "potential".

These rules are turned into one SQL `CASE` expression by `_category_case_sql()`, so they're written in only one place.

## 2. Spike detection settings

```python
BASELINE_MONTHS = 12   # a month is compared with the 12 months before it
SPIKE_THRESHOLD = 2.0  # flagged when its z-score is above this
TOP_N = 3              # reason categories and firms listed for each spike
```

Change a number here and the whole method follows.

## 3. The spike query

```sql
WINDOW w AS (ORDER BY month ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING)
...
(recalls - baseline_mean) / NULLIF(baseline_sd, 0) AS z_score
```

- The **window** is "the 12 months before this one". `1 PRECEDING` means the month itself is never in its own baseline.
- `NULLIF(baseline_sd, 0)` turns a flat history into "can't score" instead of a divide-by-zero error.
- A `generate_series` of every month plus a `LEFT JOIN` makes quiet months count as 0 instead of disappearing.

In plain words: **z = (this month − average of the last 12) ÷ their usual wiggle**. Above 2 is a spike.

## 4. Partial-month detection

```python
oldest_is_partial = oldest.day > 7
```

Every FDA report date is a Wednesday, so a fully covered month must have a report in its first 7 days. If the oldest recall is dated after the 7th, that month is cut off and excluded. In the current data, February 2018 is excluded.

## The three public functions

| Function | Endpoint | Returns |
| --- | --- | --- |
| `monthly_recalls(conn)` | `/analytics/recalls/monthly` | Months with totals by class, plus coverage info |
| `reason_categories(conn, start, end)` | `/analytics/recalls/reasons` | Category counts and shares, Other share, top unmatched reasons |
| `recall_spikes(conn)` | `/analytics/recalls/spikes` | Method description, threshold, each spike with top 3 reasons and firms |

## Interview line

"Spike detection compares each month to its previous 12 using a z-score above 2. The SQL uses a window function that excludes the month itself and counts quiet months as zero. Six spikes came out, and each was mostly one company's mass recall."
