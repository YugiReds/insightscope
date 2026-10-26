# InsightScope

[![Tests](https://github.com/YugiReds/insightscope/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/YugiReds/insightscope/actions/workflows/tests.yml)

A small data service over the FDA's public drug directory (the openFDA NDC API). A script pulls ~5,000 drug
records, cleans them with pandas, and loads them into PostgreSQL. A second script does the same for the ~10,000
most recent FDA drug recalls (the openFDA enforcement API). A FastAPI service then lets clients look the data
up over HTTP, and a React dashboard shows it all on one page.

**Live demo:** https://insightscope.onrender.com (Render free web service + Neon free Postgres). The first visit after about 15 minutes idle takes up to a minute while the free server wakes up.

**Stack:** Python, pandas, SQLAlchemy, PostgreSQL, FastAPI, pytest. Dashboard: React, Vite, Tailwind CSS, Recharts, Vitest.

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
| `frontend/` | The React dashboard (Vite, Tailwind, Recharts). `npm run build` writes `frontend/dist`, which `main.py` serves at `/`. Has its own tests (Vitest). |

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
| `GET /health` | Confirms the API process is up. Never touches the database, so it is fast and cannot wake a sleeping one. |
| `GET /health/db` | Runs `SELECT 1`. Returns `503` if the database cannot be reached. |
| `GET /products` | List products. Filters: `labeler`, `dosage_form`. Paging: `limit` (1-100), `offset`. |
| `GET /products/{ndc}` | One product with its ingredients and packages. 404 if the NDC is unknown. |
| `GET /stats/labelers` | Labelers ranked by number of distinct NDCs. |
| `GET /search?q=` | Search brand and generic names (min 2 characters). |
| `GET /recalls` | List recalls, newest first. Filters: `classification` (e.g. `Class I`), `status` (e.g. `Ongoing`), `recalling_firm` (contains). Paging: `limit` (1-100), `offset`. |
| `GET /recalls/{recall_number}` | One recall with the NDCs it covers (an empty list if it names none). 404 if the recall number is unknown. Recall numbers may contain slashes (`N/A`). |
| `GET /products/{ndc}/recalls` | Recalls that list this NDC, newest first, with paging. Works for any NDC that appears in a recall, even one that is not in `products`. A valid NDC with no recalls returns `total: 0`. A malformed NDC returns 422. |
| `GET /analytics/recalls/monthly` | Recalls per month (by report date), split by classification. A partly covered oldest month is left out, and the response says which. |
| `GET /analytics/recalls/reasons` | Recalls per reason category (keyword rules). Optional `start` and `end` dates. Reports the share that landed in "Other" and the most common reasons no rule matched. |
| `GET /analytics/recalls/spikes` | Months with unusually many recalls (z-score above 2 against the previous 12 months), each with its top 3 reason categories and top 3 recalling firms. |
| `GET /insights/recalls/spikes` | Each spike's facts plus a plain-English summary. The summary comes from an AI that may only use those facts, or from a template when the AI is unavailable or says anything not in the facts. Every result says which (`source`) and why not the AI (`fallback_reason`). |
| `GET /reports/recalls.csv` | Download the recalls as a CSV file, one row per recall, newest first. Optional `start`, `end` (dates) and `classification`. A backwards or invalid date range returns 422. |
| `GET /reports/spikes.csv` | Download the spike months as a CSV file, with their summaries and whether each came from the AI or the template. Saved summaries are reused, so already-cached spikes cause no AI calls. |

Example: `GET /products/76961-101` returns the product (Rolvedon, labeler Spectrum Pharmaceuticals) with
`active_ingredients: [{"name": "EFLAPEGRASTIM", "strength": "13.2 mg/.6mL"}]` and a `packages` list.

Example: `GET /products/16729-455/recalls` returns `total: 26` and the first page of those recalls. The newest come
first, and ties on the report date are broken by `recall_number`, so paging through all of them returns every
recall exactly once.

## How the recall analytics work

The logic is in `analytics.py`, and the numbers come from plain SQL you can read top to bottom.

**Which months are used.** Only the newest ~10,000 recalls are loaded, so the oldest month may be cut off partway.
The FDA publishes weekly reports (every report date in the data is a Wednesday), and any 7 consecutive days contain
exactly one report. So a complete month must have a report dated in its first 7 days. If the oldest recall is dated
after the 7th, that month is partial and is left out (in the loaded data, February 2018). The newest month is
flagged when it may still be in progress but is kept, since an unfinished month is low and cannot cause a false spike.

**Spike detection.** For each month, take the recall counts of the 12 months before it, and work out their average
and how much they usually vary (the standard deviation). The z-score is how many "usual variations" this month sits
above that average: `z = (this month - average) / standard deviation`. A z above 2 is a rule of thumb: if monthly
counts were bell-curve shaped, only about 2% of months would reach it, so it is flagged as unusual. Months with no
recalls count as 0, a month needs 12 months of history to be scored, and a perfectly flat history cannot be scored.
In the loaded data every spike is driven largely by one firm: the top firm accounts for 41% to 87% of the month's
recalls, and for more than half of them in three of the six spikes (for example, King Bio Inc. accounts for 465 of
the 535 recalls in March 2019).
One limit: a huge spike inflates the variation for the next 12 months, which makes smaller spikes in that period
harder to flag.

**Reason categories.** Each free-text reason is sorted by keyword into one category: sterility/contamination,
impurities, potency, labeling, CGMP violations (good manufacturing practice), packaging, failed specifications,
unapproved drug, or other. The rules are checked in order and the first match wins: specific problems come first,
the broad CGMP bucket after them, and the catch-alls last. So "CGMP Deviations: carcinogen impurity detected" counts
as Impurities, and "potential" does not count as potency. The endpoint reports how much landed in "Other" (2.5% when
written) and lists the most common reasons nothing matched, so you can tell when the rules need updating.

## AI summaries: how they stay honest

`GET /insights/recalls/spikes` explains each spike in a few plain sentences. The logic is in `insights.py`.

1. **Our code does the maths.** Every number comes from the analytics (month, count, usual level, z-score, top
   reasons and firms). Our code also works out how much of the month one firm explains: 50% or more is "mainly one
   firm's mass recall", 25% to 49% is "one firm drove a large part", and less is "no single firm dominates".
2. **The AI only writes it up.** The prompt gives the model those facts and tells it not to add any facts, causes,
   names, dates or numbers. It runs on Hugging Face's hosted inference with a small instruction-tuned model.
3. **A guardrail checks the answer.** Every number in the AI's text must appear in the facts it was given, and
   vague quantities like "hundreds of recalls" are rejected. So is calling the recalls "products" or "items", because
   the facts count recalls (a firm's own name containing the word is fine). One invented number and the whole AI
   summary is dropped.
4. **A template is the fallback.** If the AI is unavailable (no `HF_TOKEN`, timeout, error, no credits) or fails the
   guardrail, a plain template written from the same facts is used. The result says `source: "template"` and gives
   the `fallback_reason`. After one failed call, the other spikes in the same request skip the AI, so an outage costs
   one timeout, not six.
5. **Good AI summaries are cached** in the Postgres table `insight_cache`. It survives restarts, is shared by every
   worker, and can be inspected in pgAdmin. The key is a hash of the facts, the model and the prompt version, so a
   changed number or model gets a fresh summary. Templates and failures are not cached, so the next request tries
   the AI again. Clear it with `DELETE FROM insight_cache;`.

**Setup.** Put a Hugging Face token in `.env` as `HF_TOKEN=...` (never commit it, and the code never prints it).
No extra package is needed: it uses `requests`. Choose another model with `HF_MODEL`. Run
`.\venv\Scripts\python.exe insights.py` to see each spike's summary, its source and any fallback reason.

**Status.** The default model, `meta-llama/Llama-3.1-8B-Instruct`, was checked against the real service: all six
real spikes passed the guardrail in three separate runs, taking about 3 seconds for the six. Two other small models
also passed (`google/gemma-3-4b-it`, slower, and `Qwen/Qwen3-4B-Instruct-2507`, the slowest at about 25 seconds and
offered by only one provider). The automated tests use a fake AI and never touch the network.

**Known limits.** The guardrail checks numbers and a few banned words, not claims. A model can still join two
separate facts into a statement the facts do not make. Prompt version 1 produced "198 of its products being recalled
due to CGMP violations" (the facts list the top firms and the top reasons separately and never link them). Version 2
still put the top reasons and the top firm in one sentence, wrote "the FDA reported" in 10 of 24 test summaries, and
sometimes worked out its own figures (for example a "304% increase", which the number check rejects, so that summary
falls back to the template). Version 3 forbids all of these, and a code check now rejects "products" and "items".
Across 24 real version-3 summaries, none of those problems appeared.
What the checks still cannot catch: a true but derived statement (one saved summary says CGMP violations were "the
majority of the recalls", which is correct, 198 of 236, but is not written in the facts), repetition and awkward
wording, summaries that run past the requested 2 or 3 sentences or leave out the usual monthly level (one saved
summary, March 2019, does both), and "significant spike", which can be mistaken for a statistical claim. Treat the AI summaries as drafts.

## Dashboard

A single page that shows everything the API knows, built with React (Vite), Tailwind CSS and Recharts.

![InsightScope dashboard: status light, summary tiles, recalls per month with spike markers, spike cards and recall reasons](screenshots/dashboard.png)

**What it shows:**
- A header with a live status light. It tells three situations apart: everything fine, the API is up but its database
  is not, and the API cannot be reached at all. `/health` is checked every 15 seconds; `/health/db` only about once a
  minute and never while the tab is hidden, so a forgotten tab cannot keep a sleeping database awake.
- Four summary tiles: total recalls, the share that are Class I, the number of spike months, and the date range covered.
- Recalls per month as stacked columns split by classification, with a diamond on every spike month.
- A card for each spike with its count against the usual level, the top firm and its share, the summary, and a badge
  saying **AI** or **Template**. Hover (or focus) a Template badge to see why the AI was not used.
- Reason categories with a date range picker (presets, or two date boxes).
- "Has this drug been recalled?": an NDC lookup with four clearly different outcomes: recalls found, none found, a
  malformed NDC (the API's 422, shown with the right format), and an API or database error.
- A "Download report" area: the two CSV files, and a Print / Save as PDF button. See "Reports" below.

**When something is down.** Every section has its own loading state and its own plain-language error with a Try
again button. If the API is down, a banner says so, and the sections reload by themselves when it comes back.
The page never goes blank.

**Accessibility.** Every input has a label. Every chart has a sentence that describes it and a table view with the same
numbers. Spike months are marked by a diamond shape, not by colour alone. Class colours are one blue ramp checked with
the dataviz palette validator, and every text colour pair reaches WCAG AA in light and dark mode (the page follows
your system setting).

### Run it while developing (two terminals)

```
# Terminal 1: the API
.\venv\Scripts\python.exe -m uvicorn main:app --reload

# Terminal 2: the dashboard (the first time, run npm install first)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite forwards the API paths (`/health`, `/products`, `/recalls`, `/analytics`,
`/insights`, `/search`, `/stats`, `/docs`) to the API on port 8000, so the browser only talks to one address and no
CORS settings are needed. If you add an API path with a new first segment, add it to `API_PATHS` in
`frontend/vite.config.js`.

### Run it as one server (production)

```
cd frontend
npm install
npm run build
cd ..
.\venv\Scripts\python.exe -m uvicorn main:app
```

Open **http://127.0.0.1:8000/**. FastAPI serves the built files at `/`, and `/docs` and every API endpoint still work.
Build **before** starting uvicorn, or restart uvicorn after the first build: the dashboard is only mounted if
`frontend/dist` exists when the server starts. Rebuilding while the server runs is fine.

### Tests

```
cd frontend
npm test                  # 64 dashboard tests (Vitest), with the API faked
cd ..
.\venv\Scripts\python.exe -m pytest    # includes tests/test_dashboard.py, which checks FastAPI serves the built page
```

The dashboard tests cover the error states, the AI and Template badge, the four NDC outcomes, the date range picker and
the chart's text and table alternatives. They never call a real server. The Python tests that need the real build are
skipped until `npm run build` has been run.

### Why `node_modules` and `dist` are not in git

Both are rebuilt from files that **are** committed, so storing them would only add size and noise. `node_modules/` is
about 140 MB and is recreated exactly by `npm install` from `package.json` and `package-lock.json` (commit those two,
and `.npmrc`, which turns off install scripts). `dist/` is the build output of `npm run build`: committing it would put
generated, minified code in every diff and let it go stale. The trade-off is that whoever deploys must run the build.

### Known limits

The built JavaScript is about 630 kB (185 kB compressed), mostly the charting library. It is not split into lazy-loaded
pieces. The spike summaries can take a few seconds to appear the first time, because an AI writes them; later visits
use the saved ones. There is no login: anyone who can reach the server can see the dashboard.

## Reports: CSV files and a printable page

The dashboard's **Download report** area has a button for each CSV file and a **Print / Save as PDF** button.

**The two CSV files**

| Address | One row per | Columns |
|---|---|---|
| `GET /reports/recalls.csv` | recall, newest first (ties broken by `recall_number`) | `recall_number`, `report_date`, `classification`, `status`, `recalling_firm`, `product_description`, `reason_for_recall`, `reason_category` |
| `GET /reports/spikes.csv` | spike month | `month`, `recalls`, `baseline_average`, `z_score`, `top_firm`, `top_firm_share_pct`, `top_reasons`, `summary`, `source` (ai or template), `fallback_reason` |

- The recalls file takes the optional `start` and `end` dates (both ends included) and `classification`. It follows the
  date range chosen under "Why drugs are recalled" on the dashboard. A backwards range or an invalid date is a 422, the
  same as the other endpoints. The file name says what is inside, for example
  `insightscope-recalls_2025-01-01_to_2025-12-31_class-i.csv`.
- The spikes file uses the saved summaries (see "AI summaries"), so a spike that already has one makes **no AI call**.
  Only a spike without a saved summary can cause one, and then that summary is saved too.
- **Opens correctly in Excel.** The files are UTF-8 with a byte order mark, which is how Excel knows to show names with
  accents (Müller, Lääke) properly. Commas, quotes and line breaks inside a cell are quoted in the standard way.
- **Protected against CSV injection.** A spreadsheet treats a cell that starts with `=`, `+`, `-`, `@`, a tab or a
  carriage return as a formula to run. Our cells hold text we do not control (firm names, product descriptions,
  AI-written summaries), so a cell like `=HYPERLINK(...)` could run when someone opens the file. Every such text cell gets
  an apostrophe in front, which spreadsheets show as plain text and hide. It really matters here: one product description
  in the data starts with `+` ("+Protec Hands Antibacterial Gel"). The cost is that the raw file shows an apostrophe on
  values that genuinely start with those characters.

**The printable report.** Print / Save as PDF opens the browser's print window (choose "Save as PDF" as the printer to
get a file). The printed page has a title, the date it was generated, the date range, the four headline numbers, the
monthly chart, every spike summary with its AI or Template badge (the reason a template was used is written out,
because a hover tip cannot be printed), the reason categories, and the data limits. The buttons, the NDC lookup, the date
pickers and the status light are hidden. It always prints in **light colours**, even if your screen is in dark mode. It is
laid out for Letter and A4 paper (the chart is a fixed 620 px wide, which fits inside the margins of both, but only
Letter has been checked on real output). In Chrome's print window, turning off "Headers and footers" gives a cleaner page.

**Why print-to-PDF and not a PDF library on the server.** It keeps deployment simple. The server stays one Python process
plus static files, with nothing new to install. Server-side PDF tools (WeasyPrint, wkhtmltopdf, ReportLab) need system
libraries, fonts or separate programs on every server, which must be installed, updated and kept working. Print-to-PDF
also means there is only one design: the page you see is the page that prints, and the browser already has the right
fonts and paper sizes. The trade-offs are that the result varies slightly between browsers, and that nothing can make a
PDF without a person at a browser, so scheduled or emailed PDF reports are not possible. If that is ever needed, the
next step would be headless Chrome or a PDF library, added deliberately.

## Postman collection

`postman/insightscope.postman_collection.json` has one request for each endpoint, grouped into **Happy path**
(requests that should succeed) and **Error cases** (requests that should be rejected, like an unknown NDC or an
oversized `limit`). Each request has a test script that checks the status code and one or two fields.

To run it:
1. Start the API (`.\venv\Scripts\python.exe -m uvicorn main:app --reload`).
2. In Postman, choose **Import** and select the JSON file.
3. Open the collection's **Variables** tab and check that `baseUrl` is `http://127.0.0.1:8000`. Change it to
   `https://insightscope.onrender.com` to test the live copy.
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

Requests take their IDs from earlier responses (the product and recall lookups use an NDC and a recall number saved
from the list requests), so the collection works against any data load, local or live.

The labeler filter uses the longest word (at least 3 characters) of a labeler saved from the product list, and the `N/A` recall request accepts
either the recall or our own "No recall found" 404 (it fails only on the generic `Not Found`). The remaining data
checks (the `TABLET` filter and the 2025 date ranges) still assume the data from `ingest.py` and `ingest_recalls.py`
is loaded.

## A data quirk worth knowing

An NDC is **not unique** in this data. openFDA keeps several label versions per NDC, and each product's
`product_id` is `<ndc>_<spl_id>`. In the loaded sample, 33 NDCs (75 rows) have multiple versions, some up to 4.
Counting rows would overcount drugs, so every NDC lookup and count uses only the version with the latest
`marketing_start_date` (ties broken by `product_id`). The integrity checks report this as a WARN, not a failure,
because it is expected behavior in the source data.

## Continuous integration

Every push and pull request to `main` runs the tests on GitHub (`.github/workflows/tests.yml`), in two jobs that run
side by side:

- **Dashboard tests:** `npm ci` and `npm test` (the Vitest tests in `frontend/`).
- **Python tests:** starts a throwaway Postgres 18, builds the dashboard (so the tests that serve the real build run
  instead of being skipped), loads made-up data, and runs `pytest`.

**Why a seeded database and not the live openFDA data?** The tests compare the API with the database, so the database
must be filled. Loading the real data on every push would be slow, openFDA could rate limit the shared GitHub servers,
and the data changes every week, so a test could turn red with no code change. `tests/seed_ci_data.py` instead builds a
small fixed data set of invented firms, drugs and recalls, shaped to contain the cases the tests look for (repeated
NDCs, a recall numbered `N/A`, two spikes, a firm name with a comma, and so on). It uses no random numbers and no
clock, so a red badge always means a real change broke something. The real data is still what you test by hand with
`pytest` locally and with the Postman collection.

**No secrets are used.** The workflow has read-only access to the repository. The database password in it is a
throwaway value for a database that exists only while the job runs, `DATABASE_URL` points at it, and there is no Neon
connection and no `HF_TOKEN`. The AI tests use a fake client and any real network call fails the test.

**The seed script refuses to run on any other database.** It deletes every row first, so it stops unless the database
name in `DATABASE_URL` is exactly `insightscope_ci`, and it never reads `.env`. To run the whole suite the same way
locally, create an empty database called `insightscope_ci`, then in PowerShell set `$env:DATABASE_URL` to its address,
run `.\venv\Scripts\python.exe tests\seed_ci_data.py` and `.\venv\Scripts\python.exe -m pytest`, and remove the variable.

## Running in production: Render + Neon

The setup above is for development: the API runs in a terminal on a laptop and stops when the terminal closes. The
live app, https://insightscope.onrender.com, runs like this:

- **One Render free web service**, described by `render.yaml`. It runs `uvicorn main:app` without `--reload`. Render
  provides HTTPS and the `onrender.com` address, and redeploys automatically on every push to GitHub.
- **Neon managed PostgreSQL** (free), on its own server, not on the same machine as the API.
- **Secrets as environment variables** in Render (`DATABASE_URL`, `HF_TOKEN`), never stored in the code.
- **The dashboard** is served by the same FastAPI process. The build command runs `npm run build` on every deploy,
  because the build output is not stored in git.
- **Health checks:** Render calls `/health` regularly. It never touches the database, so the check does not keep Neon
  awake. `/health/db` runs `SELECT 1` and returns 503 when the database cannot be reached: use it to tell "API down"
  from "database down". The request log (status code and milliseconds) is where to start debugging.

### How it was deployed

1. **Database:** in Neon, click **Connect**, switch **Connection pooling OFF**, and copy the direct connection string
   (not the pooled one, whose host contains `-pooler`). It looks like `postgresql://user:password@host/db?sslmode=require`.
   The app accepts `postgres://`, `postgresql://` and `postgresql+psycopg://` and fixes the prefix itself
   (`normalize_database_url` in `db.py`).
2. **Hugging Face token:** create a separate fine-grained token with only the permission "Make calls to Inference
   Providers", used for nothing else.
3. **Render:** choose **New > Blueprint** and pick this repository. Render reads `render.yaml`. When asked, enter
   `DATABASE_URL` (the Neon direct string) and `HF_TOKEN` as secrets. They are `sync: false`, so they are never stored in git.
4. **Tables:** the first start creates every table on the empty database by itself (in the background, so `/health`
   answers at once).
5. **Data:** load it from your own PowerShell. A `DATABASE_URL` set in the shell wins over `.env`, and `Read-Host`
   keeps the password out of the command history and the screen recording:

```powershell
$env:DATABASE_URL = Read-Host "Neon direct connection string"   # paste it when asked
.\venv\Scripts\python.exe ingest.py
.\venv\Scripts\python.exe ingest_recalls.py
Remove-Item Env:DATABASE_URL
```

Free-tier note: Render sleeps an idle service and Neon suspends an idle database, so the first request after a quiet
period can take up to a minute.

### What a bigger production setup would add

The free setup is fine for a demo. A real one would add: an always-on paid instance (no sleeping), monitoring and
alerts on the health checks and the request log, and several uvicorn workers.

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
The API is running but cannot reach PostgreSQL. Call `/health/db` to confirm (`/health` only says the API is up). Then check that the PostgreSQL service
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

**"`/insights/recalls/spikes` says `source: template` for every spike."**
The endpoint is working, but the AI was not used. Read `fallback_reason`, because it says why. "HF_TOKEN is not set"
means no token is in `.env`. "HTTP 402 (no remaining credits)" means the Hugging Face account cannot pay for
inference. "HTTP 401" means the token was rejected, and "HTTP 403" means it lacks the Inference Providers
permission. "timed out" or "could not reach Hugging Face" points at the network or the service. "the AI summary was
rejected: it contains numbers that are not in the facts" means the model made something up and the guardrail
worked as intended. Only the first failure in a request is tried: the other spikes then say they were skipped.

**"The dashboard says the API is unreachable, or the status light is red."**
Read the wording, because the three states mean different things. "API unreachable" means the browser got no answer at
all: the server is stopped, or (in development) only the dashboard is running and the API on port 8000 is not. "API is
up, database unavailable" means the API answered with a 503: PostgreSQL is down or `DATABASE_URL` is wrong. A section
showing "The API returned an error (HTTP 422)" means the request itself was rejected, and the message says why.
The sections reload by themselves once the status light is green again.

**"The badge says 'API unreachable' but the data still loads."**
The data loading proves the API is answering, so the browser itself is blocking the status check. A browser extension
can interfere with the dashboard's requests (seen with the SimplyCodes extension in Opera). Open the page in a private
window, where extensions are normally off, and check again. If the badge is green there, the app is fine.

**"Opening `http://127.0.0.1:8000/` shows `{"detail":"Not Found"}` instead of the dashboard."**
The dashboard has not been built, or the server was started before it was. Run `npm run build` inside `frontend/`, then
restart uvicorn (the dashboard is only mounted if `frontend/dist` exists when the server starts). `/docs` still works
either way, which is a quick way to tell a missing build apart from a stopped server.

**"Excel shows strange characters instead of accents (Müller looks like MÃ¼ller)."**
Opening the file by double-clicking should work, because the file starts with a byte order mark that tells Excel it is UTF-8. If it still looks wrong, the file was probably brought in through Excel's import wizard (Data, From Text/CSV). In that wizard, set the file origin to "65001: Unicode (UTF-8)".

**"Some cells in the CSV start with an apostrophe."**
That is the CSV injection guard working. Any text cell that begins with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading apostrophe so a spreadsheet cannot run it as a formula. Spreadsheets hide the apostrophe. To get the original value in code, remove one leading apostrophe.

**"The spike CSV took several seconds, and now it is fast."**
The first download of a spike without a saved summary asks the AI to write it, and saves it. Every later download uses the saved summary. Check the `source` and `fallback_reason` columns: if every row says `template`, the AI was not used (see the "source: template" scenario above).

**"The printed page looks wrong (a missing chart, a dark page, or buttons on paper)."**
First check that you used the page's own Print / Save as PDF button or Ctrl+P on the dashboard (not a screenshot). Then see the bug story below for how a missing printed chart was tracked down. The printed page is designed to be light even on a dark screen, to hide the buttons and the lookup, and to show every chart.

## Bug story: the chart that vanished from the printout

**What broke.** The printable report looked right on screen, and every test passed, but in the printed pages the monthly
chart was a blank gap between its legend and its caption.

**How it was found.** Unit tests cannot print, because the test browser has no print engine. So the page was printed with
Chrome's real print engine (a script started headless Chrome, loaded the page, waited for it to draw, and then asked for a
PDF), and the pages were read. The chart's box was there but empty. Measuring the chart's elements while the browser
pretended to be printing showed the box 631 px wide with the chart inside it 0 px wide.

**The cause.** One print rule said a chart must never be wider than the page (`max-width: 100%`). The charting library
draws inside a hidden wrapper that is zero pixels wide, so "100% of the wrapper" was 0 and the chart collapsed. Behind
that was a second problem: when a browser switches to its print layout it does not wait for a stretchy chart to measure
itself again.

**The fix.** Remove the rule. Just before printing (the browser's `beforeprint` event) the charts switch to a fixed
width that fits both Letter and A4 paper, and they switch back afterwards. Tests lock in both parts, and each was
proven to fail when deliberately broken.

**The lesson.** "The tests pass" is not the same as "it works on paper". Look at the real output, and when something
exists but cannot be seen, measure it.

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
