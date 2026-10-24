"""Tests for being deploy-ready (Render web service + Neon Postgres).

Covers: the DATABASE_URL rewriting, the engine's settings, which setting wins (shell or .env), the health endpoints, the
tables being created on an empty database, and the deployment files (render.yaml, requirements.txt, .env.example).

NOTHING here reads the contents of .env. The only fake values used are obviously fake (db.example.test, secret-pass).

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

import db
import main

ROOT = pathlib.Path(__file__).resolve().parent.parent
client = TestClient(main.app)
NEON_STYLE = "ep-cool-meadow-123456.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


# ---------------------------------------------------------------------------------------------------------
# DATABASE_URL: normalizing the scheme
# ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_all_three_ways_of_writing_the_address_become_the_psycopg_form(scheme):
    assert db.normalize_database_url(f"{scheme}user:secret-pass@{NEON_STYLE}") == f"postgresql+psycopg://user:secret-pass@{NEON_STYLE}"


def test_everything_after_the_scheme_is_kept_exactly_including_every_query_parameter():
    url = f"postgres://neondb_owner:p%40ss%3Aword@{NEON_STYLE}&application_name=insightscope"
    normalized = db.normalize_database_url(url)
    assert normalized.split("://", 1)[1] == url.split("://", 1)[1]                       # nothing after the scheme changed
    parsed = make_url(normalized)                                                          # and SQLAlchemy reads it the way we expect
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.host == "ep-cool-meadow-123456.us-east-2.aws.neon.tech"
    assert parsed.database == "neondb"
    assert parsed.password == "p@ss:word"
    assert dict(parsed.query) == {"sslmode": "require", "channel_binding": "require", "application_name": "insightscope"}


def test_only_the_leading_scheme_is_replaced():
    # A password or database name that happens to contain "postgres://" must not be touched.
    url = "postgres://user:postgres://trick@localhost/db"
    assert db.normalize_database_url(url) == "postgresql+psycopg://user:postgres://trick@localhost/db"


def test_surrounding_whitespace_is_ignored():
    assert db.normalize_database_url("  postgresql://u:p@localhost/db\n") == "postgresql+psycopg://u:p@localhost/db"


@pytest.mark.parametrize("bad", ["mysql://u:secret-pass@host/db", "postgresql+psycopg2://u:secret-pass@host/db", "u:secret-pass@host/db", "", None])
def test_a_wrong_scheme_is_rejected_and_the_error_never_repeats_the_password(bad):
    with pytest.raises(ValueError) as caught:
        db.normalize_database_url(bad)
    assert "secret-pass" not in str(caught.value)
    assert "postgres" in str(caught.value)


def test_the_error_names_the_scheme_that_was_found():
    with pytest.raises(ValueError, match=r"starts with mysql://"):
        db.normalize_database_url("mysql://u:p@host/db")


# ---------------------------------------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------------------------------------

def test_the_engine_survives_neon_dropping_idle_connections(monkeypatch):
    seen = {}

    def fake_create_engine(url, **kwargs):
        seen["url"], seen["kwargs"] = url, kwargs
        return "fake engine"

    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    monkeypatch.setenv("DATABASE_URL", f"postgres://user:secret-pass@{NEON_STYLE}")
    assert db.get_engine() == "fake engine"
    assert seen["url"] == f"postgresql+psycopg://user:secret-pass@{NEON_STYLE}"          # normalized, query kept
    assert seen["kwargs"]["pool_pre_ping"] is True                                          # test a connection before using it
    assert seen["kwargs"]["pool_recycle"] == 300                                            # replace connections older than 5 minutes
    assert seen["kwargs"]["connect_args"]["connect_timeout"] == 10                          # never wait forever for an unreachable database


def test_a_real_engine_object_can_be_made_from_a_neon_style_address_without_connecting(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:secret-pass@{NEON_STYLE}")
    engine = db.get_engine()                      # nothing connects until the first query
    assert engine.dialect.driver == "psycopg"
    assert engine.pool._pre_ping is True and engine.pool._recycle == 300
    assert dict(engine.url.query) == {"sslmode": "require", "channel_binding": "require"}


def test_a_missing_database_url_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        db.get_engine()


# ---------------------------------------------------------------------------------------------------------
# Which setting wins: the shell's, or .env's. (Each case runs in a fresh Python process, because the choice is
# made when db.py is first imported. Only True/False is ever printed, never a value.)
# ---------------------------------------------------------------------------------------------------------

def run_python(code, environment):
    result = subprocess.run([sys.executable, "-c", code], env=environment, cwd=ROOT, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, "the subprocess crashed"        # stderr is deliberately not shown
    return result.stdout.strip()


def test_a_database_url_set_in_the_environment_wins_over_the_dotenv_file():
    environment = {**os.environ, "DATABASE_URL": "postgresql://someone:secret-pass@db.example.test:5432/other?sslmode=require"}
    answer = run_python("import db; u = db.get_engine().url; print(u.host == 'db.example.test' and u.database == 'other')", environment)
    assert answer == "True"


@pytest.mark.skipif(not (ROOT / ".env").exists(), reason="no .env file here (for example on CI)")
def test_without_one_in_the_environment_the_dotenv_file_is_used_as_the_fallback():
    environment = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
    answer = run_python("import db, os; db.get_engine(); print(bool(os.environ.get('DATABASE_URL')))", environment)
    assert answer == "True"


# ---------------------------------------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------------------------------------

class ExplodingEngine:
    """An engine that fails the test if anything uses it."""
    def connect(self):
        raise AssertionError("/health touched the database")

    begin = connect


def test_health_never_touches_the_database(monkeypatch):
    monkeypatch.setattr(main, "engine", ExplodingEngine())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_runs_a_query_and_reports_the_result():
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}


def test_health_db_is_503_when_the_connection_fails(monkeypatch):
    class Broken:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("could not connect"))
    monkeypatch.setattr(main, "engine", Broken())
    response = client.get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_both_health_routes_are_registered_before_the_dashboard_mount():
    paths = [getattr(route, "path", "") for route in main.app.routes]
    assert "/health" in paths and "/health/db" in paths
    if main.app.routes[-1].name == "dashboard":
        assert main.app.routes[-1].path == ""                      # the mount is the very last route
        assert paths.index("/health") < len(paths) - 1 and paths.index("/health/db") < len(paths) - 1


# ---------------------------------------------------------------------------------------------------------
# Tables are created on an EMPTY database. A scratch schema stands in for a brand-new database, so the real tables
# are never touched. (A new Neon database has no tables at all until something creates them.)
# ---------------------------------------------------------------------------------------------------------

EXPECTED_TABLES = {"products", "active_ingredients", "packages", "recalls", "recall_ndcs", "insight_cache"}


@pytest.fixture
def empty_database():
    real = db.get_engine()
    schema = f"scratch_{uuid.uuid4().hex[:10]}"
    with real.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scratch = create_engine(real.url, connect_args={"options": f"-csearch_path={schema}"})
    yield scratch, schema
    scratch.dispose()
    with real.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    real.dispose()


def tables_in(engine, schema):
    return set(inspect(engine).get_table_names(schema=schema))


def test_startup_creates_every_table_including_insight_cache_on_an_empty_database(empty_database):
    scratch, schema = empty_database
    assert tables_in(scratch, schema) == set()                      # really empty to begin with
    main.initialize_database(scratch)
    assert tables_in(scratch, schema) == EXPECTED_TABLES


def test_running_it_again_changes_nothing_and_keeps_existing_data(empty_database):
    scratch, schema = empty_database
    main.initialize_database(scratch)
    # One row in a table from EACH of the three groups startup creates (the product tables, the recall tables, and
    # insight_cache), so dropping any one group would be noticed.
    with scratch.begin() as conn:
        conn.execute(text("INSERT INTO products (product_id) VALUES ('KEEP-PRODUCT')"))
        conn.execute(text("INSERT INTO active_ingredients (product_id, name) VALUES ('KEEP-PRODUCT', 'KEEP-INGREDIENT')"))
        conn.execute(text("INSERT INTO recalls (recall_number) VALUES ('KEEP-ME')"))
        conn.execute(text("INSERT INTO recall_ndcs (recall_number, product_ndc) VALUES ('KEEP-ME', '12345-678')"))
        conn.execute(text("INSERT INTO insight_cache (cache_key, summary, model) VALUES ('k', 's', 'm')"))
    main.initialize_database(scratch)                               # what happens on every restart
    with scratch.connect() as conn:
        for table in ("products", "active_ingredients", "recalls", "recall_ndcs", "insight_cache"):
            assert conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 1, f"{table} lost its row"
    assert tables_in(scratch, schema) == EXPECTED_TABLES


def test_the_real_database_is_not_touched_by_the_scratch_tests(empty_database):
    scratch, schema = empty_database
    main.initialize_database(scratch)
    with main.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM recalls")).scalar() > 1000     # still the real data


def test_the_app_still_starts_and_answers_health_when_the_database_cannot_be_reached(monkeypatch):
    attempts, pauses = [], []

    def always_fails(target=None):
        attempts.append(1)
        raise OperationalError("CREATE TABLE", {}, Exception("could not connect"))

    monkeypatch.setattr(main, "initialize_database", always_fails)
    assert main.prepare_database(attempts=3, pause=pauses.append) is False       # gives up, but does NOT raise
    assert len(attempts) == 3 and pauses == [3, 6]                                 # waits a little longer each time, not after the last try


def test_preparing_the_database_retries_until_it_works(monkeypatch):
    calls = []

    def fails_twice(target=None):
        calls.append(1)
        if len(calls) < 3:
            raise OperationalError("CREATE TABLE", {}, Exception("neon is waking up"))

    monkeypatch.setattr(main, "initialize_database", fails_twice)
    assert main.prepare_database(attempts=5, pause=lambda seconds: None) is True
    assert len(calls) == 3


def test_starting_the_app_prepares_the_database_in_the_background_without_blocking_health(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow_prepare(*args, **kwargs):
        started.set()
        release.wait(10)                                            # pretend Neon takes a long time to wake

    monkeypatch.setattr(main, "prepare_database", slow_prepare)
    began = time.perf_counter()
    with TestClient(main.app) as live:                              # entering the block runs the app's startup
        assert time.perf_counter() - began < 5, "startup waited for the database instead of carrying on"
        assert started.wait(5), "startup did not begin preparing the database"
        assert not release.is_set()                                  # the preparation is STILL running...
        assert live.get("/health").json() == {"status": "ok"}       # ...and /health is answered anyway
        release.set()


# ---------------------------------------------------------------------------------------------------------
# The deployment files
# ---------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def blueprint():
    return yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def service(blueprint):
    assert len(blueprint["services"]) == 1, "one web service only"
    return blueprint["services"][0]


def env_of(service):
    return {item["key"]: item for item in service["envVars"]}


def test_render_blueprint_describes_one_free_python_web_service_in_virginia(service):
    assert service["type"] == "web"
    assert service["runtime"] == "python"
    assert service["region"] == "virginia"
    assert service["plan"] == "free"


def test_render_builds_the_python_packages_and_the_dashboard_and_starts_uvicorn(service):
    assert service["buildCommand"] == "pip install -r requirements.txt && cd frontend && npm ci --include=dev && npm run build"
    start = service["startCommand"]
    assert start == "uvicorn main:app --host 0.0.0.0 --port $PORT"
    assert hasattr(main, "app")                                     # "main:app" really exists
    assert (ROOT / "main.py").exists()                              # at the repo root, where the command runs


def test_render_health_check_uses_the_route_that_never_touches_the_database(service):
    assert service["healthCheckPath"] == "/health"


def test_render_secrets_are_not_stored_in_the_file(service):
    env = env_of(service)
    for secret in ("DATABASE_URL", "HF_TOKEN"):
        assert env[secret].get("sync") is False                    # Render asks for the value; it is never in git
        assert "value" not in env[secret]


def test_render_versions_match_this_machine_and_satisfy_the_packages(service):
    env = env_of(service)
    assert env["HF_MODEL"]["value"] == "meta-llama/Llama-3.1-8B-Instruct"
    assert env["PYTHON_VERSION"]["value"] == f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    node = tuple(int(part) for part in str(env["NODE_VERSION"]["value"]).split("."))
    assert len(node) == 3                                           # a full version, as Render documents
    assert node >= (24, 15, 0) or ((22, 22, 2) <= node < (23, 0, 0))   # the floor set by jsdom (the strictest dev package)
    assert node >= (22, 12, 0)                                      # Vite 8 and Vitest 5


def test_requirements_install_on_linux():
    names = {line.split("==")[0].lower() for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines() if "==" in line}
    assert "uvicorn" in names
    assert {"psycopg", "psycopg-binary"} <= names                  # psycopg[binary]: the driver and its bundled libpq
    windows_only = {"pywin32", "pywin32-ctypes", "pypiwin32", "win32-setctime", "pywinpty", "wmi", "comtypes", "winshell"}
    assert not (names & windows_only)


def test_the_example_env_file_has_only_fake_values_in_neon_style():
    text_ = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in text_.splitlines() if "=" in line and not line.lstrip().startswith("#")}
    url = lines["DATABASE_URL"]
    assert "sslmode=require" in url and "neon.tech" in url
    assert "YOUR_PASSWORD" in url and "example" in url             # a placeholder, not a real credential
    assert lines["HF_TOKEN"].startswith("hf_your_token")           # also a placeholder
    db.normalize_database_url(url)                                  # and a form the app accepts


def test_dotenv_is_ignored_by_git_but_the_example_is_not():
    def ignored(name):
        return subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT).returncode == 0
    assert ignored(".env")
    assert not ignored(".env.example")
