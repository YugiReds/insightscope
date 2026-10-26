# Troubleshooting Guide

Problems you might hit, grouped by where they show up. Each one says what you see, why it happens, and how to fix it. Entries marked **(hit)** actually happened during the build.

**First moves for almost any problem:**
1. Read the error message to the end. The useful line is usually the last one.
2. Check you're in the project folder with the venv active: the prompt should look like `(venv) PS C:\Users\anaah\projects\insightscope>`.
3. If you just installed something, close PowerShell and open a new window.

---

## 1. PowerShell and setup

### "Access is denied" when creating files or the venv (hit)
- **Why:** PowerShell opened in `C:\Windows\System32`, a protected system folder.
- **Fix:** move to the project first:

```powershell
cd ~\projects\insightscope
```

### A pasted command breaks with "Unexpected token" (hit)
- **Why:** multi-line code lost its line breaks when pasted, so PowerShell read one broken line.
- **Fix:** paste one-line commands, one at a time.

### "'psql' is not recognized" (hit)
- **Why:** PostgreSQL is installed, but its folder isn't on the PATH, or the window was opened before the PATH changed.
- **Fix:** open a new PowerShell window. If it still fails, check `Test-Path "C:\Program Files\PostgreSQL"`; if `True`, add `C:\Program Files\PostgreSQL\18\bin` to your user PATH.

### "running scripts is disabled on this system" when activating the venv
- **Why:** Windows blocks scripts by default.
- **Fix (once):**

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "ModuleNotFoundError: No module named 'fastapi'" (or pandas, sqlalchemy...)
- **Why:** the venv isn't active, so the wrong Python is running, or packages weren't installed.
- **Fix:** activate the venv, then reinstall from the list:

```powershell
.\venv\Scripts\Activate
```

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

### A value with `$` in it vanished (hit)
- **Why:** in PowerShell, `$18` inside double quotes is read as a variable (which is empty).
- **Fix:** use single quotes for anything containing `$`: `'...$18...'`. Check with `Get-Content .env`.

---

## 2. Database

### "password authentication failed for user postgres"
- **Why:** the password in `.env` is wrong or got mangled.
- **Fix:** `Get-Content .env` and compare it with your real password. Rewrite it with single quotes if needed.

### "connection refused" / "could not connect to server" / every API request returns 503
- **Why:** the PostgreSQL service isn't running.
- **Fix:** open **Services** (Win+R → `services.msc`), find **postgresql-x64-18**, and click **Start**. Then check `GET /health/db` (plain `/health` no longer touches the database).

### "database "insightscope" does not exist"
- **Fix:**

```powershell
psql -U postgres -c "CREATE DATABASE insightscope;"
```

Then reload the data with `ingest.py` and `ingest_recalls.py`.

### "relation "products" does not exist" (or "recalls")
- **Why:** the tables were never created, or the database was recreated.
- **Fix:** run the loaders:

```powershell
.\venv\Scripts\python.exe ingest.py
```

```powershell
.\venv\Scripts\python.exe ingest_recalls.py
```

### "KeyError: 'DATABASE_URL'"
- **Why:** `.env` is missing, misnamed (`.env.txt`), or the script was run from another folder.
- **Fix:** run scripts from the project folder, and check the file: `Get-Content .env`.

### How to check what's in the database

```powershell
psql -U postgres -d insightscope -c "SELECT relname AS table_name, n_live_tup AS row_count FROM pg_stat_user_tables ORDER BY relname;"
```

Expected: products ~5,000, active_ingredients ~7,900, packages ~9,700, recalls ~10,000, recall_ndcs ~7,000.

---

## 3. Loading data (ingest scripts)

### The download fails with HTTP 429 or 500+
- **Why:** the FDA's free API is rate-limited or briefly down.
- **Fix:** the recalls loader retries automatically 3 times. The products loader doesn't; just run it again in a minute. Your existing data is safe either way, because both scripts download everything before touching the database.

### "No records fetched, so the database was left untouched"
- **Why:** the FDA returned nothing (outage or network problem).
- **Fix:** check your internet, try again later. Nothing was deleted.

### A warning about a dropped recall number
- **Why:** a real FDA record has a blank or repeated recall number and can't be stored. One Aurobindo record is always dropped.
- **Fix:** nothing; it's expected and logged on purpose.

---

## 4. Running the API

### "address already in use" / "[Errno 10048]" on startup
- **Why:** another copy of the API is already running on port 8000.
- **Fix:** close the other terminal running uvicorn (Ctrl+C), or find it:

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
```

```powershell
Stop-Process -Id <the number shown>
```

### "Error loading ASGI app. Could not import module 'main'"
- **Why:** uvicorn was started outside the project folder.
- **Fix:** `cd ~\projects\insightscope` first.

### Code changes don't show up
- **Why:** the server was started without `--reload`.
- **Fix:** stop it (Ctrl+C) and start it with `--reload`.

---

## 5. API responses (what a user might report)

### 404 "No product found with NDC ..."
- **Why:** that NDC isn't in the 5,000-product sample, or it has a typo. The format is `labeler-product`, like `76961-101`.
- **Check the source:** `https://api.fda.gov/drug/ndc.json?search=product_ndc:"76961-101"`

### A plain 404 "Not Found" (no custom message) (hit)
- **Why:** the URL didn't match any endpoint, so the request never reached your code. Check the path for typos or unexpected slashes.
- **Example:** the `N/A` recall, fixed with the `{recall_number:path}` route.

### 422 Unprocessable Entity
- **Why:** the request breaks a rule. The response body says which field.
- **Common causes:** `limit` above 100 or below 1, negative `offset`, a search under 2 letters, a malformed NDC, a reasons `start` date after `end`, or an invalid date.

### 503 "Database unavailable"
- **Why:** the API is running but can't reach PostgreSQL.
- **Fix:** call `/health` to confirm, then see "connection refused" in section 2. The real error is in the terminal running the API.

### "The drug count looks wrong: 4,958 instead of 5,000"
- **Why:** expected. The API counts each NDC once (its newest label version); 33 NDCs have multiple versions.

### `total: 0` from `/products/{ndc}/recalls`
- **Why:** no recall in the ~10,000 loaded mentions that code. It doesn't prove the drug was never recalled: the table only covers 2018 onward, and many recalls list no drug codes at all.

### Paging gives repeated or missing items
- **Why:** a sort without a unique tiebreaker. Every list endpoint now ends its sort with a unique column; if you add a new list endpoint, do the same.

### The API feels slow
- **Fix:** read the request log in the API's terminal (`GET /search -> 200 (123 ms)`). Broad text searches scan the whole table; they're the first thing to index if the data grows.

---

## 6. AI summaries (Hugging Face)

### Every summary says `source: template` (hit)
- **Why:** the AI call didn't happen or failed. The `fallback_reason` field says which:
  - **"HTTP 402 (no remaining credits)"**: your Hugging Face credit balance is $0. Free accounts get no monthly credits for hosted models. Add credits under **Settings → Billing** on huggingface.co.
  - **Missing token**: `HF_TOKEN` isn't in `.env`. Check with `Select-String -Path .env -Pattern "HF_TOKEN" -Quiet` (should print `True`).
  - **HTTP 401 or 403**: the token is wrong, deleted, or lacks permission. Create a fine-grained token with the **Inference** preset.
  - **Timeout or other HTTP error**: the provider is busy; try again later.

### One summary is a template while the others are AI (hit)
- **Why:** the fact-checker rejected that AI summary because it contained a number not in the facts (e.g. "contains numbers that are not in the facts: 4").
- **Fix:** nothing; this is the guardrail doing its job, and the template is accurate. If rejections become frequent, improve the prompt or change `HF_MODEL`. Don't weaken the checker.

### A summary has correct numbers but says something the data doesn't (hit)
- **Example:** "Cardinal Health's 198 recalls were due to CGMP violations." The facts never link a firm to a reason.
- **Why:** the number check can't see claims, only numbers.
- **Fix:** add a prompt rule, bump `PROMPT_VERSION` in `insights.py` (so every summary regenerates), and re-check all six. If the rule can be written as code (like "products"/"items"), add a code check instead. This is how prompt v2 and v3 came about.

### `insight_cache` has more rows than spikes
- **Why:** each prompt version or model change creates new cache keys; old rows are never used again.
- **Fix (optional):** `DELETE FROM insight_cache;` clears it, and the next request regenerates the current summaries (costs a few cents).

### A summary didn't change after reloading the data
- **Why:** it shouldn't stay stale: the cache key includes the facts, so changed numbers get a fresh summary. If the numbers didn't change, the cached summary is correct.
- **To force fresh summaries:** clear the cache table:

```powershell
psql -U postgres -d insightscope -c "DELETE FROM insight_cache;"
```

### You accidentally shared your token (hit)
- **Fix:** on huggingface.co → **Access Tokens**, delete it, create a new one, and paste the new one straight into `.env`. Never paste a token into a chat or a screenshot.

### Worried about cost
- Check **Settings → Billing → Inference Usage** on huggingface.co. Keep **Automatic Recharge** off so you can never spend more than you added. Cached summaries don't call the AI again.

---

## 7. Tests and Postman

### The GitHub Actions run is red (the badge says "failing")
- **Where:** repo → **Actions** → the run → the red job → the red step. Read the last lines of its log.
- **Common causes:** a test really broke (run `.\venv\Scripts\python.exe -m pytest` or `npm test` locally); the versions in the workflow and `render.yaml` drifted apart (a `test_ci_setup.py` test names them); `requirements.txt` or `package-lock.json` is out of date.
- **Not your code?** If only the "Set up job" or "Initialize containers" step failed, GitHub had a hiccup. Click **Re-run all jobs**.

### CI shows "269 passed, 1 skipped" (hit)
- **Why:** the `.env` fallback test in `test_deploy_ready.py` skips in CI, because CI has no `.env` (and never should). It runs on your PC.
- **Fix:** nothing. That's the expected result.

### "Refusing to run: the database name in DATABASE_URL must be exactly 'insightscope_ci'"
- **Why:** `tests/seed_ci_data.py` deletes rows before inserting, so it only runs against the throwaway CI database. This is the guard working.
- **Fix:** point `DATABASE_URL` at a database named `insightscope_ci`. Never rename your real database to get around it.

### Notice: "The ubuntu-latest label will migrate to Ubuntu 26"
- **Why:** GitHub is upgrading its machines. It's a notice, not an error.
- **Fix:** nothing needed. To control the timing, change `runs-on: ubuntu-latest` to `runs-on: ubuntu-24.04` in the workflow.

### Tests fail with a database error
- **Why:** PostgreSQL isn't running, or the data isn't loaded. Most tests run against the real database.
- **Fix:** sections 2 and 3, then `.\venv\Scripts\python.exe -m pytest` again.

### Every Postman request fails with "Could not send request" / ECONNREFUSED
- **Why:** the API isn't running.
- **Fix:** start it in its own terminal, wait for `Application startup complete`, then run the collection.

### Postman results don't match the latest changes
- **Why:** Postman is using an old imported copy.
- **Fix:** delete the collection in Postman and import the JSON again.

### A new endpoint returns 404 in Postman but the code has it (hit)
- **Why:** the uvicorn running on your PC was started before the change and without `--reload` (or it's an old leftover process).
- **Fix:** Ctrl+C in its terminal and start it again: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`.

### Postman passes locally but a lookup 404s against the live site (hit)
- **Why:** the live database (Neon) was loaded from a different openFDA sample, so a hard-coded NDC or recall number may not exist there.
- **Fix:** don't hard-code data IDs. The collection now saves them from earlier responses (`sampleNdc`, `sampleRecallNumber` and so on). If a lookup still fails, check that the list request ran first.

### Postman still calls `127.0.0.1` after changing `baseUrl`
- **Why:** the change wasn't saved, or an environment with its own `baseUrl` is selected.
- **Fix:** set the **Current value** in the collection's **Variables** tab, press **Ctrl+S**, and check the top right says **No Environment**.

### Red 404 / 422 badges in Postman
- **Not a problem** when the checks under them say PASS. Those requests test error cases on purpose.

---

## 8. Dashboard (npm, Vite, the page)

### DevTools won't open (F12 or Ctrl+Shift+I does nothing, or something else opens) (hit)
- **Why:** on some keyboards (like Keychron) the F-keys default to media keys, and AMD Software grabs Ctrl+Shift+I for desktop recording.
- **Fix:** right-click the page → **Inspect**. Then click the phone/tablet icon to test phone widths.

### Light mode doesn't appear after switching Windows to Light (hit)
- **Why:** some browsers (Opera) follow their own theme, not Windows.
- **Fix:** test in Chrome, or in DevTools: **⋮ → More tools → Rendering → prefers-color-scheme: light**. Turn off any "Force dark pages" setting.

### "'npm' is not recognized"
- **Why:** Node.js isn't installed, or the window was opened before it was.
- **Fix:** open a new PowerShell window and run `node -v`. If that fails too, install Node.js LTS.

### `npm run dev` says "Missing script" or "Could not read package.json"
- **Why:** you're in the project folder, not `frontend`.
- **Fix:** `cd frontend` first.

### "Cannot find module" / "vite is not recognized"
- **Why:** packages aren't installed (fresh clone, or `node_modules/` deleted).
- **Fix:** run `npm install` inside `frontend`.

### The dev page won't load at `127.0.0.1:5173` (hit)
- **Why:** on Windows the Vite dev server may only answer on `localhost`.
- **Fix:** open http://localhost:5173.

### The status light says "API unreachable" and a red banner appears
- **Why:** FastAPI isn't running on port 8000. In dev mode Vite forwards API calls there.
- **Fix:** start uvicorn in a second terminal. The sections reload by themselves within about 15 seconds.
- **On the live site, while the numbers and charts still load:** the API is fine. A browser extension is blocking the status check. See "Live site says API unreachable in one browser only" in section 10.

### The status light says "API is up, database unavailable"
- **Why:** `/health/db` answered 503: PostgreSQL is stopped (locally) or Neon can't be reached (live).
- **Fix:** locally, see "connection refused" in section 2. On the live site, open `/health/db` directly and check Neon's dashboard.

### `http://127.0.0.1:8000/` shows JSON `{"detail":"Not Found"}` instead of the dashboard
- **Why:** the dashboard isn't built, or uvicorn started before the first build. `main.py` only mounts `frontend/dist/` if it existed at startup.
- **Fix:** run `npm run build` inside `frontend`, then restart uvicorn.

### The dashboard on port 8000 shows old content after a code change
- **Why:** port 8000 serves the last **build**. Only the dev server (5173) updates live.
- **Fix:** run `npm run build` again, or use the dev server while editing.

### A new API endpoint 404s in dev mode but works on port 8000
- **Why:** the Vite proxy only forwards the paths listed in `frontend/vite.config.js`.
- **Fix:** add the new top-level path to `API_PATHS`, then restart `npm run dev`.

### Every Python test fails to collect after editing `main.py` (hit)
- **Why:** `from pathlib import Path` replaced FastAPI's `Path`.
- **Fix:** use `import pathlib` and `pathlib.Path(...)`.

### pytest shows "4 skipped"
- **Not a problem.** Four dashboard tests check the real build and skip until `npm run build` has been run.

### A download button shows an error, or `/reports/...` returns 404
- **Why:** the API was started before the reports code existed, without `--reload`.
- **Fix:** stop uvicorn (Ctrl+C) and start it again.

### A CSV opens in Excel with garbled accented names
- **Why:** the file lost its byte order mark (for example, re-saved by another tool).
- **Fix:** download it again from the dashboard, or in Excel use Data → From Text/CSV and choose UTF-8.

### A cell in the CSV starts with an apostrophe, like `'+Protec Hands Gel`
- **Not a problem.** That's the CSV-injection guard. Excel hides the apostrophe and shows the text.

### The chart is missing from the printed PDF (hit)
- **Why:** on paper the chart's stretch-to-fit box can measure zero width.
- **Fix:** already fixed: charts switch to a fixed width when printing starts. If it comes back after editing print CSS, check that charts don't have `max-width: 100%`, and that `ChartFrame.jsx` is still used.

### The printout has the URL and date at the top and bottom
- **Fix:** in the print window, open **More settings** and turn off **Headers and footers**.

### Spike cards take a few seconds on the first visit
- **Why:** the AI writes any summaries that aren't cached yet. Later visits use the cache.

---

## 9. Git and GitHub

### "remote origin already exists" (hit)
- **Why:** `git remote add origin` was run twice. The first one worked.
- **Fix:** nothing.

### "Your branch is ahead of 'origin/main' by 1 commit" (hit)
- **Why:** you committed but didn't push.
- **Fix:** `git push`.

### "did not match any files" from `git rm` (hit)
- **Why:** the file is already gone.
- **Fix:** nothing.

### "LF will be replaced by CRLF"
- **Why:** Windows line endings. Harmless.

### A commit shows "0 insertions" for `requirements.txt` (hit)
- **Why:** the file was saved as UTF-16 by PowerShell's `>`.
- **Fix:**

```powershell
pip freeze | Set-Content -Encoding ascii requirements.txt
```

### `.env` shows up in `git status`
- **Stop. Don't commit.** Check `.gitignore` still contains `.env`:

```powershell
git check-ignore -v .env
```

If it prints nothing, add it back: `Add-Content .gitignore ".env"`. If `.env` was already committed, change your PostgreSQL password and ask for help removing it from history.

### `node_modules/` or `dist/` shows up in `git status`
- **Stop. Don't commit.** Check `.gitignore` contains `frontend/node_modules/` and `frontend/dist/`: `git check-ignore -v frontend/node_modules`.

### Unexpected folders appear in `git status` (`.vscode/`, `.postman/`, `New Collection/`) (hit)
- **Why:** tools create their own folders.
- **Fix:** add them to `.gitignore` before committing, e.g. `Add-Content .gitignore ".vscode/"`.

---

## 10. Deploy (Render and Neon)

### The first visit to the live site takes up to a minute
- **Why:** the free Render service sleeps after 15 minutes with no visitors, and Neon suspends an idle database. Render shows a loading page while it wakes.
- **Fix:** nothing to fix; that's the free tier. Open the site a minute before a demo or interview.

### `ValueError: DATABASE_URL must start with postgres://, postgresql:// ... but it starts with (no scheme)` (hit)
- **Why:** whatever is in `DATABASE_URL` isn't a connection string. In step 8b the clipboard still held the `uvicorn` command, so that got pasted at the `Read-Host` prompt. Snippet views in Neon (`psql '...'` or `DATABASE_URL=...`) cause the same error.
- **Fix:** copy only the plain string from Neon (`postgresql://` to `channel_binding=require`), run `$env:DATABASE_URL = Read-Host "Paste Neon URL"`, paste **at the prompt**, then check without showing the password:

```powershell
$env:DATABASE_URL.Substring(0, 15)
```

It should print `postgresql://in`.

### The `Read-Host` prompt shows your URL followed by `:` and waits (hit)
- **Why:** the URL was typed into the command in place of the words `"Paste Neon URL"`, so PowerShell used it as the question text. The password is now on screen and in the command history.
- **Fix:** press Ctrl+C, **reset the password in Neon**, and run the command exactly as written, pasting only after the prompt appears.

### You shared the database connection string (hit)
- **Why:** the string contains the password (the part after `insightscope_owner:` and before `@`).
- **Fix:** in Neon, **Postgres database → Roles → ⋮ beside `insightscope_owner` → Reset password**. Copy the new string from **Connect**, then update it in Render (**Environment** → `DATABASE_URL`) and redeploy. Deleting the message doesn't undo a leak; changing the password does.

### `localhost refused to connect` on port 8001
- **Why:** nothing is listening, because uvicorn crashed or was stopped. It's not a database problem.
- **Fix:** look at the terminal. Fix the error shown there, start uvicorn again and wait for `Uvicorn running on http://127.0.0.1:8001`.

### Render says "No repositories found"
- **Why:** Render is signed in to GitHub but hasn't been given access to any repository.
- **Fix:** click **GitHub** (or **Configure account**) and choose **Only select repositories** → `insightscope`.

### The Render build fails with "vite: not found"
- **Why:** Vite is a development dependency and `npm ci` skipped it.
- **Fix:** the build command must use `npm ci --include=dev` (it already does in `render.yaml`).

### Live site says "API unreachable" in one browser only (hit)
- **Why:** a browser extension blocks or rewrites the status-check request. In step 8b it was **SimplyCodes** in Opera; Chrome, the phone and an Opera private window were all green.
- **How to tell:** the numbers and charts still load (they come from the same API), only the badge is red.
- **Fix:** open the site in a private window (extensions off). If it's green there, limit that extension's site access or remove it. Turning off Opera's ad blocker didn't help here.

### The live site shows no data, or an error, after a deploy
- **Why:** usually `DATABASE_URL` in Render is wrong (pooled string, quotes, `psql` prefix) or the password was reset in Neon but not updated in Render.
- **Fix:** open `https://insightscope.onrender.com/health/db`. A 503 means the database can't be reached; fix `DATABASE_URL` in Render → **Environment** and redeploy. Check Render's **Logs** for `Database tables are ready`.

### AI summaries on the live site are all "Template"
- **Why:** `HF_TOKEN` is missing or wrong in Render, or the token lacks "Make calls to Inference Providers".
- **Fix:** create a new fine-grained token with that one permission and paste it into Render → **Environment** → `HF_TOKEN`. Summaries already saved in Neon's `insight_cache` don't need the AI again.

### A pushed change doesn't appear on the live site
- **Why:** Render is still building (a few minutes), or the build failed.
- **Fix:** Render → the service → **Events**. A failed deploy keeps the old version running; open its log to see why.
