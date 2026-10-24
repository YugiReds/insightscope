# Step 7: Dashboard

**Result:** a one-page React dashboard that shows the recall trends, the six spikes with their AI summaries, the reason categories and an NDC lookup, with a live API status light. FastAPI serves the built page at `/`, so one server delivers both the dashboard and the API. Tests grew to 153 Python plus 38 dashboard tests.

**Date:** October 24, 2026 (early morning)

## The goal

Put steps 4 to 6 on one page that a non-technical reader understands at a glance, and make every failure say plainly what's wrong instead of leaving a blank page. The second part is the support-engineer angle.

## The stack

| Piece | Job |
| --- | --- |
| **React** | Builds the page out of components (one per section) |
| **Vite** | Dev server with instant reload, and `npm run build` makes the final files |
| **Tailwind CSS** | Styling with short class names, like `rounded-xl` or `p-4` |
| **Recharts** | The charts. Chosen over hand-written SVG and Chart.js because it draws real SVG elements, so screen readers and tests can reach the chart content. Stacked bars and markers are built in |
| **Vitest + Testing Library** | Dashboard tests that run in a fake browser (jsdom) |

12 npm packages, each pinned to an exact version (newest stable at least 14 days old). Install scripts are turned off in `frontend/.npmrc` to block a common supply-chain attack. `npm install` reported 0 vulnerabilities. No new Python package was needed, since FastAPI can already serve static files.

## What's on the page

| Section | What it shows | API it calls |
| --- | --- | --- |
| Status light (header) | API and database OK / database down / API unreachable, checked every 15 s | `/health` |
| Summary tiles | Total recalls, Class I recalls, spike count and similar headline numbers | `/recalls`, `/analytics/...` |
| Recalls per month | Stacked bars by class, diamonds on the six spike months, a text summary and a table view | `/analytics/recalls/monthly`, `/analytics/recalls/spikes` |
| Spike months | One card per spike with its summary and an **AI** or **Template** badge | `/insights/recalls/spikes` |
| Reason categories | Bar chart with a date picker | `/analytics/recalls/reasons` |
| NDC lookup | Recalls that list a drug code | `/products/{ndc}/recalls` |

## How the two run modes work

**While developing:** two servers. Vite (port 5173) serves the page, and its **proxy** forwards API paths such as `/health` and `/recalls` to FastAPI on port 8000. The browser only ever talks to one address, so CORS never comes into play.

**Production:** one server. `npm run build` writes the finished files to `frontend/dist/`, and `main.py` serves them at `/`. The mount at `/` matches every path, so **it must be the last thing in `main.py`**, or it would swallow the API routes (a test proves this).

## Errors that explain themselves

Every failure is sorted into one of three kinds, because each needs a different fix:

| What happened | What the dashboard says |
| --- | --- |
| No answer at all (server stopped, network down, timeout) | "Can't reach the API", red, with **Try again** |
| API answered 503 | "The API can't reach its database", amber |
| API answered 422 or another error | The API's own message, such as the reason an NDC is invalid |

The NDC lookup has four outcomes, each with its own icon, colour **and** wording, so they can't be confused:

| Outcome | Look | Meaning |
| --- | --- | --- |
| Found | Check icon, table of recalls | Recalls list this NDC |
| None | Blue info box | Valid NDC, no recall in our data lists it. This doesn't prove it was never recalled |
| Invalid | Amber warning | The API rejected it (422) |
| Error | Red, Try again | The API or database couldn't answer |

When the status light sees the API come back after an outage, every section that failed reloads by itself.

## Checked in a real browser

- One server delivered the page, its files, `/docs` and the API.
- All sections rendered, with diamonds on all six spike months and AI badges on the cards.
- Lookup: found, none and invalid each looked clearly different.
- **A real outage:** the server was stopped mid-session. The header switched to "API unreachable", a banner appeared, and the lookup offered Try again.
- The Vite proxy gave answers identical to calling the API directly.

**Not checked by eye yet:** light mode, narrow phone widths and keyboard use of the chart tooltip. Light mode passes the contrast checks, but nobody has looked at it.

## Testing the tests

| Deliberate break | Tests that failed |
| --- | --- |
| AI/Template badge swapped | 7 |
| A 422 shown as a generic error | 1 |
| "No recalls" shown as a found result | 2 |
| An unreachable API reported as a database problem | 1 |

`tests/test_dashboard.py` (10 Python tests): six use a tiny fake build, so they pass on a fresh clone without npm. Four check the real build and are **skipped** until `npm run build` has been run.

## Why `node_modules/` and `dist/` aren't in Git

Both are rebuilt from committed files. `node_modules/` (139 MB) comes back exactly from `package-lock.json` with `npm install`. `dist/` is build output, and committing it would put minified code in every diff and let it go stale. The trade-off is that whoever deploys must run `npm run build` (step 8).

## Problems hit and fixed

| Problem | Cause | Fix |
| --- | --- | --- |
| Every Python test failed to collect | `from pathlib import Path` replaced FastAPI's `Path` in `main.py` | `import pathlib` instead. `CLAUDE.md` now warns about it |
| Dev page didn't load on `127.0.0.1:5173` | On Windows the Vite dev server may only answer on `localhost` | Use `http://localhost:5173` |
| Windows clipboard panel froze while pasting the prompt | `TextInputHost` hung | Ended it in Task Manager |

## Known limits

- The built JavaScript is about 630 kB (185 kB compressed), mostly Recharts, with no lazy loading.
- A made-up URL like `/no-such-page` still returns FastAPI's JSON 404, not a dashboard page. This is on purpose, so the README's 404 technique still works.
- No screenshot yet. The README line for `screenshots/dashboard.png` is commented out until one is added.

## How to run it

Dev mode, terminal 1:

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

Dev mode, terminal 2 (run `npm install` once, then `npm run dev`):

```powershell
cd frontend
```

```powershell
npm install
```

```powershell
npm run dev
```

Then open http://localhost:5173.

Production (one server): from `frontend`, run `npm run build`, then `cd ..` and start uvicorn. Open http://127.0.0.1:8000/. Build **before** starting uvicorn, or restart it after the first build.

Tests: `npm test` in `frontend`, and `.\venv\Scripts\python.exe -m pytest` in the project folder.

## Git commits in this step

| Commit | Message |
| --- | --- |
| *(pending)* | Add React dashboard served by FastAPI, with tests |

## Interview lines

- "The dashboard tells apart three different failures: the API is down, the API is up but the database isn't, and the request itself is invalid. Each one gets its own wording, because each one points a support engineer at a different fix. I tested this by stopping the server mid-session."
- "In production FastAPI serves the built React files, so it's one deploy. I have a test that proves why the static mount has to be registered last."
