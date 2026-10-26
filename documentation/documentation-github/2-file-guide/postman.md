# `postman/insightscope.postman_collection.json`: the Postman collection

**Job:** a saved set of 31 API requests with 78 tests, that you can run in Postman with one click, against your PC or the live site.

**This JSON file is the source of truth.** Postman also writes its own YAML copies under `postman/collections/` and `postman/globals/`; those are no longer tracked by Git (they're in `.gitignore`).

## Structure

```
InsightScope API
├── Happy path   (requests that should succeed)
└── Error cases  (requests that should fail on purpose: 404, 422)
```

One collection variable: `baseUrl = http://127.0.0.1:8000`. Every request is written as `{{baseUrl}}/...`, so pointing the collection at the live server means changing one value: set `baseUrl` to `https://insightscope.onrender.com` (open the site first if it's been idle, so it's awake).

## Running it against the live site

1. Open https://insightscope.onrender.com first, so the free server is awake.
2. Click the collection → **Variables** → set `baseUrl`'s **Current value** to `https://insightscope.onrender.com` → **Ctrl+S**.
3. **Run**. Then set it back to `http://127.0.0.1:8000`.

Change only the **Current value**. The **Initial value** is what's saved in the JSON file, so it stays local.

Results on October 25, 2026: **78 of 78 passed** on both, about 16 ms per request locally and 92 ms live.

## IDs come from the data, not the collection

The first live run failed on "Get product by NDC (76961-101)": that NDC didn't exist on Neon, because `ingest.py` downloads a fresh openFDA sample each time, so the local and live databases hold different products. The request had **hard-coded** test data.

Now earlier requests save real values as collection variables, and later requests use them:

| Saved by | Variable | Used by |
| --- | --- | --- |
| List products (limit 5) | `sampleNdc` | Get product by NDC (from the list) |
| List products (limit 5) | `sampleLabeler` → `sampleLabelerWord` (its longest word, 3+ characters) | Filter products by labeler |
| List recalls (limit 5) | `sampleRecallNumber` | Get recall by number (from the list) |
| A pre-request script that opens up to 40 recent recalls until one lists NDCs | `sampleRecallNdc` | Recalls for an NDC (found in the recalls) |

```javascript
// in "List products (limit 5)" tests
pm.collectionVariables.set("sampleNdc", pm.response.json().items[0].product_ndc);
```

**The N/A recall request** now passes on a 200 for recall `N/A`, **or** on our own 404 message (`No recall found with recall number N/A`). It fails on FastAPI's generic `{"detail":"Not Found"}`, which is the routing bug it exists to catch. So it proves the routing on any data load.

**Still data-dependent, on purpose:** the `TABLET` filter, the 2025 Class I CSV and "at least one spike". With ~10,000 recalls since 2018 these always have data; if one fails, something really is wrong.

Error cases keep **fake** IDs (`0000-0000`, `X-9999-9999`, `A/B/C`, `abc`), because they must never exist.

## A test script

```javascript
pm.test("Status code is 422", function () {
    pm.response.to.have.status(422);
});
pm.test("error body has a detail list", function () {
    pm.expect(pm.response.json().detail).to.be.an("array");
});
```

| Piece | Meaning |
| --- | --- |
| `pm.test("name", fn)` | One checklist line; shows PASS or FAIL |
| `pm.response.to.have.status(422)` | Did the API answer 422? |
| `pm.response.json()` | The response body as data |
| `pm.expect(x).to...` | States what must be true |

## Requests by group

| Group | Count | Examples |
| --- | --- | --- |
| Happy path | Database health check (`/health/db`), products (NDC and labeler taken from the list), search, labelers, recalls, N/A recall, analytics, AI spike insights, recalls CSV, spikes CSV | `GET /products/76961-101`, `GET /analytics/recalls/spikes` |
| Error cases | Unknown NDC 404, short search 422, limit 500 422, unknown recall 404, malformed NDC 422, backwards date range 422, invalid date 422, recalls CSV backwards range 422, recalls CSV invalid date 422 | `GET /products/0000-0000` |

## How to run

1. Start the API: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`
2. Postman → **Import** → this JSON file (delete the old copy first if the file changed).
3. Collection → **Run** → **Start run**.

Red 404 and 422 badges with green PASS checks under them are correct.
