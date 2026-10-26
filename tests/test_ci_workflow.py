import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def commands(job):
    return [step["run"] for step in WORKFLOW["jobs"][job]["steps"] if "run" in step]


def test_the_workflow_runs_on_pushes_to_main_and_on_pull_requests():
    triggers = WORKFLOW.get("on", WORKFLOW.get(True))
    assert triggers["push"]["branches"] == ["main"] and "pull_request" in triggers


def test_the_backend_job_installs_the_dev_requirements_and_runs_the_tests():
    assert commands("backend") == ["pip install -r requirements-dev.txt", "pytest -q"]
    assert (ROOT / "requirements-dev.txt").exists()


def test_the_backend_job_uses_the_python_of_the_docker_image():
    python = next(step["with"]["python-version"] for step in WORKFLOW["jobs"]["backend"]["steps"] if str(step.get("uses", "")).startswith("actions/setup-python"))
    assert f"python:{python}" in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_the_frontend_job_checks_types_lint_tests_and_the_build():
    assert commands("frontend") == ["npm ci", "npm test", "npx tsc --noEmit", "npm run lint", "npm run build"]
    assert WORKFLOW["jobs"]["frontend"]["defaults"]["run"]["working-directory"] == "frontend"


def test_every_npm_script_the_workflow_calls_exists():
    scripts = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))["scripts"]
    called = [command.split()[2] for command in commands("frontend") if command.startswith("npm run ")]
    assert all(name in scripts for name in called) and "test" in scripts


def test_the_lock_file_the_cache_key_names_exists():
    step = next(step for step in WORKFLOW["jobs"]["frontend"]["steps"] if str(step.get("uses", "")).startswith("actions/setup-node"))
    assert (ROOT / step["with"]["cache-dependency-path"]).exists()
