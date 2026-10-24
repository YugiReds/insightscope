# Step 3: Postman collection

**Result:** a saved Postman collection that tests every endpoint. It started at 9 requests (20 checks, all passing) and has grown to 25 requests as later steps added endpoints.

**Date:** October 23, 2026 (morning), updated through step 5

## What a Postman collection is

**Postman** is an app for sending requests to an API and seeing what comes back. A **collection** is a saved folder of those requests. Each request carries a small **test script** that checks the answer automatically and marks PASS or FAIL.

The Medidata job posting lists Postman by name, so this step closes that gap.

## The file

`postman/insightscope.postman_collection.json` is the source of truth. It uses one variable, `baseUrl = http://127.0.0.1:8000`, so every request is written as `{{baseUrl}}/products` and so on.

## How to run it

1. Start the API in its own terminal: `.\venv\Scripts\python.exe -m uvicorn main:app --reload`
2. In Postman: **Import** → pick `postman\insightscope.postman_collection.json`.
3. Click the collection → **Run** → **Start run**.
4. After the JSON changes, delete the old collection in Postman and import again.

## How a test script works

```javascript
pm.test("Status code is 404", function () {
    pm.response.to.have.status(404);
});
```

- `pm.test("name", ...)` is one line on the checklist.
- `pm.response.to.have.status(404)` asks "did the API answer 404?"
- `pm.response.json()` opens the response body to check fields.

The test only **checks** the status code. The API decides it (see [step 2](02-api.md)).

**Red 404 and 422 badges are correct, not failures.** Those requests are supposed to return errors, and the green PASS under each confirms it.

## Growth of the collection

| When | Requests | Result in Postman |
| --- | --- | --- |
| Step 3 | 9 (6 happy path, 3 error cases) | 20 of 20 checks passed |
| Step 4 (recalls) | 19 | 40 of 40 checks passed |
| Step 5 (analytics) | 25 | Run after re-importing |
| Step 6 (AI insights) | 26 | Run after re-importing |

## Postman quirks

- During setup Postman linked the project folder and created a `.postman/` folder, which was added to `.gitignore`.
- Postman also writes its own YAML copies under `postman/collections/` and `postman/globals/`. They go out of sync whenever the JSON changes, so in step 5 they were removed from Git (`git rm -r --cached postman/collections postman/globals`) and added to `.gitignore`.
- The committed `postman/globals/workspace.globals.yaml` was checked: it's empty, so nothing sensitive went public.
- An empty "New Collection" placeholder appeared once and is gone.

## Git commit in this step

| Commit | Message |
| --- | --- |
| `9aa675a` | Add Postman collection with tests for happy path and error cases |
