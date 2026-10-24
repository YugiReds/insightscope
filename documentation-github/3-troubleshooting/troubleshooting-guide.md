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
- **Fix:** open **Services** (Win+R → `services.msc`), find **postgresql-x64-18**, and click **Start**. Then check `GET /health`.

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

## 6. Tests and Postman

### Tests fail with a database error
- **Why:** PostgreSQL isn't running, or the data isn't loaded. Most tests run against the real database.
- **Fix:** sections 2 and 3, then `.\venv\Scripts\python.exe -m pytest` again.

### Every Postman request fails with "Could not send request" / ECONNREFUSED
- **Why:** the API isn't running.
- **Fix:** start it in its own terminal, wait for `Application startup complete`, then run the collection.

### Postman results don't match the latest changes
- **Why:** Postman is using an old imported copy.
- **Fix:** delete the collection in Postman and import the JSON again.

### Red 404 / 422 badges in Postman
- **Not a problem** when the checks under them say PASS. Those requests test error cases on purpose.

---

## 7. Git and GitHub

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

### Unexpected folders appear in `git status` (`.vscode/`, `.postman/`, `New Collection/`) (hit)
- **Why:** tools create their own folders.
- **Fix:** add them to `.gitignore` before committing, e.g. `Add-Content .gitignore ".vscode/"`.
