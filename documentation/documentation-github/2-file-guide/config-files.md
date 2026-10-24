# Config and project files

These aren't code, but the project doesn't work (or isn't safe) without them.

## `.env`: the secrets file

**Job:** holds the secrets and settings the code reads at runtime:

| Line | Meaning |
| --- | --- |
| `DATABASE_URL` | The database connection string, including your PostgreSQL password |
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

**Why it matters:** without it, each Claude Code session would start with no memory of the project's decisions.

## `README.md`: the repo's front page

**Job:** the first thing a recruiter sees on GitHub. It covers what the project does, how the pieces fit, setup steps, every endpoint, how the analytics work, the duplicate-NDC quirk, troubleshooting scenarios and the N/A bug story.

**Why it matters:** it's your project's pitch, and its troubleshooting section reads like a support knowledge-base article.
