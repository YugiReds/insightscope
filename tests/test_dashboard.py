"""Tests that FastAPI serves the built dashboard without disturbing the API.

Most of these use a tiny fake "built" dashboard in a temporary folder, so they pass on a fresh clone with no npm.
The last group runs against the real build in frontend/dist and is skipped until `npm run build` has been run.

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main

INDEX_HTML = '<!doctype html><html><body><div id="root"></div><!-- dashboard-marker --></body></html>'


@pytest.fixture
def built_dashboard(tmp_path):
    """A pretend `npm run build` output: index.html plus one file in assets/."""
    (tmp_path / "index.html").write_text(INDEX_HTML)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('dashboard')")
    return tmp_path


@pytest.fixture
def small_app(built_dashboard):
    application = FastAPI()

    @application.get("/ping")
    def ping():
        return {"pong": True}

    main.mount_dashboard(application, built_dashboard)   # mounted last, like in main.py
    return TestClient(application)


# --- the mount itself ---

def test_the_built_index_page_is_served_at_the_root(small_app):
    response = small_app.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "dashboard-marker" in response.text


def test_built_assets_are_served(small_app):
    response = small_app.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log('dashboard')" in response.text


def test_api_routes_and_docs_still_win_over_the_dashboard(small_app):
    assert small_app.get("/ping").json() == {"pong": True}
    docs = small_app.get("/docs")
    assert docs.status_code == 200 and "swagger" in docs.text.lower()
    assert "/ping" in small_app.get("/openapi.json").json()["paths"]


def test_an_unknown_path_is_a_404_not_the_dashboard(small_app):
    assert small_app.get("/no-such-page").status_code == 404


def test_a_route_added_after_the_mount_is_never_reached(built_dashboard):
    # This is WHY the mount must be the last thing in main.py.
    application = FastAPI()
    main.mount_dashboard(application, built_dashboard)

    @application.get("/late")
    def late():
        return {"reached": True}

    assert TestClient(application).get("/late").status_code == 404


def test_the_dashboard_folder_is_where_npm_run_build_puts_it():
    assert main.DASHBOARD_DIR == Path(main.__file__).parent / "frontend" / "dist"


# --- the real build (skipped until `npm run build` has been run in frontend/) ---

REAL_INDEX = main.DASHBOARD_DIR / "index.html"
needs_build = pytest.mark.skipif(not REAL_INDEX.exists(), reason="the dashboard is not built: run `npm run build` in frontend/")


@needs_build
def test_the_real_app_serves_the_built_index_page():
    response = TestClient(main.app).get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == REAL_INDEX.read_text(encoding="utf-8")
    assert '<div id="root">' in response.text


@needs_build
def test_the_real_app_still_serves_docs_and_the_api():
    client = TestClient(main.app)
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/health").json() == {"status": "ok", "database": "reachable"}
    # The API's own 404 message (not the dashboard's) for a recall number with slashes: the :path route still wins.
    unknown = client.get("/recalls/A/B/C")
    assert unknown.status_code == 404 and unknown.json()["detail"] == "No recall found with recall number A/B/C"


@needs_build
def test_every_file_the_index_page_asks_for_exists():
    client = TestClient(main.app)
    wanted = re.findall(r'(?:src|href)="(/assets/[^"]+)"', REAL_INDEX.read_text(encoding="utf-8"))
    assert wanted, "index.html does not reference any built assets"
    for path in wanted:
        assert client.get(path).status_code == 200, path


@needs_build
def test_the_dashboard_is_the_last_route_in_the_real_app():
    assert main.app.routes[-1].name == "dashboard"
