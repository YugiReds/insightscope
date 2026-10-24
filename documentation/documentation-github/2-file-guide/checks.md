# `checks.sql` and `run_checks.py`: data quality checks

**Job:** confirm the data in the database is trustworthy. `checks.sql` holds the SQL; `run_checks.py` runs it and prints PASS, WARN or FAIL.

**Run it:** `.\venv\Scripts\python.exe run_checks.py`

## How each check is written

Every check returns three things: a name, a severity and a count of bad rows. **0 bad rows means PASS.**

```sql
-- 1. Orphan ingredients: ingredient rows whose product_id has no matching product.
SELECT 'orphan active_ingredients' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM active_ingredients a
LEFT JOIN products p ON p.product_id = a.product_id
WHERE p.product_id IS NULL;
```

`LEFT JOIN ... WHERE p.product_id IS NULL` is the classic SQL pattern for "find rows with no match." Worth knowing for any SQL interview.

```sql
-- 3. Duplicate products by product_id
SELECT 'duplicate product_id' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM (
    SELECT product_id FROM products GROUP BY product_id HAVING COUNT(*) > 1
) d;
```

`GROUP BY ... HAVING COUNT(*) > 1` finds anything that appears more than once.

## All eight checks

| # | Check | Severity | Current result |
| --- | --- | --- | --- |
| 1 | Orphan ingredients | FAIL | PASS |
| 2 | Orphan packages | FAIL | PASS |
| 3 | Duplicate product_id | FAIL | PASS |
| 4 | Repeated product_ndc (label versions) | WARN | 33 (expected) |
| 5 | Duplicate recall numbers | FAIL | PASS |
| 6 | Recalls missing a date | FAIL | PASS |
| 7 | Orphan recall_ndcs | FAIL | PASS |
| 8 | Recall NDCs matching a product | WARN | 126 of 3,374 (expected) |

**FAIL** means a real data problem. **WARN** means "worth knowing, but expected."

## The runner

```python
statements = [s.strip() for s in open("checks.sql").read().split(";") if "SELECT" in s]
...
status = "PASS" if bad_rows == 0 else severity
failed = failed or status == "FAIL"
print(f"{status} {name}: {bad_rows} rows")
...
sys.exit(1 if failed else 0)
```

- It splits `checks.sql` on semicolons and runs each `SELECT`.
- It exits with code 1 only on a real FAIL, so warnings don't count as errors. That makes it usable in automated pipelines later.

## Quirk to know

Check 8 counts **matches**, so zero matches would print PASS even though that would be the surprising result. Fine today (126), but worth knowing.

## Why the first checks always pass

The database already enforces them: `product_id` is a primary key and the child tables have foreign keys. The checks confirm it independently, and would still catch problems if the schema were ever loosened.
