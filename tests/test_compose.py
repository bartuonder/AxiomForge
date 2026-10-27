from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
DOCKERFILE = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")


def test_every_part_of_the_system_is_a_service():
    assert set(COMPOSE["services"]) == {"redis", "postgres", "mlflow", "api", "worker", "frontend"}


def test_the_frontend_is_built_from_its_own_folder_and_waits_for_the_api():
    frontend = COMPOSE["services"]["frontend"]
    assert frontend["build"]["context"] == "./frontend" and frontend["depends_on"] == ["api"]
    assert (ROOT / "frontend" / "Dockerfile").exists()


def test_the_console_is_served_on_port_3000_which_the_api_allows():
    assert COMPOSE["services"]["frontend"]["ports"] == ["3000:3000"]
    from app.main import app

    origins = next(layer.kwargs["allow_origins"] for layer in app.user_middleware if "allow_origins" in layer.kwargs)
    assert "http://localhost:3000" in origins


def test_the_address_of_the_api_and_the_key_are_build_arguments():
    arguments = COMPOSE["services"]["frontend"]["build"]["args"]
    assert arguments["NEXT_PUBLIC_API_URL"] == "${NEXT_PUBLIC_API_URL:-http://localhost:8000}"
    assert arguments["NEXT_PUBLIC_API_KEY"] == "${NEXT_PUBLIC_API_KEY:-}"
    assert "ARG NEXT_PUBLIC_API_URL" in DOCKERFILE and "ARG NEXT_PUBLIC_API_KEY" in DOCKERFILE


def test_the_image_builds_in_one_stage_and_runs_in_a_smaller_one():
    assert DOCKERFILE.count("FROM node:") == 2 and "AS build" in DOCKERFILE
    assert "RUN npm ci" in DOCKERFILE and "RUN npm run build" in DOCKERFILE
    assert DOCKERFILE.rstrip().endswith('CMD ["npm", "run", "start"]') and "EXPOSE 3000" in DOCKERFILE


def test_the_api_and_the_worker_keep_the_reports_volume_that_holds_the_usage_count():
    for name in ("api", "worker"):
        assert "reports:/srv/reports" in COMPOSE["services"][name]["volumes"]


def test_the_build_context_leaves_out_dependencies_and_builds():
    ignored = (ROOT / "frontend" / ".dockerignore").read_text(encoding="utf-8").split()
    assert {"node_modules", ".next"} <= set(ignored)


def test_the_build_context_leaves_out_the_browser_tests_and_their_output():
    ignored = set((ROOT / "frontend" / ".dockerignore").read_text(encoding="utf-8").split())
    assert {"e2e", "test-results", "playwright-report", "playwright.config.ts"} <= ignored
