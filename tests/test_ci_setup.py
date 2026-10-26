"""Tests for the CI setup: the safety check on the seed script, the made-up data, and the workflow file.

None of these need a database. The seed script is only run with a made-up address that fails the safety check, so it
stops before it could connect anywhere.

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

import seed_ci_data
from seed_ci_data import SeedRefused, build_data, ensure_ci_database

ROOT = Path(__file__).resolve().parent.parent
SEED_SCRIPT = ROOT / "tests" / "seed_ci_data.py"
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


# --- the safety check: the seed deletes rows, so it must only ever run on insightscope_ci ---

@pytest.mark.parametrize("url", [
    "postgresql://user:pw@localhost:5432/insightscope",                       # the real local database
    "postgresql://user:pw@ep-example.neon.tech/insightscope?sslmode=require",   # a Neon-style address
    "postgresql://user:pw@localhost:5432/insightscope_ci2",
    "postgresql://user:pw@localhost:5432/insightscope_ci_backup",
    "postgresql://user:pw@localhost:5432/INSIGHTSCOPE_CI",                    # capitals count
    "postgresql://user:pw@localhost:5432/postgres",
    "postgresql://user:pw@localhost:5432/",                                   # no database name at all
    "postgresql://user:pw@localhost:5432",
    "not an address",
    "",
    "   ",
    None,
])
def test_any_database_that_is_not_exactly_insightscope_ci_is_refused(url):
    with pytest.raises(SeedRefused):
        ensure_ci_database(url)


@pytest.mark.parametrize("url", [
    "postgresql://postgres:pw@localhost:5432/insightscope_ci",
    "postgresql+psycopg://postgres:pw@localhost:5432/insightscope_ci",
    "postgres://postgres:pw@db.example.test:5432/insightscope_ci?sslmode=disable",
    "  postgresql://postgres:pw@localhost:5432/insightscope_ci  ",
])
def test_the_ci_database_is_accepted(url):
    ensure_ci_database(url)


def test_a_refusal_never_repeats_the_address_or_password():
    with pytest.raises(SeedRefused) as refused:
        ensure_ci_database("postgresql://someone:secret-pass@db.example.test:5432/insightscope")
    for private in ("secret-pass", "someone", "db.example.test"):
        assert private not in str(refused.value)


def run_script(extra_env, remove=()):
    environment = {key: value for key, value in os.environ.items() if key not in remove}
    environment.update(extra_env)
    return subprocess.run([sys.executable, str(SEED_SCRIPT)], env=environment, cwd=ROOT, capture_output=True, text=True, timeout=60)


def test_running_the_script_against_another_database_exits_with_an_error_and_prints_no_secret():
    result = run_script({"DATABASE_URL": "postgresql://someone:secret-pass@db.example.test:5432/insightscope"})
    assert result.returncode != 0
    assert "Refusing to run" in result.stderr
    assert "secret-pass" not in result.stdout + result.stderr


def test_running_the_script_without_database_url_does_not_fall_back_to_the_dotenv_file():
    # The script stops at once, so a .env file (which points at a real database) is never even loaded.
    result = run_script({}, remove=["DATABASE_URL"])
    assert result.returncode != 0
    assert "DATABASE_URL is not set" in result.stderr


# --- the made-up data ---

def test_the_data_is_the_same_every_time():
    assert build_data() == build_data()


def test_every_report_date_is_a_wednesday_and_the_history_is_long_enough_to_score_spikes():
    dates = {r["report_date"] for r in build_data()["recalls"]}
    assert {d.weekday() for d in dates} == {2}                                  # 2 = Wednesday
    assert (max(dates).year - min(dates).year) * 12 + max(dates).month - min(dates).month >= 14
    assert min(dates).day <= 7                                                    # so the oldest month counts as complete


def test_the_data_has_what_the_tests_look_for():
    data = build_data()
    recalls = data["recalls"]
    numbers = [r["recall_number"] for r in recalls]
    assert len(numbers) == len(set(numbers)) and "N/A" in numbers
    assert any(r["state"] is None for r in recalls) and any(r["voluntary_mandated"] is None for r in recalls)
    assert any(r["product_description"].startswith("+") for r in recalls)
    assert any("," in r["recalling_firm"] and '"' in r["reason_for_recall"] for r in recalls)
    assert any("%" in r["recalling_firm"] for r in recalls) and any("_" in r["recalling_firm"] for r in recalls)
    popular = [n for n in data["recall_ndcs"] if n["product_ndc"] == seed_ci_data.POPULAR_NDC]
    assert len(popular) > 10
    assert all(n["recall_number"] in set(numbers) for n in data["recall_ndcs"])
    assert "99999-999" not in {n["product_ndc"] for n in data["recall_ndcs"]}   # the Postman "no recalls" NDC stays empty
    versions = {}
    for p in data["products"]:
        versions.setdefault(p["product_ndc"], []).append(p["marketing_start_date"])
    assert sum(1 for dates in versions.values() if len(dates) > 1) >= 3
    assert len(versions) >= 6 and len({p["labeler_name"] for p in data["products"] if p["labeler_name"]}) >= 5


def test_the_file_says_at_the_top_that_the_data_is_made_up():
    assert "MADE-UP DATA FOR CI ONLY" in SEED_SCRIPT.read_text(encoding="utf-8").splitlines()[0]


# --- the workflow file ---

@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def render_env():
    service = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))["services"][0]
    return {item["key"]: item.get("value") for item in service["envVars"]}


def steps_using(workflow, action):
    return [s for job in workflow["jobs"].values() for s in job["steps"] if s.get("uses", "").startswith(action + "@")]


def test_it_runs_on_push_and_pull_request_to_main(workflow):
    triggers = workflow.get("on", workflow.get(True))                       # YAML reads a bare `on` as True
    assert triggers["push"]["branches"] == ["main"] and triggers["pull_request"]["branches"] == ["main"]


def test_it_only_has_read_access_cancels_older_runs_and_has_timeouts(workflow):
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is True
    assert set(workflow["jobs"]) == {"frontend", "backend"}                  # two jobs, which run in parallel
    assert all("needs" not in job and job["timeout-minutes"] == 10 for job in workflow["jobs"].values())


def test_it_uses_the_same_python_and_node_versions_as_render(workflow, render_env):
    assert [str(s["with"]["python-version"]) for s in steps_using(workflow, "actions/setup-python")] == [render_env["PYTHON_VERSION"]]
    assert {str(s["with"]["node-version"]) for s in steps_using(workflow, "actions/setup-node")} == {str(render_env["NODE_VERSION"])}


def test_it_needs_no_secrets_and_no_ai_token(workflow):
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text and "HF_TOKEN" not in text and "neon" not in text.lower()


def test_it_points_at_the_throwaway_database_the_seed_accepts(workflow):
    backend = workflow["jobs"]["backend"]
    assert backend["services"]["postgres"]["image"].startswith("postgres:18")
    ensure_ci_database(backend["env"]["DATABASE_URL"])                        # the same check the seed script uses
    assert backend["services"]["postgres"]["env"]["POSTGRES_DB"] == seed_ci_data.CI_DATABASE_NAME
    assert "localhost" in backend["env"]["DATABASE_URL"]


def test_it_seeds_before_the_tests_and_builds_the_dashboard_first(workflow):
    runs = [s.get("run", "") for s in workflow["jobs"]["backend"]["steps"]]
    seed = next(i for i, r in enumerate(runs) if "tests/seed_ci_data.py" in r)
    build = next(i for i, r in enumerate(runs) if "npm run build" in r)
    pytest_run = next(i for i, r in enumerate(runs) if "pytest" in r)
    assert build < pytest_run and seed < pytest_run


def test_every_action_is_pinned_to_a_full_commit(workflow):
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                _, _, ref = step["uses"].partition("@")
                assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), step["uses"]


def test_the_seed_script_is_not_imported_by_the_app():
    for name in ("main.py", "db.py", "ingest.py", "ingest_recalls.py"):
        assert "seed_ci_data" not in (ROOT / name).read_text(encoding="utf-8")
