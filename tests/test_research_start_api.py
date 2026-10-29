import pytest
from fastapi.testclient import TestClient

import app.guard as guard
import app.main as main
import app.research.service as service
import app.research.session as session
import app.tasks as tasks
from tests.test_research_session import MODELS, config, make_runner, planted

BODY = {"models": MODELS}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())
    monkeypatch.setattr(guard, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("DAILY_START_LIMIT", raising=False)
    return tmp_path / "research"


@pytest.fixture
def client(monkeypatch):
    queued = []
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: queued.append((task, args)))
    test_client = TestClient(main.app)
    test_client.queued = queued
    return test_client


class TestStart:
    def test_it_queues_a_session_and_the_task(self, client):
        response = client.post("/start_research_session", json=BODY)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued" and body["session_id"].startswith("r-")
        assert client.queued == [(main.run_research_session_task, (body["session_id"],))]
        saved = session.load(body["session_id"])
        assert saved["status"] == "queued" and saved["config"]["models"] == MODELS and saved["config"]["generator"] == "rules"

    def test_the_options_reach_the_config(self, client):
        body = client.post("/start_research_session", json={**BODY, "tuning": 12, "seed": 3, "generator": "rules"}).json()
        saved = session.load(body["session_id"])["config"]
        assert saved["tuning"] == 12 and saved["seed"] == 3

    def test_too_few_models_are_rejected(self, client):
        response = client.post("/start_research_session", json={"models": ["RandomForest"]})
        assert response.status_code == 422 and "two different models" in response.json()["detail"]
        assert client.queued == [] and session.list_sessions() == []

    def test_an_unknown_model_is_rejected(self, client):
        response = client.post("/start_research_session", json={"models": ["RandomForest", "Nope"]})
        assert response.status_code == 422 and "Nope" in response.json()["detail"]

    def test_an_unknown_generator_is_rejected(self, client):
        assert client.post("/start_research_session", json={**BODY, "generator": "magic"}).status_code == 422

    def test_a_bad_tuning_value_is_rejected(self, client):
        assert client.post("/start_research_session", json={**BODY, "tuning": 0}).status_code == 422

    def test_the_request_is_closed_to_unknown_fields(self, client):
        assert client.post("/start_research_session", json={**BODY, "pool": ["magic"]}).status_code == 422

    def test_the_daily_limit_counts_the_start(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        assert client.post("/start_research_session", json=BODY).status_code == 200
        second = client.post("/start_research_session", json=BODY)
        assert second.status_code == 429 and len(client.queued) == 1
        assert guard.usage()["used"] == 1

    def test_a_rejected_request_does_not_spend_the_limit(self, client):
        client.post("/start_research_session", json={"models": ["RandomForest"]})
        assert guard.usage()["used"] == 0

    def test_the_key_is_required_when_set(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        assert client.post("/start_research_session", json=BODY).status_code == 401
        assert client.post("/start_research_session", json=BODY, headers={"X-API-Key": "secret"}).status_code == 200

    def test_the_llm_generator_needs_model_access(self, client, monkeypatch):
        def refuse():
            raise RuntimeError("no key")

        monkeypatch.setattr(main, "check_openai_access", refuse)
        response = client.post("/start_research_session", json={**BODY, "generator": "llm"})
        assert response.status_code == 503 and client.queued == [] and session.list_sessions() == []
        assert client.post("/start_research_session", json=BODY).status_code == 200

    def test_a_queue_failure_marks_the_session_failed(self, monkeypatch):
        from fastapi import HTTPException

        def refuse(task, *args):
            raise HTTPException(status_code=503, detail="task queue is unavailable")

        monkeypatch.setattr(main, "_enqueue", refuse)
        response = TestClient(main.app).post("/start_research_session", json=BODY)
        assert response.status_code == 503
        (name,) = session.list_sessions()
        assert session.load(name)["status"] == "failed" and "unavailable" in session.load(name)["reason"]


class TestCancel:
    def test_a_queued_session_is_cancelled(self, client):
        session_id = client.post("/start_research_session", json=BODY).json()["session_id"]
        response = client.post(f"/research_sessions/{session_id}/cancel")
        assert response.status_code == 200 and response.json()["status"] == "cancelled"

    def test_a_running_session_gets_a_cancel_request(self, client):
        session.save({**session.queue_session(config()), "status": "running"})
        service.beat("s1")
        response = client.post("/research_sessions/s1/cancel")
        assert response.status_code == 200 and response.json()["cancel_requested"] is True
        assert client.get("/research_sessions/s1").json()["session"]["cancel_requested"] is True

    def test_a_finished_session_gives_409(self, client):
        session.run_session(config(), runner=make_runner(planted()))
        assert client.post("/research_sessions/s1/cancel").status_code == 409

    def test_an_unknown_session_gives_404(self, client):
        assert client.post("/research_sessions/nope/cancel").status_code == 404

    def test_an_invalid_id_gives_400(self, client):
        assert client.post("/research_sessions/.hidden/cancel").status_code == 400

    def test_the_key_is_required_when_set(self, client, monkeypatch):
        session.queue_session(config())
        monkeypatch.setenv("API_KEY", "secret")
        assert client.post("/research_sessions/s1/cancel").status_code == 401


class TestRetry:
    def test_a_failed_session_is_queued_again(self, client):
        session.save({**session.queue_session(config()), "status": "failed", "reason": "boom"})
        response = client.post("/research_sessions/s1/retry")
        assert response.status_code == 200 and response.json() == {"session_id": "s1", "status": "queued"}
        assert client.queued == [(main.run_research_session_task, ("s1",))]
        assert session.load("s1")["status"] == "queued" and guard.usage()["used"] == 1

    def test_a_completed_session_gives_409_and_spends_nothing(self, client):
        session.run_session(config(), runner=make_runner(planted()))
        assert client.post("/research_sessions/s1/retry").status_code == 409
        assert guard.usage()["used"] == 0 and client.queued == []

    def test_the_daily_limit_blocks_a_retry(self, client, monkeypatch):
        session.save({**session.queue_session(config()), "status": "failed", "reason": "boom"})
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        guard.spend_start()
        assert client.post("/research_sessions/s1/retry").status_code == 429
        assert session.load("s1")["status"] == "failed"

    def test_an_unknown_session_gives_404(self, client):
        assert client.post("/research_sessions/nope/retry").status_code == 404

    def test_a_queue_failure_marks_the_session_failed(self, monkeypatch):
        from fastapi import HTTPException

        def refuse(task, *args):
            raise HTTPException(status_code=503, detail="task queue is unavailable")

        session.save({**session.queue_session(config()), "status": "failed", "reason": "boom"})
        monkeypatch.setattr(main, "_enqueue", refuse)
        assert TestClient(main.app).post("/research_sessions/s1/retry").status_code == 503
        assert session.load("s1")["status"] == "failed" and "unavailable" in session.load("s1")["reason"]

    def test_the_key_is_required_when_set(self, client, monkeypatch):
        session.save({**session.queue_session(config()), "status": "failed", "reason": "boom"})
        monkeypatch.setenv("API_KEY", "secret")
        assert client.post("/research_sessions/s1/retry").status_code == 401


class TestReading:
    def test_a_stale_running_session_is_shown_as_failed(self, client):
        session.save({**session.queue_session(config()), "status": "running"})
        body = client.get("/research_sessions/s1").json()
        assert body["session"]["status"] == "failed" and body["session"]["stale"] is True
        assert body["summary"]["status"] == "failed"
        assert client.get("/research_sessions").json()["items"][0]["status"] == "failed"

    def test_a_queued_session_is_listed_and_readable(self, client):
        session.queue_session(config())
        assert client.get("/research_sessions").json()["items"][0]["status"] == "queued"
        body = client.get("/research_sessions/s1").json()
        assert body["session"]["status"] == "queued" and body["intact"] is True

    def test_a_live_running_session_shows_its_phase(self, client):
        session.save({**session.queue_session(config()), "status": "running", "phase": "tuned"})
        service.beat("s1")
        assert client.get("/research_sessions").json()["items"][0]["phase"] == "tuned"


    def test_the_progress_of_the_datasets_is_served_while_running(self, client):
        progress = {"stage": "default", "datasets": {"a": {"status": "finished"}, "b": {"status": "running"}, "c": {"status": "queued"}}}
        session.save({**session.queue_session(config()), "status": "running", "progress": progress})
        service.beat("s1")
        expected = {"stage": "default", "total": 3, "finished": 1, "failed": 0, "running": ["b"]}
        assert client.get("/research_sessions").json()["items"][0]["progress"] == expected
        assert client.get("/research_sessions/s1").json()["summary"]["progress"] == expected


class TestTask:
    def test_the_task_runs_the_queued_session(self, monkeypatch):
        session.queue_session(config())
        seen = []
        monkeypatch.setattr(service, "execute_session", lambda session_id: seen.append(session_id))
        tasks.run_research_session_task.run("s1")
        assert seen == ["s1"]
