# Config and project files

These aren't code, but the project doesn't work (or isn't safe) without them.

## `.env`: the secrets file

**Job:** holds the secrets and settings the code reads at runtime:

| Line | Meaning |
| --- | --- |
| `DATABASE_URL` | The database connection string, including your PostgreSQL password. A `DATABASE_URL` set in the shell (or by Render) wins over this file |
| `HF_TOKEN` | Your Hugging Face token (step 6). Fine-grained, Inference preset |
| `HF_MODEL` | Optional: which AI model to use; defaults to `meta-llama/Llama-3.1-8B-Instruct` |

**What it looks like** (password replaced):

```
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/insightscope
```

Reading the connection string left to right:

| Part | Meaning |
| --- | --- |
| `postgresql+psycopg://` | Use PostgreSQL through the psycopg driver |
| `postgres` | The database user name |
| `YOUR_PASSWORD` | That user's password |
| `localhost:5432` | The database runs on this PC, on port 5432 (PostgreSQL's default) |
| `insightscope` | The database name |

**Why it matters:** the code reads the password from here at runtime, so it never appears in code that goes on GitHub.

**Rules:**
- Never commit it. `.gitignore` blocks it.
- When writing it from PowerShell, use **single quotes**, because `$` inside double quotes is treated as a variable.
- Check it's protected: `git check-ignore -v .env` should print a line, and `git ls-files .env` should print nothing.

## `.env.example`: the safe copy

**Job:** shows the format of `.env` with **fake** values, so someone cloning the repo knows what to fill in. It *is* committed, which is why it shows up in `git status` while `.env` doesn't.

```
DATABASE_URL=postgresql://neondb_owner:YOUR_PASSWORD@ep-example-123456.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
HF_TOKEN=hf_your_token_here
```

Never put a real password or token in it.

## `render.yaml`: the Render Blueprint

**Job:** tells Render how to build and run the live site. Render reads it when you choose **New → Blueprint**, and re-reads it on every push.

```yaml
    runtime: python
    region: virginia
    plan: free
    buildCommand: pip install -r requirements.txt && cd frontend && npm ci --include=dev && npm run build
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
```

| Line | Meaning |
| --- | --- |
| `region: virginia` | Same area as the Neon database (AWS US East 1), so queries stay fast |
| `plan: free` | The free instance. It sleeps after 15 minutes idle, and the next visit takes about a minute |
| `buildCommand` | Installs the Python packages, then builds the dashboard into `frontend/dist` (which isn't in Git) |
| `--include=dev` | Makes sure Vite (a dev dependency) is installed even if the host sets `NODE_ENV=production` |
| `--host 0.0.0.0 --port $PORT` | Listen on the port Render assigns, from outside the container |
| `healthCheckPath: /health` | Render pings this every few seconds. It never touches the database, so Neon can sleep |

```yaml
      - key: DATABASE_URL
        sync: false
      - key: HF_TOKEN
        sync: false
```

`sync: false` means "ask me for the value when the service is created". The real secrets live only in Render's settings, never in Git. `HF_MODEL`, `PYTHON_VERSION` (3.12.10) and `NODE_VERSION` (24.15.0) are plain values in the file.

**Careful:** the purple banner in Render says changes to this file are applied automatically. Changing `plan: free` to a paid plan here would cost money.

## `.gitignore`: what Git never saves

**Job:** a list of files and folders Git pretends don't exist.

```
venv/
.env
__pycache__/
*.pyc
.vscode/
.postman/
postman/collections/
postman/globals/
documentation/documentation/
frontend/node_modules/
frontend/dist/
```

| Entry | Why it's ignored |
| --- | --- |
| `venv/` | Huge, and rebuilt from `requirements.txt` |
| `.env` | Contains your password |
| `__pycache__/`, `*.pyc` | Python's temporary compiled files |
| `.vscode/` | Your personal VS Code settings |
| `.postman/` | Postman's local workspace files |
| `postman/collections/`, `postman/globals/` | Postman's own YAML copies, which drift out of sync; the JSON collection is the source of truth |
| `documentation/documentation/` | Your PDF copy of the docs (the Markdown copy in `documentation-github/` is committed) |
| `frontend/node_modules/` | 139 MB of npm packages, rebuilt exactly by `npm install` from `package-lock.json` |
| `frontend/dist/` | Build output from `npm run build`; committing it would add minified code to every diff and go stale |

## `requirements.txt`: the package list

**Job:** lists every Python package and its exact version, so anyone can recreate the environment:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

**To update it after installing something new:**

```powershell
pip freeze | Set-Content -Encoding ascii requirements.txt
```

Avoid `pip freeze > requirements.txt` in Windows PowerShell: `>` can save the file as UTF-16, which Git can't read as text.

## `frontend/package.json`, `package-lock.json`, `.npmrc`

The dashboard's version of `requirements.txt`. `package.json` lists the npm packages (pinned exactly), `package-lock.json` records every sub-package, and `.npmrc` turns off install scripts. All three are committed. Details in [frontend.md](frontend.md).

## `pytest.ini`: test settings

A small settings file that tells pytest where the tests are. You rarely need to touch it.

## `CLAUDE.md`: Claude Code's rulebook

**Job:** Claude Code reads this at the start of every session. It describes the project and its rules.

Key rules in it:
- Always run Python with `.\venv\Scripts\python.exe`.
- Never print, read out or commit `.env`.
- Ask before installing packages; keep `requirements.txt` in sync.
- Keep code simple, with plain-language comments, because you need to explain every file in an interview.
- The duplicate-NDC rule: use the newest label version per NDC.
- API rules: a unique tiebreaker in every sort, nullable fields, recalls-by-NDC behavior.
- Keep recalls in their own table list so `ingest.py` can't wipe them.
- Keep the dashboard mount last in `main.py`, and use `import pathlib`, not `from pathlib import Path`.
- `/health` must never touch the database; the live site is on Render + Neon with the direct (not pooled) connection string.

**Why it matters:** without it, each Claude Code session would start with no memory of the project's decisions.

## `README.md`: the repo's front page

**Job:** the first thing a recruiter sees on GitHub. It starts with the **live demo link** and a dashboard screenshot (`screenshots/dashboard.png`), then covers what the project does, how the pieces fit, setup steps, every endpoint, how the analytics work, the duplicate-NDC quirk, troubleshooting scenarios and the N/A bug story.

**Why it matters:** it's your project's pitch, and its troubleshooting section reads like a support knowledge-base article.
