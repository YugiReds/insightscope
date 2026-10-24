# Step 1: Data pipeline

**Result:** 5,000 real FDA drug products loaded into three linked PostgreSQL tables, plus automated data checks and the first push to GitHub.

**Date:** October 23, 2026 (early morning)

## The goal

Pull real drug data from the FDA, clean it, and store it in a database you can query with SQL.

**Data source:** the [openFDA NDC drug directory](https://open.fda.gov/apis/drug/ndc/), the FDA's free list of drug products. It was chosen because it ties directly to your pharmacy background (PrimeRx), and because its nested fields need real cleaning.

## What was built

| File | Job |
| --- | --- |
| `db.py` | Connects to PostgreSQL and defines the tables |
| `ingest.py` | Downloads, cleans and loads the data |
| `checks.sql` | SQL checks that look for bad data |
| `run_checks.py` | Runs the checks and prints PASS, WARN or FAIL |
| `CLAUDE.md` | The rulebook Claude Code reads at the start of each session |

## The tables

| Table | Rows | One row per |
| --- | --- | --- |
| products | 5,000 | Drug product |
| active_ingredients | 7,874 | Ingredient in a product (about 1.6 per product) |
| packages | 9,696 | Package size of a product (about 2 per product) |

The FDA sends ingredients and packages as nested lists inside each product. The script splits them into their own tables, linked back by `product_id`. This is a **one-to-many design**: one product has many ingredients and many packages.

**Foreign keys** make PostgreSQL itself reject any ingredient or package that doesn't belong to a real product.

## How the load works

1. **Fetch:** download 1,000 records at a time from openFDA until 5,000 are collected.
2. **Clean:** trim spaces, turn blank text into real empty values (NULL), and convert dates like `20221018` into real dates. Bad dates become empty instead of crashing.
3. **Flatten:** turn the nested ingredient and package lists into rows.
4. **Load:** drop and recreate the tables, then insert the rows (products first, so the links work).

The script downloads everything before touching the database, so an FDA outage can't wipe your data.

Run it with:

```powershell
.\venv\Scripts\python.exe ingest.py
```

## Data checks

| Check | Result | What it proves |
| --- | --- | --- |
| Orphan ingredients | PASS | Every ingredient belongs to a real product |
| Orphan packages | PASS | Every package belongs to a real product |
| Duplicate product_id | PASS | No product is stored twice |
| Repeated NDC codes | WARN (33) | Some drug codes appear on more than one row |

Run them with:

```powershell
.\venv\Scripts\python.exe run_checks.py
```

## The duplicate-NDC finding (bug story #1)

The fourth check flagged **33 drug codes (NDCs) on 75 rows**.

- **Investigation:** Claude Code traced all 33 to the FDA's own data. The FDA keeps several versions of a drug's label, and each version gets its own `product_id` (the NDC plus a label version id).
- **Decision:** keep them (they're real), mark the check as WARN instead of FAIL, and document the rule in `CLAUDE.md`.
- **The rule:** when looking up or counting by NDC, use only the newest label version (latest `marketing_start_date`, with `product_id` as a tiebreaker).
- **Why it matters:** without the rule, the API would count some drugs twice.

## Git commits in this step

| Commit | Message |
| --- | --- |
| `1a7f235` | Project setup: venv, dependencies, gitignore |
| `1b85846` | Fix requirements.txt encoding |
| `2735824` | Add data validation checks; document duplicate NDC label versions |

Then the repo was created at [github.com/YugiReds/insightscope](https://github.com/YugiReds/insightscope) and pushed with `git push -u origin main`. The `.env` file was confirmed absent from GitHub.

## Weaknesses noted for later

1. No retries if the FDA API hiccups.
2. Each table loads in its own transaction, so a failure could leave half-loaded data.
3. `print` instead of proper logging.

Fix #2 was done for recalls in [step 4](04-recalls.md). The products load still has all three.
