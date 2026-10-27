from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.campaign.service as service
import app.campaign.store as store
import app.guard as guard
import app.graph.workflow as workflow
import app.main as main
from app.campaign.runner import run_campaign, run_dataset
from app.datasets import DATASETS, benchmark_keys
from app.seeds import SPLIT_SEEDS
from app.variants import expected_keys

MODELS = ["RandomForest", "MLP"]
KEYS = benchmark_keys()[:4]
SPEC = {
    "title": "Forests against nets",
    "models": MODELS,
    "params": {},
    "datasets": KEYS,
    "claims": [{"statement": "Forests beat the MLP", "metric": "roc_auc", "subject": ["RandomForest"], "other": ["MLP"]}],
    "source": {},
}
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    monkeypatch.setattr(guard, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("DAILY_START_LIMIT", raising=False)
    return tmp_path / "campaigns"


@pytest.fixture
def client(monkeypatch):
    queued = []
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: queued.append((task, args)))
    test_client = TestClient(main.app)
    test_client.queued = queued
    return test_client


def output_for(dataset):
    lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
    for _ in SPLIT_SEEDS:
        for key in expected_keys(MODELS, {"models": MODELS, "params": {}}):
            lines.append(f"model={key} accuracy=0.9000 f1=0.8500 roc_auc=0.9000 pr_auc=0.8800 train_seconds=0.1000 tn=500 fp=100 fn=100 tp=500")
    return "\n".join(lines)


def healthy(script, schema):
    return output_for(next(key for key in KEYS if DATASETS[key]["config"] in script))


def write_state(campaign_id, status, updated=None, **extra):
    state = {"id": campaign_id, "title": "T", "status": status, "datasets": {key: {"status": "queued"} for key in KEYS}, **extra}
    store.save_state(campaign_id, state)
    if updated is not None:
        path = store.campaign_dir(campaign_id) / "state.json"
        import json

        path.write_text(json.dumps({**state, "updated": updated.isoformat(timespec="seconds")}), encoding="utf-8")


class TestCancelFlag:
    def test_there_is_no_request_at_first(self):
        assert store.cancel_requested("abc") is False

    def test_a_request_is_remembered(self):
        store.request_cancel("abc")
        assert store.cancel_requested("abc") is True
        assert store.cancel_requested("other") is False

    def test_it_can_be_cleared_and_clearing_twice_is_harmless(self):
        store.request_cancel("abc")
        store.clear_cancel("abc")
        store.clear_cancel("abc")
        assert store.cancel_requested("abc") is False

    def test_an_invalid_id_is_refused(self):
        with pytest.raises(store.CampaignStoreError):
            store.request_cancel("../x")


class TestRunnerStops:
    def test_a_dataset_is_not_started_after_the_stop(self):
        result = run_dataset(KEYS[0], SPEC, healthy, should_stop=lambda: True)
        assert result["status"] == "cancelled" and result["dataset"] == KEYS[0]

    def test_no_second_attempt_after_the_stop(self):
        calls = []

        def broken(script, schema):
            calls.append(1)
            raise RuntimeError("boom")

        result = run_dataset(KEYS[0], SPEC, broken, attempts=3, should_stop=lambda: len(calls) >= 1)
        assert result["status"] == "cancelled" and len(calls) == 1

    def test_without_a_stop_function_nothing_changes(self):
        assert run_dataset(KEYS[0], SPEC, healthy)["status"] == "finished"

    def test_a_stopped_campaign_lists_the_datasets_it_left_out(self):
        started = []

        def stop():
            return len(started) >= 1

        def execute(script, schema):
            started.append(1)
            return healthy(script, schema)

        outcome = run_campaign(SPEC, execute, workers=1, should_stop=stop)
        assert len(outcome["datasets"]) == 1
        assert outcome["cancelled"] == KEYS[1:]
        assert outcome["failed"] == {}

    def test_the_progress_callback_hears_about_cancelled_datasets(self):
        heard = {}
        run_campaign(SPEC, healthy, workers=1, on_update=lambda dataset, result: heard.__setitem__(dataset, result["status"]), should_stop=lambda: True)
        assert heard == {key: "cancelled" for key in KEYS}

    def test_a_dataset_stopped_before_it_began_has_no_attempts(self):
        assert run_dataset(KEYS[0], SPEC, healthy, should_stop=lambda: True)["attempts"] == 0

    def test_a_dataset_stopped_after_one_attempt_counts_it(self):
        calls = []

        def broken(script, schema):
            calls.append(1)
            raise RuntimeError("boom")

        assert run_dataset(KEYS[0], SPEC, broken, attempts=3, should_stop=lambda: len(calls) >= 1)["attempts"] == 1

    def test_a_dataset_that_was_never_started_is_not_reported_as_running(self):
        heard = []
        run_campaign(SPEC, healthy, workers=1, on_update=lambda dataset, result: heard.append(result["status"]), should_stop=lambda: True)
        assert "running" not in heard and heard == ["cancelled"] * len(KEYS)

    def test_the_stop_reaches_the_attempts_of_a_dataset_inside_a_campaign(self):
        calls = []

        def broken(script, schema):
            calls.append(1)
            raise RuntimeError("boom")

        outcome = run_campaign(SPEC, broken, workers=1, attempts=3, should_stop=lambda: len(calls) >= 1)
        assert len(calls) == 1 and outcome["cancelled"] == KEYS and outcome["failed"] == {}

    def test_a_complete_run_has_no_cancelled_key(self):
        assert "cancelled" not in run_campaign(SPEC, healthy, workers=1)


class TestExecuteHonoursCancel:
    def test_a_campaign_cancelled_while_queued_never_starts(self):
        service.queue_campaign(SPEC)
        campaign_id = store.list_campaigns()[0]
        service.cancel_campaign(campaign_id)

        def forbidden(script, schema):
            raise AssertionError("must not run")

        state = service.execute_campaign(SPEC, campaign_id, forbidden)
        assert state["status"] == "cancelled"

    def test_a_running_campaign_stops_and_keeps_no_analysis(self):
        service.queue_campaign(SPEC)
        campaign_id = store.list_campaigns()[0]
        calls = []

        def execute(script, schema):
            calls.append(1)
            if len(calls) == 1:
                store.request_cancel(campaign_id)
            return healthy(script, schema)

        state = service.execute_campaign(SPEC, campaign_id, execute, workers=1)
        assert state["status"] == "cancelled"
        assert state["finished"].endswith("+00:00")
        statuses = [item["status"] for item in state["datasets"].values()]
        assert statuses.count("finished") == 1 and statuses.count("cancelled") == len(KEYS) - 1
        assert store.load_analysis(campaign_id) is None and store.load_report(campaign_id) is None
        assert "verdicts" not in state

    def test_a_cancel_that_comes_too_late_changes_nothing(self):
        service.queue_campaign(SPEC)
        campaign_id = store.list_campaigns()[0]
        remaining = [len(KEYS)]

        def execute(script, schema):
            remaining[0] -= 1
            if remaining[0] == 0:
                store.request_cancel(campaign_id)
            return healthy(script, schema)

        state = service.execute_campaign(SPEC, campaign_id, execute, workers=1)
        assert state["status"] in {"completed", "needs_review"}


class TestCancelCampaign:
    def test_a_queued_campaign_is_cancelled_at_once(self):
        service.queue_campaign(SPEC)
        campaign_id = store.list_campaigns()[0]
        state = service.cancel_campaign(campaign_id)
        assert state["status"] == "cancelled" and state["finished"]
        assert {item["status"] for item in state["datasets"].values()} == {"cancelled"}
        assert store.load_state(campaign_id)["status"] == "cancelled"
        assert store.cancel_requested(campaign_id)

    def test_a_running_campaign_gets_a_request(self):
        write_state("run-1", "running")
        state = service.cancel_campaign("run-1")
        assert state["status"] == "running" and state["cancel_requested"] is True
        assert store.cancel_requested("run-1")
        assert store.load_state("run-1")["status"] == "running"

    @pytest.mark.parametrize("status", ["completed", "needs_review", "failed", "cancelled"])
    def test_a_finished_campaign_cannot_be_cancelled(self, status):
        write_state("done-1", status)
        with pytest.raises(service.CampaignControlError) as caught:
            service.cancel_campaign("done-1")
        assert caught.value.status_code == 409 and status in str(caught.value)
        assert not store.cancel_requested("done-1")

    def test_an_unknown_campaign_is_404(self):
        with pytest.raises(service.CampaignControlError) as caught:
            service.cancel_campaign("nope")
        assert caught.value.status_code == 404

    def test_a_stale_running_campaign_is_treated_as_failed(self, monkeypatch):
        monkeypatch.setattr(service, "_now", lambda: NOW)
        write_state("old-1", "running", updated=NOW - timedelta(minutes=30))
        with pytest.raises(service.CampaignControlError) as caught:
            service.cancel_campaign("old-1")
        assert caught.value.status_code == 409


class TestEffectiveState:
    def test_it_matches_the_graph_threshold(self):
        assert service.STALE_SECONDS == workflow.STALE_CAMPAIGN_SECONDS

    def fresh(self, status, minutes):
        return {"id": "x", "status": status, "updated": (NOW - timedelta(minutes=minutes)).isoformat(timespec="seconds"), "datasets": {}}

    @pytest.mark.parametrize("status", ["queued", "running"])
    def test_an_idle_active_campaign_is_shown_as_failed(self, status):
        shown = service.effective_state(self.fresh(status, 21), NOW)
        assert shown["status"] == "failed" and shown["stale"] is True
        assert shown["error"] == "the campaign has reported no progress for 21 minutes; its worker may have stopped"

    @pytest.mark.parametrize("status", ["queued", "running"])
    def test_a_recent_active_campaign_is_untouched(self, status):
        state = self.fresh(status, 19)
        assert service.effective_state(state, NOW) == state

    def test_the_boundary_is_not_yet_stale(self):
        state = self.fresh("running", 20)
        assert service.effective_state(state, NOW) == state

    @pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "needs_review"])
    def test_a_finished_campaign_is_never_stale(self, status):
        state = self.fresh(status, 600)
        assert service.effective_state(state, NOW) == state

    def test_a_missing_or_broken_time_is_left_alone(self):
        for updated in (None, "not a time"):
            state = {"id": "x", "status": "running", "updated": updated}
            assert service.effective_state(state, NOW) == state

    def test_a_naive_time_counts_as_utc(self):
        state = {"id": "x", "status": "running", "updated": (NOW - timedelta(minutes=40)).replace(tzinfo=None).isoformat()}
        assert service.effective_state(state, NOW)["status"] == "failed"

    def test_the_original_is_not_modified(self):
        state = self.fresh("running", 40)
        service.effective_state(state, NOW)
        assert state["status"] == "running" and "stale" not in state

    def test_a_pending_cancel_is_shown_on_a_running_campaign(self):
        write_state("run-2", "running")
        store.request_cancel("run-2")
        assert service.effective_state(store.load_state("run-2"), NOW)["cancel_requested"] is True

    def test_no_cancel_flag_is_shown_when_none_is_pending(self):
        write_state("run-3", "running")
        assert "cancel_requested" not in service.effective_state(store.load_state("run-3"), NOW)

    def test_a_queued_campaign_does_not_show_a_cancel_request(self):
        write_state("q-1", "queued")
        store.request_cancel("q-1")
        assert "cancel_requested" not in service.effective_state(store.load_state("q-1"), NOW)

    def test_a_finished_campaign_does_not_show_an_old_cancel_flag(self):
        write_state("done-2", "completed")
        store.request_cancel("done-2")
        assert "cancel_requested" not in service.effective_state(store.load_state("done-2"), NOW)


class TestRetryCampaign:
    def spec_saved(self, campaign_id, status, **extra):
        write_state(campaign_id, status, **extra)
        store.save_spec(campaign_id, SPEC)

    @pytest.mark.parametrize("status", ["failed", "cancelled"])
    def test_a_stopped_campaign_goes_back_to_the_queue(self, status):
        self.spec_saved("r-1", status, error="old", finished="then")
        store.request_cancel("r-1")
        spec, state = service.retry_campaign("r-1")
        assert spec == SPEC
        assert state["status"] == "queued" and state["recoveries"] == 1
        assert "error" not in state and "finished" not in state
        assert not store.cancel_requested("r-1")
        assert store.load_state("r-1")["status"] == "queued"
        assert {item["status"] for item in state["datasets"].values()} == {"queued"}

    def test_every_dataset_starts_over(self):
        self.spec_saved("r-0", "failed")
        previous = {key: {"status": "finished", "seconds": 3.0} for key in KEYS[:2]} | {key: {"status": "failed", "error": "x"} for key in KEYS[2:]}
        store.save_state("r-0", store.load_state("r-0") | {"datasets": previous})
        _, state = service.retry_campaign("r-0")
        assert state["datasets"] == {key: {"status": "queued"} for key in KEYS}

    def test_the_count_grows_and_the_origin_stays(self):
        self.spec_saved("r-2", "failed", recoveries=2, origin="console")
        _, state = service.retry_campaign("r-2")
        assert state["recoveries"] == 3 and state["origin"] == "console"

    def test_a_stale_campaign_can_be_retried(self, monkeypatch):
        monkeypatch.setattr(service, "_now", lambda: NOW)
        write_state("r-3", "running", updated=NOW - timedelta(minutes=45))
        store.save_spec("r-3", SPEC)
        assert service.retry_campaign("r-3")[1]["status"] == "queued"

    @pytest.mark.parametrize("status", ["queued", "running", "completed", "needs_review"])
    def test_other_states_cannot_be_retried(self, status):
        self.spec_saved("r-4", status)
        with pytest.raises(service.CampaignControlError) as caught:
            service.retry_campaign("r-4")
        assert caught.value.status_code == 409
        assert store.load_state("r-4")["status"] == status

    def test_an_unknown_campaign_is_404(self):
        with pytest.raises(service.CampaignControlError) as caught:
            service.retry_campaign("nope")
        assert caught.value.status_code == 404

    def test_without_a_saved_spec_it_is_409(self):
        write_state("r-5", "failed")
        with pytest.raises(service.CampaignControlError) as caught:
            service.retry_campaign("r-5")
        assert caught.value.status_code == 409 and "specification" in str(caught.value)
        assert store.load_state("r-5")["status"] == "failed"

    def test_a_retried_campaign_runs_again(self):
        service.queue_campaign(SPEC)
        campaign_id = store.list_campaigns()[0]
        service.cancel_campaign(campaign_id)
        spec, _ = service.retry_campaign(campaign_id)
        state = service.execute_campaign(spec, campaign_id, healthy, workers=2)
        assert state["status"] in {"completed", "needs_review"}


class TestApi:
    def test_cancel_a_queued_campaign(self, client):
        service.queue_campaign(SPEC)
        campaign_id = store.list_campaigns()[0]
        response = client.post(f"/campaign/{campaign_id}/cancel")
        assert response.status_code == 200 and response.json()["status"] == "cancelled"

    def test_cancel_a_running_campaign_reports_the_request(self, client):
        write_state("a-1", "running")
        body = client.post("/campaign/a-1/cancel").json()
        assert body["status"] == "running" and body["cancel_requested"] is True

    def test_cancel_conflict_and_missing(self, client):
        write_state("a-2", "completed")
        assert client.post("/campaign/a-2/cancel").status_code == 409
        assert client.post("/campaign/nope/cancel").status_code == 404
        assert client.post("/campaign/..%2Fx/cancel").status_code in {400, 404}

    def test_retry_queues_the_task_with_the_saved_spec(self, client):
        write_state("a-3", "failed")
        store.save_spec("a-3", SPEC)
        response = client.post("/campaign/a-3/retry")
        assert response.status_code == 200 and response.json() == {"campaign_id": "a-3", "status": "queued"}
        task, args = client.queued[0]
        assert task is main.run_campaign_task and args == ("a-3", SPEC)

    def test_retry_conflict_and_missing(self, client):
        write_state("a-4", "running")
        assert client.post("/campaign/a-4/retry").status_code == 409
        assert client.post("/campaign/nope/retry").status_code == 404
        assert client.queued == []

    def test_a_retry_that_cannot_be_queued_leaves_the_campaign_failed(self, monkeypatch):
        def refuse(task, *args):
            raise main.HTTPException(status_code=503, detail="queue is down")

        monkeypatch.setattr(main, "_enqueue", refuse)
        write_state("a-5", "failed")
        store.save_spec("a-5", SPEC)
        response = TestClient(main.app).post("/campaign/a-5/retry")
        assert response.status_code == 503
        assert store.load_state("a-5")["status"] == "failed" and store.load_state("a-5")["error"] == "queue is down"

    def test_status_shows_a_stale_campaign_as_failed(self, client, monkeypatch):
        monkeypatch.setattr(service, "_now", lambda: NOW)
        write_state("a-6", "running", updated=NOW - timedelta(minutes=50))
        body = client.get("/campaign/a-6").json()
        assert body["status"] == "failed" and body["stale"] is True and "no progress for 50 minutes" in body["error"]
        assert store.load_state("a-6")["status"] == "running"

    def test_the_list_shows_a_stale_campaign_as_failed(self, client, monkeypatch):
        monkeypatch.setattr(service, "_now", lambda: NOW)
        write_state("a-7", "running", updated=NOW - timedelta(minutes=50))
        item = next(item for item in client.get("/campaigns").json()["items"] if item["id"] == "a-7")
        assert item["status"] == "failed"

    def test_the_summary_shows_the_cancel_request_and_the_stale_error(self, client, monkeypatch):
        monkeypatch.setattr(service, "_now", lambda: NOW)
        write_state("a-8", "running", updated=NOW - timedelta(minutes=50))
        body = client.get("/campaign/a-8/summary").json()
        assert body["status"]["code"] == "failed" and body["error_info"]["code"] == "stale_worker"

    def test_a_key_is_required_when_one_is_set(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        write_state("a-9", "running")
        store.save_spec("a-9", SPEC)
        assert client.post("/campaign/a-9/cancel").status_code == 401
        assert client.post("/campaign/a-9/retry").status_code == 401
        assert client.post("/campaign/a-9/cancel", headers={"X-API-Key": "secret"}).status_code == 200

    def test_a_retry_spends_one_start(self, client, monkeypatch):
        spent = []
        monkeypatch.setattr(main, "spend_start", lambda: spent.append(1))
        write_state("a-10", "failed")
        store.save_spec("a-10", SPEC)
        client.post("/campaign/a-10/retry")
        assert spent == [1]

    def test_a_refused_retry_spends_nothing(self, client, monkeypatch):
        spent = []
        monkeypatch.setattr(main, "spend_start", lambda: spent.append(1))
        write_state("a-11", "completed")
        client.post("/campaign/a-11/retry")
        assert spent == []


class TestCollectNode:
    def test_a_cancelled_campaign_stops_the_research_with_a_clear_message(self):
        from app.graph.campaign_nodes import campaign_collect_node

        write_state("g-1", "cancelled")
        with pytest.raises(RuntimeError, match=r"^campaign cancelled"):
            campaign_collect_node({"campaign_id": "g-1"})


class TestWorkerLossRecovery:
    def test_the_campaign_task_is_redelivered_when_its_worker_dies(self):
        import app.tasks as tasks

        assert tasks.run_campaign_task.acks_late is True
        assert tasks.run_campaign_task.reject_on_worker_lost is True

    def test_other_tasks_keep_the_default(self):
        import app.tasks as tasks

        assert tasks.run_research_task.acks_late in (None, False)

    def test_the_broker_waits_longer_than_a_campaign_lasts(self):
        from app.celery_app import celery_app

        assert celery_app.conf.broker_transport_options["visibility_timeout"] >= 7200


class TestFreshRun:
    def test_an_old_cancel_request_does_not_stop_a_new_run(self):
        store.request_cancel("fresh-1")
        state = service.execute_campaign(SPEC, "fresh-1", healthy, workers=2)
        assert state["status"] in {"completed", "needs_review"}
        assert not store.cancel_requested("fresh-1")

    def test_the_number_of_restarts_survives_the_run(self):
        service.queue_campaign(SPEC)
        campaign_id = store.list_campaigns()[0]
        write_state(campaign_id, "queued", recoveries=2, spec_sha256=store.load_state(campaign_id)["spec_sha256"])
        state = service.execute_campaign(SPEC, campaign_id, healthy, workers=2)
        assert state["recoveries"] == 2

    def test_a_first_run_has_no_restart_count(self):
        assert "recoveries" not in service.execute_campaign(SPEC, "fresh-2", healthy, workers=2)


class TestCampaignTask:
    @pytest.fixture
    def calls(self, monkeypatch):
        import app.tasks as tasks

        calls = {"run": [], "resume": []}
        monkeypatch.setattr(tasks, "execute_campaign", lambda spec, campaign_id, tracker=None: calls["run"].append(campaign_id))
        monkeypatch.setattr(tasks.resume_campaign_task, "delay", lambda thread_id: calls["resume"].append(thread_id))
        return calls

    @pytest.mark.parametrize("status", ["completed", "needs_review"])
    def test_a_redelivered_task_does_not_run_a_finished_campaign_again(self, calls, status):
        import app.tasks as tasks

        write_state("t-1", status)
        tasks.run_campaign_task("t-1", SPEC, "thread-1")
        assert calls["run"] == [] and calls["resume"] == ["thread-1"]

    @pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
    def test_every_other_state_runs(self, calls, status):
        import app.tasks as tasks

        write_state("t-2", status)
        tasks.run_campaign_task("t-2", SPEC)
        assert calls["run"] == ["t-2"] and calls["resume"] == []

    def test_an_unknown_campaign_runs(self, calls):
        import app.tasks as tasks

        tasks.run_campaign_task("t-3", SPEC)
        assert calls["run"] == ["t-3"]
