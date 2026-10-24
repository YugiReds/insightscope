# `reports.py`: CSV reports

**Job:** builds the two CSV downloads. It uses only Python's built-in `csv` module. There's no PDF code here on purpose: the printable report is made by the browser (see [frontend.md](frontend.md)).

**Endpoints (in `main.py`):** `GET /reports/recalls.csv` and `GET /reports/spikes.csv`

> The snippets below are simplified. Open `reports.py` in VS Code for the exact code.

## 1. CSV injection protection

```python
DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r")

def neutralize(value):
    if isinstance(value, str) and value.startswith(DANGEROUS_START):
        return "'" + value
    return value
```

Excel and Google Sheets run a cell that starts with these characters as a **formula**. The apostrophe makes them show it as plain text instead. Numbers and dates are left alone, because they can't start a formula.

**Trade-off:** a real value like `+Protec Hands Gel` gets an apostrophe in the raw file. That's the accepted cost.

## 2. Building the file

```python
writer = csv.writer(buffer, lineterminator="\r\n")
...
return buffer.getvalue().encode("utf-8-sig")
```

| Detail | Why |
| --- | --- |
| `csv.writer` | Adds quotes around any cell with a comma, quote or line break, so text like `Quote "Co", Ltd` survives |
| `\r\n` line endings | What spreadsheets expect |
| `utf-8-sig` | UTF-8 **with** a byte order mark, so Excel shows accented names correctly |

## 3. The download header

```python
{"Content-Disposition": f'attachment; filename="{filename}"'}
```

`attachment` tells the browser to **save** the response as a file instead of showing it. The file name is built only from dates and short letters-and-dashes slugs, so it can never contain quotes or line breaks.

## 4. Recalls report

```sql
WHERE (:start IS NULL OR report_date >= :start)
  AND (:end IS NULL OR report_date <= :end)
  AND (:classification IS NULL OR lower(classification) = lower(:classification))
ORDER BY report_date DESC NULLS LAST, recall_number DESC
```

- Each filter is optional: when it isn't given (`NULL`), that line is always true.
- Same order as `/recalls`: newest first, with the unique `recall_number` as tiebreaker, so the file is always identical for the same request.
- `reason_category` reuses the keyword rules from `analytics.py`, so the CSV and the chart always agree.

Columns: `recall_number, report_date, classification, status, recalling_firm, product_description, reason_for_recall, reason_category`.

## 5. Spikes report

Calls `insights.spike_insights()`, the same function as `/insights/recalls/spikes`. Cached summaries are reused, so they make **no AI call**. A spike with no saved summary triggers one call, and the result is saved.

Columns: `month, recalls, baseline_average, z_score, top_firm, top_firm_share_pct, top_reasons, summary, source, fallback_reason`.

## Why it matters

Exports are what users ask for first. This shows they were built safely (injection, encoding), consistently (same sort and categories as the API) and cheaply (cache reuse).
