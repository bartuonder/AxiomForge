import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from celery.exceptions import Retry

import app.campaign.service as service
import app.campaign.store as store
import app.guard as guard
import app.tasks as tasks
from app.datasets import DATASETS, benchmark_keys
from app.seeds import SPLIT_SEEDS
from app.variants import expected_keys

MODELS = ["RandomForest", "MLP"]
KEYS = benchmark_keys()[:3]
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
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")


def healthy(script, schema):
    dataset = next(key for key in KEYS if DATASETS[key]["config"] in script)
    lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
    for _ in SPLIT_SEEDS:
        for key in expected_keys(MODELS, {"models": MODELS, "params": {}}):
            lines.append(f"model={key} accuracy=0.9000 f1=0.8500 roc_auc=0.9000 pr_auc=0.8800 train_seconds=0.1000 tn=500 fp=100 fn=100 tp=500")
    return "\n".join(lines)


def save(campaign_id, status, **extra):
    store.save_state(campaign_id, {"id": campaign_id, "title": "T", "status": status, "datasets": {}, **extra})


class TestStore:
    def test_there_is_no_beat_at_first(self):
        assert store.heartbeat_age("abc") is None

    def test_a_beat_gives_a_small_age(self):
        store.beat("abc")
        age = store.heartbeat_age("abc")
        assert age is not None and 0 <= age < 5

    def test_the_age_grows_with_the_clock(self):
        store.beat("abc")
        assert store.heartbeat_age("abc", now=time.time() + 100) == pytest.approx(100, abs=2)

    def test_a_clock_that_runs_backwards_gives_zero(self):
        store.beat("abc")
        assert store.heartbeat_age("abc", now=time.time() - 100) == 0

    def test_a_broken_file_counts_as_no_beat(self):
        store.beat("abc")
        (store.campaign_dir("abc") / store.HEARTBEAT_FILE).write_text("not a number", encoding="utf-8")
        assert store.heartbeat_age("abc") is None

    def test_an_invalid_id_is_refused(self):
        with pytest.raises(store.CampaignStoreError):
            store.beat("../x")

    def test_a_beat_of_another_campaign_is_not_seen(self):
        store.beat("one")
        assert store.heartbeat_age("two") is None


class TestAlive:
    def test_a_recent_beat_means_a_worker_is_alive(self):
        store.beat("abc")
        assert service.is_alive("abc") is True

    def test_no_beat_means_nobody_is_working(self):
        assert service.is_alive("abc") is False

    def test_an_old_beat_means_the_worker_died(self, monkeypatch):
        store.beat("abc")
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: service.ALIVE_SECONDS + 1)
        assert service.is_alive("abc") is False

    def test_the_limit_itself_is_still_alive(self, monkeypatch):
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: service.ALIVE_SECONDS)
        assert service.is_alive("abc") is True

    def test_the_beat_is_more_frequent_than_the_alive_limit(self):
        assert service.HEARTBEAT_SECONDS * 3 <= service.ALIVE_SECONDS


class TestRunBeats:
    def test_a_run_writes_beats_while_it_works_and_stops_after(self, monkeypatch):
        monkeypatch.setattr(service, "HEARTBEAT_SECONDS", 0.05)
        seen = []

        def slow(script, schema):
            time.sleep(0.25)
            seen.append(store.heartbeat_age("hb-1"))
            return healthy(script, schema)

        service.execute_campaign(SPEC, "hb-1", slow, workers=1)
        assert seen and all(age is not None and age < 0.2 for age in seen)
        stopped = store.heartbeat_age("hb-1")
        time.sleep(0.3)
        assert store.heartbeat_age("hb-1") - stopped >= 0.25
        assert not any(thread.name == "campaign-heartbeat" for thread in threading.enumerate())

    def test_the_beat_stops_even_when_the_run_fails(self, monkeypatch):
        monkeypatch.setattr(service, "HEARTBEAT_SECONDS", 0.05)

        def explode(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(service, "analyze_campaign", explode)
        state = service.execute_campaign(SPEC, "hb-2", healthy, workers=1)
        assert state["status"] == "failed"
        assert not any(thread.name == "campaign-heartbeat" for thread in threading.enumerate())

    def test_a_cancelled_run_stops_beating_too(self, monkeypatch):
        monkeypatch.setattr(service, "HEARTBEAT_SECONDS", 0.05)
        service.queue_once("hb-3", SPEC)
        calls = []

        def execute(script, schema):
            calls.append(1)
            if len(calls) == 1:
                store.request_cancel("hb-3")
            return healthy(script, schema)

        state = service.execute_campaign(SPEC, "hb-3", execute, workers=1)
        assert state["status"] == "cancelled"
        assert not any(thread.name == "campaign-heartbeat" for thread in threading.enumerate())


class TestStaleKnowsTheBeat:
    def idle(self, campaign_id, status="running"):
        return {"id": campaign_id, "status": status, "updated": (NOW - timedelta(minutes=40)).isoformat(timespec="seconds"), "datasets": {}}

    def test_a_live_worker_keeps_a_quiet_campaign_from_looking_stale(self, monkeypatch):
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: 5)
        shown = service.effective_state(self.idle("q-1"), NOW)
        assert shown["status"] == "running" and "stale" not in shown

    def test_a_silent_worker_does_not(self):
        shown = service.effective_state(self.idle("q-2"), NOW)
        assert shown["status"] == "failed" and shown["stale"] is True

    def test_a_dead_workers_old_beat_does_not(self, monkeypatch):
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: 600)
        assert service.effective_state(self.idle("q-3"), NOW)["status"] == "failed"

    def test_a_queued_campaign_with_a_beat_is_not_stale_either(self, monkeypatch):
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: 5)
        assert service.effective_state(self.idle("q-4", "queued"), NOW)["status"] == "queued"

    def test_the_limit_of_the_beat_is_the_alive_limit(self, monkeypatch):
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: service.ALIVE_SECONDS)
        assert service.effective_state(self.idle("q-5"), NOW)["status"] == "running"
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: service.ALIVE_SECONDS + 1)
        assert service.effective_state(self.idle("q-5"), NOW)["status"] == "failed"

    def test_the_clock_given_to_the_check_is_used_for_the_beat(self, monkeypatch):
        seen = []
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: seen.append(now) or 5)
        service.effective_state(self.idle("q-6"), NOW)
        assert seen == [NOW.timestamp()]


class TestTaskWaitsForALiveWorker:
    @pytest.fixture
    def calls(self, monkeypatch):
        calls = {"run": [], "resume": []}
        monkeypatch.setattr(tasks, "execute_campaign", lambda spec, campaign_id, tracker=None: calls["run"].append(campaign_id))
        monkeypatch.setattr(tasks.resume_campaign_task, "delay", lambda thread_id: calls["resume"].append(thread_id))
        return calls

    def test_a_task_delivered_while_another_worker_is_alive_waits_and_does_not_run(self, calls):
        save("t-1", "running")
        store.beat("t-1")
        with pytest.raises(Retry):
            tasks.run_campaign_task("t-1", SPEC, "thread-1")
        assert calls["run"] == [] and calls["resume"] == []

    def test_a_task_whose_worker_died_runs(self, calls, monkeypatch):
        save("t-2", "running")
        monkeypatch.setattr(store, "heartbeat_age", lambda campaign_id, now=None: 600)
        tasks.run_campaign_task("t-2", SPEC)
        assert calls["run"] == ["t-2"]

    def test_a_first_delivery_runs(self, calls):
        tasks.run_campaign_task("t-3", SPEC)
        assert calls["run"] == ["t-3"]

    def test_the_wait_is_a_minute_and_long_enough_for_a_long_campaign(self):
        assert tasks.LIVE_RETRY_SECONDS == 60
        assert tasks.LIVE_RETRIES * tasks.LIVE_RETRY_SECONDS >= 6 * 3600

    def test_a_finished_campaign_is_still_skipped_before_the_beat_is_looked_at(self, calls):
        save("t-4", "completed")
        store.beat("t-4")
        tasks.run_campaign_task("t-4", SPEC, "thread-4")
        assert calls["run"] == [] and calls["resume"] == ["thread-4"]
