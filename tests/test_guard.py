import json
from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.campaign.service as service
import app.campaign.store as store
import app.guard as guard
import app.main as main
from app.datasets import benchmark_keys

TWO_MODELS = "Compare RandomForest and SVM on churn data"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    monkeypatch.setattr(guard, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("DAILY_START_LIMIT", raising=False)
    return tmp_path


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: calls.append((task.name, args)))
    return calls


@pytest.fixture
def client(queued):
    return TestClient(main.app)


class TestKey:
    def test_without_a_configured_key_everything_is_open(self, client):
        assert client.post("/start_research", json={"query": TWO_MODELS, "mode": "experiment"}).status_code == 200

    def test_a_missing_key_is_refused_when_one_is_configured(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        response = client.post("/start_research", json={"query": TWO_MODELS, "mode": "experiment"})
        assert response.status_code == 401 and response.json()["detail"].startswith("[unauthorized]")

    def test_a_wrong_key_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        response = client.post("/start_research", json={"query": TWO_MODELS, "mode": "experiment"}, headers={"X-API-Key": "guess"})
        assert response.status_code == 401

    def test_the_right_key_is_accepted(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        response = client.post("/start_research", json={"query": TWO_MODELS, "mode": "experiment"}, headers={"X-API-Key": "secret"})
        assert response.status_code == 200

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/start_research", {"query": TWO_MODELS}),
            ("/start_campaign", {"demo": "grinsztajn-2022"}),
            ("/approve_plan", {"thread_id": "t", "decision": "N"}),
            ("/experiments", {"prompt": "x", "csv_schema": "a,b"}),
        ],
    )
    def test_every_endpoint_that_spends_or_decides_needs_the_key(self, client, monkeypatch, path, body):
        monkeypatch.setenv("API_KEY", "secret")
        assert client.post(path, json=body).status_code == 401

    @pytest.mark.parametrize("path", ["/usage", "/campaigns", "/glossary", "/vocabulary"])
    def test_reading_stays_open(self, client, monkeypatch, path):
        monkeypatch.setenv("API_KEY", "secret")
        assert client.get(path).status_code == 200

    def test_the_comparison_does_not_break_on_non_ascii_input(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        with pytest.raises(HTTPException) as caught:
            guard.require_key("şifre")
        assert caught.value.status_code == 401
        monkeypatch.setenv("API_KEY", "şifre")
        guard.require_key("şifre")

    def test_a_missing_header_is_refused_directly(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        with pytest.raises(HTTPException):
            guard.require_key(None)
        monkeypatch.delenv("API_KEY")
        guard.require_key(None)


class TestBudget:
    def start(self, client):
        return client.post("/start_research", json={"query": TWO_MODELS, "mode": "experiment"})

    def test_the_default_limit_is_documented(self):
        assert guard.DEFAULT_DAILY_LIMIT == 100

    def test_the_limit_is_enforced(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "2")
        assert self.start(client).status_code == 200 and self.start(client).status_code == 200
        response = self.start(client)
        assert response.status_code == 429 and response.json()["detail"].startswith("[daily_limit]")
        assert "2" in response.json()["detail"]

    def test_a_refused_start_is_not_queued(self, client, queued, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        self.start(client)
        self.start(client)
        assert len(queued) == 1

    def test_zero_means_unlimited(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "0")
        assert all(self.start(client).status_code == 200 for _ in range(5))

    def test_a_campaign_start_counts_too(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        assert client.post("/start_campaign", json={"demo": "grinsztajn-2022"}).status_code == 200
        assert client.post("/start_campaign", json={"demo": "grinsztajn-2022"}).status_code == 429

    def test_the_two_kinds_of_start_share_one_budget(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        assert self.start(client).status_code == 200
        assert client.post("/start_campaign", json={"demo": "grinsztajn-2022"}).status_code == 429

    def test_an_invalid_request_does_not_use_the_budget(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        assert client.post("/start_campaign", json={"demo": "nope"}).status_code in (404, 422)
        assert client.post("/start_campaign", json={"spec": {"title": "x"}}).status_code == 422
        assert self.start(client).status_code == 200

    def test_a_decision_does_not_use_the_budget(self, client, monkeypatch):
        from app.graph.workflow import PlanDecisionError

        def refuse(thread_id, decision, selected):
            raise PlanDecisionError("research thread was not found", 404)

        monkeypatch.setattr(main, "decide_plan", refuse)
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        client.post("/approve_plan", json={"thread_id": "unknown", "decision": "Y", "selected": 0})
        assert self.start(client).status_code == 200

    def test_the_count_starts_again_the_next_day(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        monkeypatch.setattr(guard, "today", lambda: date(2026, 10, 27))
        assert self.start(client).status_code == 200 and self.start(client).status_code == 429
        monkeypatch.setattr(guard, "today", lambda: date(2026, 10, 28))
        assert self.start(client).status_code == 200

    def test_the_count_is_kept_in_a_file(self, client, monkeypatch, isolated):
        monkeypatch.setenv("DAILY_START_LIMIT", "5")
        monkeypatch.setattr(guard, "today", lambda: date(2026, 10, 27))
        self.start(client)
        self.start(client)
        assert json.loads((isolated / "usage.json").read_text(encoding="utf-8")) == {"2026-10-27": 2}

    def test_old_days_are_dropped_from_the_file(self, client, monkeypatch, isolated):
        monkeypatch.setenv("DAILY_START_LIMIT", "5")
        monkeypatch.setattr(guard, "today", lambda: date(2026, 10, 27))
        (isolated / "usage.json").write_text(json.dumps({"2026-09-01": 4, "2026-10-26": 3}), encoding="utf-8")
        self.start(client)
        assert json.loads((isolated / "usage.json").read_text(encoding="utf-8")) == {"2026-10-27": 1}

    def test_a_broken_file_counts_as_a_fresh_start(self, client, monkeypatch, isolated):
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        (isolated / "usage.json").write_text("not json", encoding="utf-8")
        assert self.start(client).status_code == 200

    @pytest.mark.parametrize("value", ["abc", "-3", ""])
    def test_a_bad_limit_falls_back_to_the_default(self, monkeypatch, value):
        monkeypatch.setenv("DAILY_START_LIMIT", value)
        assert guard.daily_limit() == guard.DEFAULT_DAILY_LIMIT

    def test_the_limit_can_be_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "7")
        assert guard.daily_limit() == 7

    def test_two_threads_never_exceed_the_limit(self, monkeypatch):
        import threading

        monkeypatch.setenv("DAILY_START_LIMIT", "5")
        results = []

        def attempt():
            try:
                guard.spend_start()
                results.append("ok")
            except HTTPException:
                results.append("refused")

        threads = [threading.Thread(target=attempt) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert results.count("ok") == 5 and results.count("refused") == 7


class TestUsage:
    def test_the_usage_of_today(self, monkeypatch, isolated):
        monkeypatch.setattr(guard, "today", lambda: date(2026, 10, 27))
        (isolated / "usage.json").write_text(json.dumps({"2026-10-27": 3}), encoding="utf-8")
        monkeypatch.setenv("DAILY_START_LIMIT", "10")
        assert guard.usage() == {"date": "2026-10-27", "used": 3, "limit": 10, "remaining": 7}

    def test_unlimited_has_no_remaining(self, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "0")
        assert guard.usage()["remaining"] is None

    def test_the_health_endpoint_shows_the_budget(self, client, monkeypatch):
        monkeypatch.setenv("DAILY_START_LIMIT", "10")
        body = client.get("/usage").json()
        assert body["limit"] == 10 and body["used"] == 0 and body["remaining"] == 10


class TestEdges:
    def test_a_header_is_harmless_when_no_key_is_configured(self, client):
        response = client.post("/start_research", json={"query": TWO_MODELS, "mode": "experiment"}, headers={"X-API-Key": "anything"})
        assert response.status_code == 200

    @pytest.mark.parametrize("content", ['{"2026-10-27": "many"}', "[1, 2]", '"text"', "3"])
    def test_a_file_with_unexpected_content_counts_as_a_fresh_start(self, content, isolated, monkeypatch):
        monkeypatch.setattr(guard, "today", lambda: date(2026, 10, 27))
        (isolated / "usage.json").write_text(content, encoding="utf-8")
        assert guard.usage()["used"] == 0
        guard.spend_start()
        assert guard.usage()["used"] == 1

    def test_the_usage_file_may_live_in_a_folder_that_does_not_exist_yet(self, isolated, monkeypatch):
        monkeypatch.setattr(guard, "USAGE_FILE", isolated / "deep" / "er" / "usage.json")
        guard.spend_start()
        assert (isolated / "deep" / "er" / "usage.json").exists()

    def test_today_is_the_real_date(self):
        assert guard.today() == date.today()

    def test_a_lowered_limit_leaves_nothing_remaining_not_a_negative_number(self, isolated, monkeypatch):
        monkeypatch.setattr(guard, "today", lambda: date(2026, 10, 27))
        (isolated / "usage.json").write_text(json.dumps({"2026-10-27": 5}), encoding="utf-8")
        monkeypatch.setenv("DAILY_START_LIMIT", "3")
        assert guard.usage()["remaining"] == 0

    def test_the_direct_experiment_endpoint_uses_the_budget(self, client, monkeypatch):
        monkeypatch.setattr(main, "execute_experiment", lambda prompt, schema: {"ok": True})
        monkeypatch.setenv("DAILY_START_LIMIT", "1")
        body = {"prompt": "x", "csv_schema": "a,b"}
        assert client.post("/experiments", json=body).status_code == 200
        assert client.post("/experiments", json=body).status_code == 429
