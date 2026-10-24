# `postman/insightscope.postman_collection.json`: the Postman collection

**Job:** a saved set of 25 API requests, each with a test script, that you can run in Postman with one click.

**This JSON file is the source of truth.** The YAML files Postman writes under `postman/collections/` are its own copies and can go out of sync.

## Structure

```
InsightScope API
├── Happy path   (requests that should succeed)
└── Error cases  (requests that should fail on purpose: 404, 422)
```

One collection variable: `baseUrl = http://127.0.0.1:8000`. Every request is written as `{{baseUrl}}/...`, so pointing the collection at a deployed server later means changing one value.

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
| Happy path | Products, search, labelers, recalls, N/A recall, analytics | `GET /products/76961-101`, `GET /analytics/recalls/spikes` |
| Error cases | Unknown NDC 404, short search 422, limit 500 422, unknown recall 404, malformed NDC 422, backwards date range 422, invalid date 422 | `GET /products/0000-0000` |

## How to run

1. Start the API: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`
2. Postman → **Import** → this JSON file (delete the old copy first if the file changed).
3. Collection → **Run** → **Start run**.

Red 404 and 422 badges with green PASS checks under them are correct.
