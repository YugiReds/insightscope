# File Guide

One guide per important file: what it does, why it matters, and the key lines (copied from the real file so you can find them with `Ctrl+F` in VS Code).

## How the pieces fit

```
openFDA website
   │  ingest.py / ingest_recalls.py  (download, clean, load)
   ▼
PostgreSQL database  ◄── db.py (connection + table definitions, reads .env)
   ▲
   │  main.py (endpoints)  +  analytics.py (math)  +  reports.py (CSV)  +  insights.py (AI summaries)  +  schemas.py (response shapes)
   │
Clients: the dashboard (frontend/, served by main.py at /), your browser (/docs), Postman, the tests
```

**Live:** the same code runs on Render (`render.yaml`) at https://insightscope.onrender.com, with the database on Neon. Locally, `DATABASE_URL` comes from `.env`; on Render it's a secret set in Render's settings.

## The files

| File | One-line job | Guide |
| --- | --- | --- |
| `.env` | Holds the database password (never on GitHub) | [config-files.md](config-files.md) |
| `.env.example` | Fake placeholders showing what `.env` looks like (safe to commit) | [config-files.md](config-files.md) |
| `render.yaml` | The Render Blueprint: how the live site is built and started | [config-files.md](config-files.md) |
| `.gitignore` | Tells Git what never to save | [config-files.md](config-files.md) |
| `requirements.txt` | The list of Python packages | [config-files.md](config-files.md) |
| `pytest.ini` | Settings for the tests | [config-files.md](config-files.md) |
| `CLAUDE.md` | The rulebook Claude Code reads every session | [config-files.md](config-files.md) |
| `README.md` | The front page of the GitHub repo | [config-files.md](config-files.md) |
| `db.py` | Connects to the database and defines the tables | [db.md](db.md) |
| `ingest.py` | Loads the 5,000 drug products | [ingest.md](ingest.md) |
| `ingest_recalls.py` | Loads the ~10,000 recalls | [ingest_recalls.md](ingest_recalls.md) |
| `main.py` | **The API**: every endpoint | [main.md](main.md) |
| `schemas.py` | The shape of every API response | [schemas.md](schemas.md) |
| `analytics.py` | Monthly trends, reason categories, spike detection | [analytics.md](analytics.md) |
| `insights.py` | AI-written spike summaries, fact-checked, with a template fallback | [insights.md](insights.md) |
| `reports.py` | CSV downloads of recalls and spikes, safe for Excel | [reports.md](reports.md) |
| `checks.sql` / `run_checks.py` | Data quality checks | [checks.md](checks.md) |
| `tests/` | Automated tests | [tests.md](tests.md) |
| `postman/insightscope.postman_collection.json` | The Postman collection | [postman.md](postman.md) |
| `frontend/` | The React dashboard | [frontend.md](frontend.md) |
| `frontend/.npmrc`, `package.json` | npm packages and install settings | [frontend.md](frontend.md) |

## If you were rebuilding the API from scratch

The minimum set is `.env` → `db.py` → `schemas.py` → `main.py`, plus `requirements.txt`. The loaders fill the database; `analytics.py` adds the analytics endpoints; `insights.py` adds the AI summaries; `frontend/` adds the dashboard; everything else checks or tests.
