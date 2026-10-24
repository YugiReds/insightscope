# Step 2: The API

**Result:** a FastAPI service with five endpoints, request logging, clean error handling, 14 automated tests and a README.

**Date:** October 23, 2026 (morning)

## What an API is

An **API** is a set of web addresses that return data instead of web pages. Someone (or another program) sends a request like `GET /products/76961-101`, and the API answers with that drug's data as JSON.

## Starting it

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

- `main:app` means "in `main.py`, use the object called `app`."
- `--reload` restarts the server automatically when you save a code change.
- Then open **http://127.0.0.1:8000/docs** for an interactive page where you can try every endpoint.

## The endpoints built in this step

| Endpoint | What it does | Errors it handles |
| --- | --- | --- |
| `GET /health` | Checks the API can reach the database | 503 if the database is down |
| `GET /products` | Lists products with filters (labeler, dosage form) and pages (`limit` 1–100, `offset`) | 422 for a bad limit or offset |
| `GET /products/{ndc}` | One drug by NDC, with its ingredients and packages | 404 if the NDC doesn't exist |
| `GET /stats/labelers` | Companies ranked by number of drugs | 422 for a bad limit |
| `GET /search?q=` | Searches brand and generic names | 422 if the search is under 2 letters |

Every endpoint reads from a "latest" view that keeps only the newest label version per NDC. That's why the API reports **4,958** drugs while the raw table has 5,000 rows.

## Files added

| File | Job |
| --- | --- |
| `main.py` | The endpoints |
| `schemas.py` | The exact shape of each response (Pydantic models) |
| `tests/test_api.py` | 14 automated tests |
| `pytest.ini` | Settings for pytest |
| `README.md` | The front page of the GitHub repo |

## Support-engineer features

- **Request logging:** every request is logged with its path, status code and time in milliseconds.
- **Clean errors:** a database failure returns a short 503 ("Database unavailable") and writes the real error to the log, instead of crashing.
- **Troubleshooting section in the README:** six realistic user problems and how to work through each one.

## The tests

Run them with:

```powershell
.\venv\Scripts\python.exe -m pytest
```

They check that `/health` returns 503 when the database is down (by pointing the app at a fake database), that totals count each NDC once, that pages don't overlap, that bad requests get 422, that an unknown NDC gets 404, and that the newest label version is returned. The tests ask the database for the right answer instead of hard-coding drug names, so they keep working after a reload.

Two packages were added: **pytest** (runs tests) and **httpx2** (lets tests call the API without starting a server).

## Git commits in this step

| Commit | Message |
| --- | --- |
| `9f8e63c` | README for the API (exact message not recorded) |
| `b93bf09` | Use httpx2 for the test client; drop httpx |
| `3000f2b` | Ignore VS Code settings folder |

The API, schemas and tests were also committed in this step; their exact commit messages weren't recorded here.

## Where status codes come from (useful to remember)

| Code | Who decides | Example |
| --- | --- | --- |
| 200 | FastAPI, when the function returns normally | Any successful request |
| 404 | Your code: `if product is None: raise HTTPException(status_code=404, ...)` | `/products/0000-0000` |
| 422 | FastAPI, from rules in the function's inputs, e.g. `Query(25, ge=1, le=100)` | `/products?limit=500` |
| 503 | The `@app.exception_handler(SQLAlchemyError)` safety net | Database is down |

See [main.py in the file guide](../2-file-guide/main.md) for the exact lines.
