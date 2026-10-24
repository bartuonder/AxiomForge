from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.graph.workflow as workflow
import app.main as main

CANDIDATES = [
    {"spec": {"title": "First campaign", "datasets": ["a"]}, "estimate": {"estimated_seconds": 228}, "evidence": []},
    {"spec": {"title": "Second campaign", "datasets": ["b"]}, "estimate": {"estimated_seconds": 100}, "evidence": []},
]
TWO_MODELS = "Compare SVM and KNN on churn"
PAPER_QUERY = "Replicate the tabular benchmark claim of the Grinsztajn paper"


class FakeGraph:
    def __init__(self, values, next_nodes=("approval_gate",)):
        self.values = values
        self.next_nodes = tuple(next_nodes)
        self.updates = []

    def get_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next_nodes)

    def update_state(self, config, update):
        self.updates.append(update)
        self.values = {**self.values, **update}


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: calls.append((task.name, args)))
    return calls


@pytest.fixture
def client(queued):
    return TestClient(main.app)


class TestStart:
    def test_the_default_mode_is_the_single_dataset_experiment(self, client, queued):
        response = client.post("/start_research", json={"query": TWO_MODELS})
        assert response.status_code == 200 and response.json()["mode"] == "experiment"
        name, (thread_id, query, mode) = queued[0]
        assert name == "axiomforge.run_research" and query == TWO_MODELS and mode == "experiment"
        assert response.json()["thread_id"] == thread_id

    def test_an_explicit_experiment_behaves_the_same(self, client, queued):
        response = client.post("/start_research", json={"query": TWO_MODELS, "mode": "experiment"})
        assert response.status_code == 200 and queued[0][1][2] == "experiment"

    def test_a_campaign_is_started_only_when_it_is_asked_for(self, client, queued):
        response = client.post("/start_research", json={"query": PAPER_QUERY, "mode": "campaign"})
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "campaign" and body["status"] == "running"
        assert queued[0][1][1:] == (PAPER_QUERY, "campaign")

    def test_a_campaign_query_needs_no_model_names(self, client, queued):
        assert client.post("/start_research", json={"query": "How does churn behave?", "mode": "campaign"}).status_code == 200
        assert len(queued) == 1

    def test_an_experiment_query_without_two_models_is_still_refused(self, client, queued):
        response = client.post("/start_research", json={"query": "How does churn behave?"})
        assert response.status_code == 422 and "name at least two models" in response.json()["detail"]
        assert queued == []

    @pytest.mark.parametrize("mode", ["auto", "", "Campaign", "both", 1, None])
    def test_there_is_no_automatic_mode_and_unknown_modes_are_refused(self, client, queued, mode):
        response = client.post("/start_research", json={"query": PAPER_QUERY, "mode": mode})
        assert response.status_code == 422
        assert queued == []

    def test_an_empty_query_is_still_refused_in_both_modes(self, client, queued):
        assert client.post("/start_research", json={"query": "", "mode": "campaign"}).status_code == 422
        assert client.post("/start_research", json={"query": ""}).status_code == 422
        assert queued == []

    def test_an_unavailable_queue_is_a_503_in_campaign_mode_too(self, monkeypatch):
        from fastapi import HTTPException

        def down(task, *args):
            raise HTTPException(status_code=503, detail="task queue is unavailable: no broker")

        monkeypatch.setattr(main, "_enqueue", down)
        response = TestClient(main.app).post("/start_research", json={"query": PAPER_QUERY, "mode": "campaign"})
        assert response.status_code == 503


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph({"mode": "campaign", "campaign_specs": CANDIDATES, "approval_status": ""})

    @contextmanager
    def opened():
        yield SimpleNamespace(setup=lambda: None)

    monkeypatch.setattr(workflow, "_open_graph", opened)
    monkeypatch.setattr(workflow, "_compile", lambda checkpointer: fake)
    monkeypatch.setattr(workflow, "read_error", lambda thread_id: "")
    monkeypatch.setattr(main, "revoke_approval", lambda thread_id: None)
    return fake


class TestApproval:
    def approve(self, client, **body):
        return client.post("/approve_plan", json={"thread_id": "t", **body})

    def test_approving_a_campaign_candidate_queues_the_resume(self, client, queued, graph):
        response = self.approve(client, decision="Y", selected=1)
        assert response.status_code == 200
        body = response.json()
        assert body["selected_campaign"] == 1 and body["hypotheses"] == ["First campaign", "Second campaign"]
        assert queued == [("axiomforge.resume_research", ("t",))]
        assert graph.updates[0]["campaign_spec"] == CANDIDATES[1]["spec"]

    def test_a_campaign_approval_needs_a_valid_candidate(self, client, queued, graph):
        for selected in (None, 2, -1):
            body = {"decision": "Y"} if selected is None else {"decision": "Y", "selected": selected}
            assert self.approve(client, **body).status_code == 422
        assert queued == [] and graph.updates == []

    def test_a_campaign_rejection_queues_nothing(self, client, queued, graph):
        response = self.approve(client, decision="N")
        assert response.status_code == 200 and response.json()["approval_status"] == "rejected"
        assert queued == []

    def test_the_status_of_a_paused_campaign_lists_the_candidates(self, client, graph):
        body = client.get("/research/t").json()
        assert body["mode"] == "campaign" and body["status"] == "paused"
        assert body["campaign_specs"] == CANDIDATES and body["selected_campaign"] == 0
        assert [step["id"] for step in body["steps"]][:2] == ["literature_node", "campaign_planner_node"]
