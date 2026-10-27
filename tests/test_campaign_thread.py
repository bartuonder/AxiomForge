import pytest
from fastapi.testclient import TestClient

import app.campaign.service as service
import app.campaign.store as store
import app.guard as guard
import app.main as main
from app.datasets import DATASETS, benchmark_keys
from app.graph import campaign_nodes
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


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    monkeypatch.setattr(guard, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("DAILY_START_LIMIT", raising=False)


def healthy(script, schema):
    dataset = next(key for key in KEYS if DATASETS[key]["config"] in script)
    lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
    for _ in SPLIT_SEEDS:
        for key in expected_keys(MODELS, {"models": MODELS, "params": {}}):
            lines.append(f"model={key} accuracy=0.9000 f1=0.8500 roc_auc=0.9000 pr_auc=0.8800 train_seconds=0.1000 tn=500 fp=100 fn=100 tp=500")
    return "\n".join(lines)


class TestThreadIsRemembered:
    def test_a_campaign_queued_for_a_thread_remembers_it(self):
        service.queue_once("g-1", SPEC, thread_id="thread-1")
        assert store.load_state("g-1")["thread_id"] == "thread-1"

    def test_a_campaign_queued_without_a_thread_has_none(self):
        service.queue_once("g-2", SPEC)
        assert "thread_id" not in store.load_state("g-2")

    def test_the_running_state_keeps_it(self):
        service.queue_once("g-3", SPEC, thread_id="thread-3")
        state = service.execute_campaign(SPEC, "g-3", healthy, workers=2)
        assert state["thread_id"] == "thread-3"
        assert store.load_state("g-3")["thread_id"] == "thread-3"

    def test_a_run_without_a_thread_does_not_invent_one(self):
        service.queue_once("g-4", SPEC)
        assert "thread_id" not in service.execute_campaign(SPEC, "g-4", healthy, workers=2)

    def test_starting_again_keeps_it(self):
        service.queue_once("g-5", SPEC, thread_id="thread-5")
        store.save_state("g-5", store.load_state("g-5") | {"status": "failed", "error": "x"})
        _, state = service.retry_campaign("g-5")
        assert state["thread_id"] == "thread-5" and state["status"] == "queued"

    def test_the_dispatch_node_passes_the_thread_to_the_state(self, monkeypatch):
        monkeypatch.setattr(campaign_nodes, "_enqueue_campaign", lambda campaign_id, spec, thread_id: None)
        result = campaign_nodes.campaign_dispatch_node({"campaign_spec": SPEC}, {"configurable": {"thread_id": "thread-6"}})
        assert store.load_state(result["campaign_id"])["thread_id"] == "thread-6"


class TestRetryResumesTheThread:
    @pytest.fixture
    def client(self, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "_enqueue", lambda task, *args: calls.append((task, args)))
        client = TestClient(main.app)
        client.calls = calls
        return client

    def stopped(self, campaign_id, **extra):
        service.queue_once(campaign_id, SPEC, **extra)
        store.save_state(campaign_id, store.load_state(campaign_id) | {"status": "failed", "error": "x"})

    def test_the_task_gets_the_thread_so_the_graph_continues(self, client):
        self.stopped("g-7", thread_id="thread-7")
        assert client.post("/campaign/g-7/retry").status_code == 200
        task, args = client.calls[0]
        assert task is main.run_campaign_task and args == ("g-7", store.load_spec("g-7"), "thread-7")

    def test_a_campaign_without_a_thread_is_started_alone(self, client):
        self.stopped("g-8")
        client.post("/campaign/g-8/retry")
        task, args = client.calls[0]
        assert task is main.run_campaign_task and args == ("g-8", store.load_spec("g-8"))
