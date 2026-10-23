# InsightScope

A small data service over the FDA's public drug directory (the openFDA NDC API). A script pulls ~5,000 drug
records, cleans them with pandas, and loads them into PostgreSQL. A second script does the same for the ~10,000
most recent FDA drug recalls (the openFDA enforcement API). A FastAPI service then lets clients look the data
up over HTTP.

**Stack:** Python, pandas, SQLAlchemy, PostgreSQL, FastAPI, pytest.

## How it fits together

```
openFDA API  ->  ingest.py (fetch, clean, flatten)  ->  PostgreSQL  <-  main.py (FastAPI)  <-  clients
```

| File | Role |
|---|---|
| `ingest.py` | Downloads records, cleans them (trims text, parses dates, flattens nested lists) and loads 3 tables. Safe to re-run: it recreates the tables. |
| `ingest_recalls.py` | Same pattern for recalls. Downloads everything first, then replaces the recall tables in a single transaction, so a failure cannot leave half-loaded data. Logs a warning if it has to drop a record. |
| `db.py` | Connection (reads `DATABASE_URL` from `.env`) and table definitions. |
| `main.py` / `schemas.py` | The API endpoints and their response shapes. |
| `checks.sql` / `run_checks.py` | Data integrity checks: orphan rows, duplicate IDs, missing dates. Prints PASS, WARN or FAIL. |
| `tests/` | Automated tests for the API and for the recall cleaning step. |

**Tables:** `products` (one row per product), `active_ingredients` and `packages` (many per product, flattened
from nested lists in the source data and linked by `product_id`). `recalls` (one row per recall) and
`recall_ndcs` (the NDCs a recall covers, many per recall, and most recalls list none) are kept separate from the
product tables, so reloading one dataset never wipes the other.

## Setup

1. Create a PostgreSQL database and put its connection string in `.env` as `DATABASE_URL=...` (never commit this file).
2. Install dependencies: `python -m venv venv`, then `.\venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. Load the data: `.\venv\Scripts\python.exe ingest.py` (optionally pass a record count, e.g. `ingest.py 3000`).
4. Load the recalls: `.\venv\Scripts\python.exe ingest_recalls.py` (optionally pass a record count).
5. Check it: `.\venv\Scripts\python.exe run_checks.py`.
6. Start the API: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`, then open http://127.0.0.1:8000/docs.
7. Run the tests: `.\venv\Scripts\python.exe -m pytest`.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Confirms the API can reach the database. |
| `GET /products` | List products. Filters: `labeler`, `dosage_form`. Paging: `limit` (1-100), `offset`. |
| `GET /products/{ndc}` | One product with its ingredients and packages. 404 if the NDC is unknown. |
| `GET /stats/labelers` | Labelers ranked by number of distinct NDCs. |
| `GET /search?q=` | Search brand and generic names (min 2 characters). |
| `GET /recalls` | List recalls, newest first. Filters: `classification` (e.g. `Class I`), `status` (e.g. `Ongoing`), `recalling_firm` (contains). Paging: `limit` (1-100), `offset`. |
| `GET /recalls/{recall_number}` | One recall with the NDCs it covers (an empty list if it names none). 404 if the recall number is unknown. Recall numbers may contain slashes (`N/A`). |
| `GET /products/{ndc}/recalls` | Recalls that list this NDC, newest first, with paging. Works for any NDC that appears in a recall, even one that is not in `products`. A valid NDC with no recalls returns `total: 0`. A malformed NDC returns 422. |

Example: `GET /products/76961-101` returns the product (Rolvedon, labeler Spectrum Pharmaceuticals) with
`active_ingredients: [{"name": "EFLAPEGRASTIM", "strength": "13.2 mg/.6mL"}]` and a `packages` list.

Example: `GET /products/16729-455/recalls` returns `total: 26` and the first page of those recalls. The newest come
first, and ties on the report date are broken by `recall_number`, so paging through all of them returns every
recall exactly once.

## Postman collection

`postman/insightscope.postman_collection.json` has one request for each endpoint, grouped into **Happy path**
(requests that should succeed) and **Error cases** (requests that should be rejected, like an unknown NDC or an
oversized `limit`). Each request has a test script that checks the status code and one or two fields.

To run it:
1. Start the API (`.\venv\Scripts\python.exe -m uvicorn main:app --reload`).
2. In Postman, choose **Import** and select the JSON file.
3. Open the collection's **Variables** tab and check that `baseUrl` is `http://127.0.0.1:8000`. Change it to test
   a deployed copy of the API.
4. Run one request with **Send** and read the **Test Results** tab, or run them all with
   **Run collection** (the Runner). Every test should show PASS.

**How the test scripts work:** they are short JavaScript snippets that Postman runs after the response arrives.
- `pm.test('name', function () { ... })` defines one named check. It shows PASS or FAIL in the results.
- `pm.response.to.have.status(200)` checks the HTTP status code.
- `pm.response.json()` turns the response body into an object, so the script can look at fields like `status` or
  `items`.
- `pm.expect(value).to...` states what the value should be, for example `.to.eql('ok')` (equals),
  `.to.be.an('array')` (is a list) or `.to.have.lengthOf(5)` (has exactly 5 entries).
- The "sorted" check loops through the rows and confirms each count is no larger than the one before it.

The tests that check the data (NDC `76961-101`, the `TABLET` filter, the recalls `D-0006-2027` and `N/A`, and NDC
`16729-455`) assume the data from `ingest.py` and `ingest_recalls.py` is loaded.

## A data quirk worth knowing

An NDC is **not unique** in this data. openFDA keeps several label versions per NDC, and each product's
`product_id` is `<ndc>_<spl_id>`. In the loaded sample, 33 NDCs (75 rows) have multiple versions, some up to 4.
Counting rows would overcount drugs, so every NDC lookup and count uses only the version with the latest
`marketing_start_date` (ties broken by `product_id`). The integrity checks report this as a WARN, not a failure,
because it is expected behavior in the source data.

## Running in production (not deployed yet)

The setup above is for development: the API runs in a terminal on a laptop and stops when the terminal closes.
This project is not deployed. In production the same code would run like this:

- **A server that is always on**, with the API started as a managed service (a Docker container, `systemd` or a
  Windows service) that starts at boot and restarts automatically if it crashes.
- **uvicorn without `--reload`**, usually with several workers, behind a reverse proxy (such as nginx) that
  provides HTTPS and a real domain name.
- **Secrets as environment variables** set on the server (like `DATABASE_URL`), never stored in the code.
- **A managed PostgreSQL database** on its own server, not on the same machine as the API.
- **Health checks and logs:** a monitoring system calls `/health` every few seconds and alerts or restarts the
  service if it stops answering. The request log (status code and milliseconds) is where to start debugging.

## Troubleshooting scenarios

Realistic questions a user of this API might raise, and how to work through them.

**"I get a 404 on `/products/{ndc}`."**
The NDC is not in the database. Check for a typo or a missing hyphen (the format is `labeler-product`, like
`76961-101`). Remember the database holds a sample of ~5,000 of the ~138,000 records openFDA has, so a valid
NDC can still be missing. Compare against the source: `https://api.fda.gov/drug/ndc.json?search=product_ndc:"76961-101"`.

**"I get a 422 on `/products` or `/search`."**
The request itself is invalid, and the response body says which field. Common causes: `limit` above 100 or
below 1, a negative `offset`, or a search `q` shorter than 2 characters.

**"Every request returns 503 'Database unavailable'."**
The API is running but cannot reach PostgreSQL. Call `/health` to confirm. Then check that the PostgreSQL service
is running, and that the host, port, user and password in `DATABASE_URL` are correct. The real error is in the
API's log, not in the response (the response deliberately hides internals).

**"The drug counts look too high."**
Compare the API's `total` with `SELECT COUNT(*) FROM products`. The raw table has more rows (5,000) than the API
reports (4,958) because the API counts each NDC once, using its latest label version. See the data quirk above.

**"The API feels slow."**
Every request is logged with its status code and duration in milliseconds. Find the slow endpoint in the log
first. Broad `ILIKE` searches (`/search`, the `labeler` filter) scan the whole table, which is fine at this size
but is the first thing to index if the data grows.

**"Is the data itself trustworthy?"**
Run `run_checks.py`. It verifies there are no orphaned ingredient, package or recall-NDC rows, no duplicate product
IDs or recall numbers, and no recalls missing a date.

**"`/products/{ndc}/recalls` says `total: 0`. Does that mean the drug was never recalled?"**
No. It means no recall is on file in *our loaded data*. Three things limit that answer: only the newest ~10,000 of
the ~18,000 recalls the FDA lists were loaded, so older recalls are missing. Only about one recall in four names
any NDC at all, so a drug can be recalled without the NDC being attached. And a typo does not give `0`: a
malformed NDC returns 422 on purpose, so a mistyped code can never look like good news. For a real safety
decision, check the FDA directly:
`https://api.fda.gov/drug/enforcement.json?search=openfda.product_ndc:"16729-455"`. Its `total` can be higher than
ours, because it also counts the older recalls we did not load.

**"Paging through `/recalls` gives me repeated recalls and some that are missing."**
Compare the `total` with the number of *unique* `recall_number` values you collected, and check that your offset
step equals your `limit`. The API sorts newest first and breaks ties on `recall_number` (thousands of recalls
share a report date), so a stable table pages cleanly. The usual cause is the data changing mid-download:
`ingest_recalls.py` replaces the table, and new recalls push the older ones down, which shifts every later page.
Repeat the whole download while no reload is running. If duplicates persist with a stable table, suspect the sort
(compare it with the order the tests expect) and send the `limit`, `offset` and a repeated recall number.

## Bug story: the recall that could not be opened

**What broke.** The recall list worked, but one recall could not be opened. The FDA has a real recall whose number
is literally `N/A` (a number not yet assigned). It appeared at the top of `GET /recalls`, yet
`GET /recalls/N/A` returned `404 {"detail": "Not Found"}`. Encoding the slash (`N%2FA`) did not help.

**How it was found.** While checking the data before writing the recall tests, the first recall in the newest-first
list had the number `N/A`. It was first confirmed to be genuine FDA data (Centric Compounding LLC, "Not Yet
Classified"), not a loading mistake. Then the clue that pointed at the cause was the *wording* of the 404. An
unknown recall such as `X-9999-9999` returns the API's own message, "No recall found with recall number
X-9999-9999". The `N/A` request returned the framework's generic "Not Found". That difference meant the request
never reached the recall code at all. The URL had been rejected earlier, by the router.

**The cause.** In `/recalls/{recall_number}`, a route parameter matches a single piece of the URL, and a slash ends
it. `/recalls/N/A` has two pieces after `/recalls`, so no route matched.

**The fix.** Declare the route as `/recalls/{recall_number:path}`, which captures everything after `/recalls/`,
slashes included. Two tests now guard it. One fetches the real `N/A` recall. The other asks for an unknown number
containing slashes (`A/B/C`) and requires the API's own 404 message, which stays valid even if the FDA data changes.
Reverting the fix makes both tests fail, which confirms they really detect the problem.

**The lesson.** When an error message is generic, compare it with the error your own code produces. A different
wording can show that the request failed before it reached your code, and that tells you where to look.
