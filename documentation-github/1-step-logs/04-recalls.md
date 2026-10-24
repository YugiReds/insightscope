# Step 4: FDA recalls

**Result:** 9,999 real FDA drug recalls (February 2018 to October 2026) in two new tables, three recall endpoints, and a fix for a real routing bug. Tests grew to 45.

**Date:** October 23, 2026 (afternoon)

## Why recalls

The drug directory barely changes, so it has no trends to explain. Recalls have dates, severity classes (Class I is the most serious), reasons like contamination or mislabeling, and the companies involved. Questions like "why did recalls spike in March?" are what InsightScope was meant to answer.

**Source:** the openFDA drug enforcement API, `https://api.fda.gov/drug/enforcement.json`.

## The new tables

| Table | Rows | One row per |
| --- | --- | --- |
| recalls | 9,999 | Recall (`recall_number` is the primary key) |
| recall_ndcs | 6,996 | Drug code listed on a recall (up to 16 per recall; most list none) |

## The new loader: `ingest_recalls.py`

Same fetch → clean → load pattern as `ingest.py`, with upgrades:

- **Newest first:** it asks openFDA to sort by `report_date` descending.
- **Retries:** a busy or failing FDA server (status 429 or 500+) is retried up to 3 times, with a growing pause.
- **Fetch first:** it downloads everything before touching the database, and stops if it got zero records.
- **All-or-nothing load:** both tables are replaced inside one transaction. If anything fails, the old tables stay exactly as they were.
- **Loud about dropped data:** records with a blank recall number, or two records sharing one, are logged as warnings instead of dropped silently. One real Aurobindo record had a blank number and is dropped.

Run it with:

```powershell
.\venv\Scripts\python.exe ingest_recalls.py
```

## Four new checks

| Check | Result |
| --- | --- |
| Duplicate recall numbers | PASS |
| Recalls missing a date | PASS |
| Orphan recall NDCs | PASS |
| Recall NDCs matching a product | WARN: 126 of 3,374 |

The match is low because `products` holds only a 5,000-record sample.

## Design decisions

- **No single `product_ndc` column on recalls.** One recall can list many codes; one column would throw the rest away.
- **Recalls have their own table list (`recalls_metadata`).** `ingest.py` drops and recreates every table in its list. Sharing it would let a drug reload silently wipe the recalls.

## The recall endpoints

| Endpoint | What it does | Errors it handles |
| --- | --- | --- |
| `GET /recalls` | Lists recalls, newest first, filtered by classification, status, company | 422 for a bad limit |
| `GET /recalls/{recall_number}` | One recall with its drug codes | 404 if it doesn't exist |
| `GET /products/{ndc}/recalls` | "Has this drug been recalled?" for any recalled code | 422 for a malformed NDC |

Choices worth knowing:

- **A unique tiebreaker in every sort.** 9,989 of 9,999 recalls share a report date with another recall. Sorting by date alone would make pages repeat or skip. Every sort ends with `recall_number`.
- **Blank fields allowed.** Every field except the recall number can be empty (176 recalls have no state).
- **A malformed NDC gets 422, not "no recalls."** Otherwise a typo would look like good news.

## Testing the tests

Claude Code broke the code on purpose to prove the tests catch problems: removing the tiebreaker made 4 tests fail, and making `state` required made 7 fail. Both were restored.

## The N/A recall bug (bug story #2)

1. **What broke:** `/recalls/N/A` returned "Not Found," though the recall (Centric Compounding) was in the database.
2. **How it was found:** an unknown recall normally gets the API's own message. This got FastAPI's generic "Not Found," so the request never reached your code.
3. **The cause:** the recall number is literally `N/A`, and the slash split the URL in two.
4. **The fix:** the route became `/recalls/{recall_number:path}`, which accepts slashes. Two tests guard it.
5. **The lesson:** real data is messy; never assume an ID looks normal.

This story is written up in the project README.

## Results

- **Tests:** 45 passing (14 API + 26 recall endpoint + 3 loader + 2 N/A)
- **Postman:** 19 requests, 40 of 40 checks passed

## Git commits in this step

| Commit | Message |
| --- | --- |
| `fd01525` | Add FDA recalls dataset: ingestion, tables, and checks |
| `2ae8643` | Add recall endpoints with tests, Postman requests, and README docs |
| `212fa94` | Remove empty Postman placeholder collection |
