# InsightScope

A small data service over the FDA's public drug directory (the openFDA NDC API). A script pulls ~5,000 drug
records, cleans them with pandas, and loads them into PostgreSQL. A FastAPI service then lets clients look
the data up over HTTP.

**Stack:** Python, pandas, SQLAlchemy, PostgreSQL, FastAPI, pytest.

## How it fits together

```
openFDA API  ->  ingest.py (fetch, clean, flatten)  ->  PostgreSQL  <-  main.py (FastAPI)  <-  clients
```

| File | Role |
|---|---|
| `ingest.py` | Downloads records, cleans them (trims text, parses dates, flattens nested lists) and loads 3 tables. Safe to re-run: it recreates the tables. |
| `db.py` | Connection (reads `DATABASE_URL` from `.env`) and table definitions. |
| `main.py` / `schemas.py` | The API endpoints and their response shapes. |
| `checks.sql` / `run_checks.py` | Data integrity checks: orphan rows, duplicate IDs. Prints PASS, WARN or FAIL. |
| `tests/test_api.py` | Automated API tests. |

**Tables:** `products` (one row per product), `active_ingredients` and `packages` (many per product, flattened
from nested lists in the source data and linked by `product_id`).

## Setup

1. Create a PostgreSQL database and put its connection string in `.env` as `DATABASE_URL=...` (never commit this file).
2. Install dependencies: `python -m venv venv`, then `.\venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. Load the data: `.\venv\Scripts\python.exe ingest.py` (optionally pass a record count, e.g. `ingest.py 3000`).
4. Check it: `.\venv\Scripts\python.exe run_checks.py`.
5. Start the API: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`, then open http://127.0.0.1:8000/docs.
6. Run the tests: `.\venv\Scripts\python.exe -m pytest`.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Confirms the API can reach the database. |
| `GET /products` | List products. Filters: `labeler`, `dosage_form`. Paging: `limit` (1-100), `offset`. |
| `GET /products/{ndc}` | One product with its ingredients and packages. 404 if the NDC is unknown. |
| `GET /stats/labelers` | Labelers ranked by number of distinct NDCs. |
| `GET /search?q=` | Search brand and generic names (min 2 characters). |

Example: `GET /products/76961-101` returns the product (Rolvedon, labeler Spectrum Pharmaceuticals) with
`active_ingredients: [{"name": "EFLAPEGRASTIM", "strength": "13.2 mg/.6mL"}]` and a `packages` list.

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

The tests that check the data (NDC `76961-101`, the `TABLET` filter) assume the sample data from `ingest.py` is
loaded.

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
Run `run_checks.py`. It verifies there are no orphaned ingredient or package rows and no duplicate product IDs.
