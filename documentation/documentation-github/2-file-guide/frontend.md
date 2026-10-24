# `frontend/`: the dashboard

**Job:** the React page that shows the analytics. In development Vite serves it. In production `npm run build` turns it into plain files in `frontend/dist/`, and `main.py` serves those at `/`.

> The snippets below are simplified or shortened. Open the files in VS Code for the exact code.

## The folder

```
frontend/
├── package.json, package-lock.json   the npm packages, pinned exactly (committed)
├── .npmrc                            install settings (committed)
├── vite.config.js                    dev proxy + test settings
├── index.html                        the page shell React fills in
├── node_modules/                     installed packages (NOT committed)
├── dist/                             build output (NOT committed)
└── src/
    ├── main.jsx         starts the app
    ├── App.jsx          lays out the page and loads the data
    ├── api.js           fetches data, turns failures into plain words
    ├── hooks.js         loading logic and the status check
    ├── format.js        number and date formatting
    ├── index.css        every colour, for light and dark mode
    ├── components/      one file per section
    └── __tests__/       dashboard tests + a fake API helper
```

## `package.json` and `.npmrc`

```json
"scripts": { "dev": "vite", "build": "vite build", "test": "vitest run" }
```

So `npm run dev`, `npm run build` and `npm test` are shortcuts for these commands. Versions are written exactly (`"recharts": "3.10.1"`, no `^`), so everyone installs the same thing.

```
ignore-scripts=true
save-exact=true
```

`ignore-scripts` stops packages from running their own code during install, which is a common way malicious packages attack. `save-exact` keeps future installs pinned.

## `vite.config.js`: the dev proxy

```js
const API = 'http://127.0.0.1:8000'
const API_PATHS = ['health', 'products', 'recalls', 'analytics', 'insights', 'search', 'stats', 'docs', 'openapi.json']
server: { proxy: Object.fromEntries(API_PATHS.map((path) => [`/${path}`, { target: API }])) }
```

In dev mode the browser asks Vite (port 5173) for `/recalls`, and Vite forwards it to FastAPI (port 8000). The browser only talks to one address, so there's no CORS setup. **If you add a new top-level API path, add it to this list**, or the dev page will 404 on it.

## `api.js`: three kinds of failure

```js
// kind 'network' : no answer at all (server stopped, no connection, or too slow)
// kind 'http'    : the API answered with an error status (422, 503, ...)
```

`getJson(path)` fetches with a 25-second timeout and throws an `ApiError` saying which kind. `explainError()` turns it into a title, a message and a hint:

| Error | Title shown |
| --- | --- |
| `network` | "Can't reach the API" |
| HTTP 503 | "The API can't reach its database" |
| Other HTTP (e.g. 422) | "The API returned an error (HTTP 422)" plus the API's own message |

## `hooks.js`: loading data and the status light

- `useApi(path)` loads one endpoint and returns `{ data, error, loading, reload }`. While it reloads, the old data stays on screen, so the page doesn't flash.
- `useHealth()` calls `/health` every 15 seconds and reports `ok`, `db-down` (503) or `api-down` (no answer).

## `App.jsx`: the page

Loads the data with `useApi`, shows an outage banner when the health check fails, and lays out the sections. When health goes from down back to `ok`, every section that failed reloads by itself.

## The components

| File | Job |
| --- | --- |
| `StatusIndicator.jsx` | The live light: icon, colour **and** words for each state |
| `SummaryTiles.jsx` | The four headline tiles |
| `MonthlyChart.jsx` | Stacked monthly bars by class, spike diamonds, a text summary and a table view |
| `SpikeCards.jsx` | One card per spike with its summary and an AI/Template badge |
| `ReasonCategories.jsx` | Reason bar chart with a date picker |
| `NdcLookup.jsx` | NDC lookup with four outcomes: found, none, invalid, error |
| `States.jsx` | Shared loading and error boxes (with Try again) |
| `icons.jsx` | Small SVG icons |

**Accessibility touches:** a "Skip to the dashboard" link, chart text summaries and table views, `role="status"` / `role="alert"` so screen readers announce changes, and states that never rely on colour alone.

## `index.css`: colours

Every colour is a variable (like `--good` or `--critical`), defined once for light mode and once for dark mode. To restyle the page, change them here.

## Tests (`src/__tests__/`)

38 tests run in a fake browser (jsdom) against a **fake API**, so they need no server. They check things like: the badge says AI or Template correctly, a 422 shows the API's message, "no recalls" never looks like a found result, and an unreachable API is never reported as a database problem.

```powershell
npm test
```

(Run it inside `frontend`.)

## Why it matters

It turns the API into something a non-technical person can use, and every failure says what's wrong and what to check. That's the same job as a good support ticket reply.
