# Step 0: Setup

**Result:** a Windows PC ready to build InsightScope, with the project folder, a Python virtual environment, a database, Git and a public GitHub repo.

**Date:** October 22–23, 2026

## Why this step mattered

Every later step needs these tools. Getting them right once means each new step only adds code, not more installs.

## Tools installed

| Tool | Version | What it does |
| --- | --- | --- |
| Python | 3.12.10 | The programming language the project is written in |
| Git | 2.55 | Saves snapshots (commits) of your work and sends them to GitHub |
| VS Code | 1.143 | The editor where you see files and run Claude Code |
| PostgreSQL | 18.3 | The database that stores the drug and recall data |
| Postman | 12.33 | Sends test requests to the API (used from step 3) |
| Node.js | 24.15 | Already installed; needed later for the dashboard (step 7) |
| Claude Code | VS Code extension | The AI that writes and explains code with you |

Install command used for most of them (Windows' built-in installer):

```powershell
winget install -e --id Postman.Postman
```

To check what's installed at any time:

```powershell
foreach ($t in "python","git","code","psql","node") { if (Get-Command $t -ErrorAction SilentlyContinue) { Write-Host "OK $t -> " -NoNewline; & $t --version 2>&1 | Select-Object -First 1 } else { Write-Host "MISSING $t" } }
```

## What was set up, in order

1. **Fixed the PostgreSQL PATH.** PostgreSQL was installed, but PowerShell couldn't find `psql`. Its `bin` folder (`C:\Program Files\PostgreSQL\18\bin`) was added to the PATH. A new PowerShell window was needed to see the change.
2. **Created the database.** This made an empty database called `insightscope`:

   ```powershell
   psql -U postgres -c "CREATE DATABASE insightscope;"
   ```

3. **Made the project folder** at `C:\Users\anaah\projects\insightscope`. It's outside System32 (protected) and outside OneDrive (syncing a code folder causes problems).
4. **Created a virtual environment (`venv`).** This is a private copy of Python for this project only, so its packages don't mix with anything else on your PC. `(venv)` at the start of the prompt means it's active.

   ```powershell
   python -m venv venv
   ```

   ```powershell
   .\venv\Scripts\Activate
   ```

5. **Installed the Python packages:**

   ```powershell
   pip install fastapi "uvicorn[standard]" sqlalchemy "psycopg[binary]" pandas requests python-dotenv
   ```

   | Package | Job |
   | --- | --- |
   | fastapi | Builds the API |
   | uvicorn | Runs the API |
   | sqlalchemy | Talks to the database from Python |
   | psycopg | The driver SQLAlchemy uses to reach PostgreSQL |
   | pandas | Cleans data |
   | requests | Calls the FDA's website |
   | python-dotenv | Reads the password from `.env` |

6. **Saved the package list** to `requirements.txt` so anyone can reinstall everything later.
7. **Created `.gitignore`** so Git never saves `venv/`, `.env` or cache files.
8. **Created `.env`** holding the database connection string (with your password). Single quotes were needed because of the `$` in the password.
9. **Set your Git identity** using your GitHub noreply email, so commits credit you without exposing your Gmail:

   ```powershell
   git config --global user.name "Ahmed Adam"; git config --global user.email "131390561+YugiReds@users.noreply.github.com"
   ```

10. **Made the first commits, created the GitHub repo and pushed** (details in [step 1](01-data-pipeline.md)).
11. **Set up VS Code:** trusted the folder (so extensions work), installed the Python extension, and picked `.\venv\Scripts\python.exe` as the interpreter.

## Problems hit and fixed

| Problem | Cause | Fix |
| --- | --- | --- |
| "Access is denied" creating the venv | PowerShell opened in `C:\Windows\System32` | Made the project in your home folder |
| Multi-line commands broke when pasted | Line breaks got lost in the paste | Commands are now one line per box |
| `psql` not recognized | PostgreSQL's folder wasn't on the PATH | Added it, then opened a new window |
| Password in `.env` was cut short | `$18` inside double quotes is read as a variable | Rewrote it with single quotes |
| `requirements.txt` unreadable by Git | Windows PowerShell's `>` saves UTF-16 | `pip freeze \| Set-Content -Encoding ascii requirements.txt` |
| "Python: Select Interpreter" missing | VS Code was in Restricted Mode, and the Python extension wasn't installed | Trusted the folder, installed the extension |

## Git commands learned in this step

| Command | What it does |
| --- | --- |
| `git init` | Turns a folder into a Git project |
| `git add .` | Gathers changed files, ready to save |
| `git status` | Shows what's about to be saved; check `.env` isn't listed |
| `git commit -m "message"` | Saves a snapshot with a note |
| `git branch -M main` | Names the main branch "main" |
| `git remote add origin <url>` | Tells Git where the GitHub repo is |
| `git push -u origin main` | First upload to GitHub; after that, plain `git push` |
