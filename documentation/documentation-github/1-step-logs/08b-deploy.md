# Step 8b: Deploy

**Result:** InsightScope is live at **https://insightscope.onrender.com**. One free Render web service runs the API and serves the dashboard, and the data lives in a free Neon PostgreSQL database. The README now has the live link and a dashboard screenshot. Tests grew to 239 Python and 73 dashboard tests, and the Postman collection grew to 31 requests.

**Date:** October 24, 2026 (morning)

## The goal

Give recruiters a link they can click instead of a "clone it and run it" README. Keep it free, keep the secrets out of Git, and make every future `git push` update the live site by itself.

## The pieces

| Piece | Service | Why this one |
| --- | --- | --- |
| Web service (FastAPI + built dashboard) | **Render**, free plan, region Virginia | Builds straight from GitHub, reads a `render.yaml` file, free HTTPS, auto-deploy on every push |
| Database | **Neon**, free plan, AWS US East 1 (N. Virginia), Postgres 18 | Free Postgres that doesn't expire. Render's own free Postgres is deleted after 30 days, and Supabase's free projects pause after a week idle |
| AI summaries | **Hugging Face**, a new token used only by Render | If one token leaks, it can be deleted without breaking the other |

Both services sit in northern Virginia, so the API and the database talk over a short distance and queries stay fast.

## Accounts created, in order

1. **Neon** (signed in with GitHub). Project and database both named `insightscope`, Postgres 18, only the Postgres service switched on.
2. **Render** (signed in with GitHub). GitHub access limited to **only** the `insightscope` repository.
3. **Hugging Face token** `insightscope-render`: fine-grained, **Custom**, with only "Make calls to Inference Providers" ticked. Automatic recharge stays off.

## What was built

| Part | What it does |
| --- | --- |
| `render.yaml` (new) | A **Blueprint**: one free web service. Build: `pip install -r requirements.txt && cd frontend && npm ci --include=dev && npm run build`. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`. Health check: `/health`. Pins Python 3.12.10 and Node 24.15.0 |
| `normalize_database_url()` in `db.py` | Accepts `postgres://`, `postgresql://` or `postgresql+psycopg://` and turns it into the form SQLAlchemy needs. Keeps `?sslmode=require&channel_binding=require` exactly. Its error message never repeats the address, because the address contains the password |
| Engine settings in `db.py` | `pool_pre_ping=True` (test a connection before using it), `pool_recycle=300` (replace connections older than 5 minutes) and `connect_timeout=10`, because Neon drops connections when it goes to sleep |
| `GET /health` | Answers `{"status":"ok"}` at once and **never touches the database** |
| `GET /health/db` (new) | Runs `SELECT 1`. Answers `{"status":"ok","database":"reachable"}`, or 503 if the database is down |
| Startup table creation in `main.py` | On start, a background thread creates any missing table (including `insight_cache`) and retries if Neon is still waking up. It never drops or empties anything, and never delays `/health` |
| Status light (`useHealth` in `hooks.js`) | Checks `/health` every 15 seconds, but `/health/db` only at the start, at most once a minute, never while the tab is hidden, and right after the API comes back |
| `.env.example` (new) | Fake Neon-style placeholders that show the format. The real `.env` is still never committed |
| README | Live demo link, dashboard screenshot (`screenshots/dashboard.png`), a "Deploying to Render and Neon" section, and a troubleshooting note |

## Decisions worth explaining in an interview

**Two health checks instead of one.** Render pings `/health` every few seconds. If that ran a database query, Neon would never get to sleep and the free compute hours would run out. So `/health` only proves the API process is up, and `/health/db` proves the database answers. This is the difference between a **liveness** check (is the process alive?) and a **readiness/dependency** check (can it do its job?).

**The status light had to change too.** It used to read a 503 from `/health` as "database down". Once `/health` stopped touching the database, the dashboard would have shown green even with the database down. Claude Code spotted this and rewrote the hook to use both routes, with a throttle so a forgotten tab can't keep Neon awake.

**Direct connection, not pooled.** Neon offers a pooled connection string (host contains `-pooler`) and a direct one. The pooler can complain about prepared statements, which psycopg uses. The app has very little traffic, so the direct string is simpler and safer.

**The data was loaded from the PC, not on Render.** In one PowerShell window only, `DATABASE_URL` was set to the Neon string with `Read-Host`. Then the same `ingest.py` and `ingest_recalls.py` ran against Neon. A variable set in the shell wins over `.env` (`load_dotenv()` doesn't override), so `.env` was never edited. Closing that terminal cleared the variable.

**Secrets live only in Render's settings.** `DATABASE_URL` and `HF_TOKEN` are `sync: false` in `render.yaml`, so Render asks for them when the service is created and they never touch Git.

**`npm ci --include=dev`.** Vite is a development dependency. If the host sets `NODE_ENV=production`, plain `npm ci` skips dev dependencies and the build fails with "vite not found". Adding `--include=dev` rules that out.

**Free-tier trade-off.** Render sleeps the service after 15 minutes with no visitors, and the first visit afterwards takes about a minute. The README says so, so a recruiter isn't surprised.

## Commands used

Load the data into Neon (in a new terminal, so the Neon address only exists there):

```powershell
$env:DATABASE_URL = Read-Host "Paste Neon URL"
```

Check what was pasted without showing the password (should print `postgresql://in`):

```powershell
$env:DATABASE_URL.Substring(0, 15)
```

```powershell
uvicorn main:app --port 8001
```

Open `http://localhost:8001/health/db`, then stop it with Ctrl+C, then:

```powershell
python ingest.py
```

```powershell
python ingest_recalls.py
```

Close the terminal (trash-can icon) when done, so the Neon address is gone.

## What came out of it

| Check | Result |
| --- | --- |
| `/health/db` from the PC against Neon | `{"status":"ok","database":"reachable"}` |
| Recalls loaded into Neon | 9,999 recalls and 6,996 recall–NDC links (1 record with no recall number skipped, same as locally) |
| First AI summaries on Neon | About 19 seconds, then saved in `insight_cache` |
| Render build and start | "Your service is live", "Database tables are ready", `/health` 200 every few seconds |
| Live dashboard (Chrome and phone) | 9,999 recalls, 11.8% Class I, 6 spike months, green "API and database OK" |
| Auto-deploy | The README commit (`371bacc`) triggered a new deploy by itself |

## Problems hit along the way

| Problem | Cause | Fix |
| --- | --- | --- |
| **The database password ended up in chat, twice** | The connection string was pasted into the chat once, then typed into the command itself (and screenshotted) instead of at the `Read-Host` prompt | Reset the password in Neon (**Roles → ⋮ → Reset password**) each time, then copied the new string from **Connect**. A leaked password is fixed by changing it, not by deleting the message |
| `ValueError: ... but it starts with (no scheme)` | The clipboard held the `uvicorn` command, so that got pasted at the `Read-Host` prompt instead of the URL | Copy the URL last, run `Read-Host`, paste at the prompt, then check with `.Substring(0, 15)` |
| `localhost refused to connect` on port 8001 | uvicorn had crashed (the error above), so nothing was listening | Read the terminal first; a refused connection means "no server", not "database problem" |
| Render said "No repositories found" | Render was signed in to GitHub but had no repo access yet | Clicked **GitHub** and gave access to `insightscope` only |
| **Live site showed "API unreachable" in Opera only** | The **SimplyCodes** browser extension interfered with the status check. Chrome, the phone and an Opera private window were all green, and the data still loaded | Not an app bug. Limit or remove the extension. README troubleshooting now mentions it |

**The lesson from the Opera bug:** when the page shows data but the badge says the API is down, the API is fine. Something between the browser and the API is blocking one request. A private window (extensions off) is the fastest test.

## Testing the tests

Claude Code broke the code on purpose 14 times, and the tests caught every one. Examples on the Python side: dropping tables at startup, blocking startup while the database is asleep, and breaking `/health/db`. One break exposed a gap in its own new test, which it then fixed. On the dashboard side: breaking the database-check throttle and the reset after an outage.

## Follow-up: Postman against the live site (October 25)

The first live Postman run passed 73 of 75. "Get product by NDC (76961-101)" got a **404**: Neon was loaded later than the local database, from a different openFDA sample, so that NDC wasn't there. Running it locally also showed a 404 on `/health/db`, which turned out to be an old uvicorn process started before step 8b; restarting it fixed that.

Claude Code changed the collection so requests read their IDs from earlier responses (product NDC, labeler word, recall number, a recall's NDC) instead of hard-coding them. The N/A recall now accepts our own 404 message but still fails on FastAPI's generic one. Details in the [Postman file guide](../2-file-guide/postman.md).

**Result:** 78 of 78 tests passed, both locally and live.

**Interview line:** "A test passed locally and failed in production because it hard-coded data. I changed it to take its test data from the API's own responses, so the same suite runs against any environment."

## Not checked

- Behaviour after Neon's monthly compute allowance runs out (not expected at this traffic).
- What the site looks like in browsers other than Chrome, Opera and the phone.

## Git commits in this step

| Commit | Message |
| --- | --- |
| `81e92a2` | step 8b part 1: deploy-ready (health routes, DB URL normalization, render.yaml) |
| `371bacc` | step 8b part 2: README live demo link, dashboard screenshot, deploy docs |
| `e4a626b` | step 8b docs: deploy step log, file guides, troubleshooting |
| `788d333` | README: production section reflects Render + Neon |
| *(pending)* | Postman: IDs taken from earlier responses; works locally and live |

## Interview lines

- "It's live on Render with a Neon Postgres database, deployed from a Blueprint file, and every push to main redeploys it automatically."
- "I split the health check: `/health` proves the process is up and never touches the database, so the host's health pings don't keep the serverless database awake. `/health/db` checks the dependency."
- "Secrets only exist in the host's settings. The Hugging Face token for production is a separate, least-privilege token, so I can revoke it without touching my local one."
- "When I accidentally exposed the database password, I rotated it right away instead of just deleting the message, the same as you'd handle any leaked credential."
- "A user reported 'API unreachable' while the data was still loading. I isolated it to a browser extension by testing in Chrome, on a phone and in a private window, which is the same process I use in support."
