from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.graph.workflow as workflow
import app.main as main

SPECS = [
    {"statement": "first", "dataset": "breast_cancer", "models": ["A"], "params": {}},
    {"statement": "second", "dataset": "customer_churn", "models": ["A"], "params": {"A": {"C": 2}}},
    {"statement": "third", "dataset": "breast_cancer", "models": ["A"], "params": {}},
]
WAITING = {
    "hypotheses": ["first", "second", "third"],
    "experiment_specs": SPECS,
    "approval_status": "",
}


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
def graph(monkeypatch):
    fake = FakeGraph(dict(WAITING))

    @contextmanager
    def opened():
        yield SimpleNamespace(setup=lambda: None)

    monkeypatch.setattr(workflow, "_open_graph", opened)
    monkeypatch.setattr(workflow, "_compile", lambda checkpointer: fake)
    monkeypatch.setattr(workflow, "read_error", lambda thread_id: "")
    return fake


def test_approving_stores_the_selected_hypothesis(graph):
    result = workflow.decide_plan("t", "Y", 1)
    assert graph.updates == [{"approval_status": "approved", "selected_hypothesis": 1}]
    assert result["status"] == "running"
    assert result["selected_hypothesis"] == 1


def test_the_decision_letter_is_case_insensitive(graph):
    assert workflow.decide_plan("t", " y ", 2)["selected_hypothesis"] == 2


@pytest.mark.parametrize("selected", [None, -1, 3, "1", True])
def test_approving_without_a_valid_selection_changes_nothing(graph, selected):
    with pytest.raises(ValueError):
        workflow.decide_plan("t", "Y", selected)
    assert graph.updates == []


def test_rejecting_needs_no_selection(graph):
    result = workflow.decide_plan("t", "N")
    assert graph.updates == [{"approval_status": "rejected"}]
    assert result["approval_status"] == "rejected"
    assert "selected_hypothesis" not in result


def test_a_second_decision_is_refused(graph):
    workflow.decide_plan("t", "Y", 0)
    with pytest.raises(RuntimeError, match="already decided"):
        workflow.decide_plan("t", "Y", 1)
    assert len(graph.updates) == 1


def test_a_thread_that_is_not_waiting_is_refused(graph):
    graph.next_nodes = ("experiment_node",)
    with pytest.raises(RuntimeError, match="not waiting"):
        workflow.decide_plan("t", "Y", 0)


def test_an_unknown_thread_is_refused(graph):
    graph.values = {}
    with pytest.raises(RuntimeError, match="not found"):
        workflow.decide_plan("t", "Y", 0)


def test_a_bad_decision_letter_is_refused(graph):
    with pytest.raises(RuntimeError, match="Y or N"):
        workflow.decide_plan("t", "maybe", 0)


def test_the_status_shows_the_specs_and_the_default_selection(graph):
    status = workflow.get_research("t")
    assert status["status"] == "paused"
    assert status["experiment_specs"] == SPECS
    assert status["selected_hypothesis"] == 0


def test_the_status_follows_the_selection(graph):
    workflow.decide_plan("t", "Y", 2)
    status = workflow.get_research("t")
    assert status["selected_hypothesis"] == 2
    assert status["status"] == "running"


@pytest.fixture
def client(graph, monkeypatch):
    queued = []
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: queued.append((task.name, args)))
    monkeypatch.setattr(main, "revoke_approval", lambda thread_id: queued.append(("revoked", thread_id)))
    test_client = TestClient(main.app)
    test_client.queued = queued
    return test_client


def approve(client, **body):
    return client.post("/approve_plan", json={"thread_id": "t", **body})


def test_the_endpoint_queues_the_resume_for_a_valid_choice(client, graph):
    response = approve(client, decision="Y", selected=1)
    assert response.status_code == 200
    assert response.json()["selected_hypothesis"] == 1
    assert client.queued == [("axiomforge.resume_research", ("t",))]


def test_the_endpoint_answers_422_without_a_selection(client, graph):
    response = approve(client, decision="Y")
    assert response.status_code == 422
    assert "selected" in response.json()["detail"]
    assert client.queued == []
    assert graph.updates == []


def test_the_endpoint_answers_422_for_an_out_of_range_choice(client):
    response = approve(client, decision="Y", selected=7)
    assert response.status_code == 422
    assert client.queued == []


def test_the_endpoint_does_not_queue_a_rejection(client):
    response = approve(client, decision="N")
    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"
    assert client.queued == []


def test_the_endpoint_refuses_a_second_decision(client):
    assert approve(client, decision="Y", selected=0).status_code == 200
    again = approve(client, decision="Y", selected=1)
    assert again.status_code == 409
    assert "already decided" in again.json()["detail"]
    assert len(client.queued) == 1


@pytest.mark.parametrize(
    ("setup", "decision", "status", "text"),
    [
        ("unknown", "Y", 404, "not found"),
        ("busy", "Y", 409, "not waiting"),
        ("decided", "Y", 409, "already decided"),
        ("waiting", "maybe", 422, "Y or N"),
    ],
)
def test_each_refusal_has_its_own_status(client, graph, setup, decision, status, text):
    if setup == "unknown":
        graph.values = {}
    elif setup == "busy":
        graph.next_nodes = ("experiment_node",)
    elif setup == "decided":
        graph.values = {**graph.values, "approval_status": "approved"}
    response = approve(client, decision=decision, selected=0)
    assert response.status_code == status and text in response.json()["detail"]
    assert client.queued == []


@pytest.mark.parametrize(
    ("setup", "decision", "status"),
    [("unknown", "Y", 404), ("busy", "Y", 409), ("decided", "Y", 409), ("waiting", "maybe", 422)],
)
def test_the_refusals_carry_their_status_code(graph, setup, decision, status):
    if setup == "unknown":
        graph.values = {}
    elif setup == "busy":
        graph.next_nodes = ("experiment_node",)
    elif setup == "decided":
        graph.values = {**graph.values, "approval_status": "approved"}
    with pytest.raises(workflow.PlanDecisionError) as caught:
        workflow.decide_plan("t", decision, 0)
    assert caught.value.status_code == status and isinstance(caught.value, RuntimeError)


def test_a_real_runtime_failure_is_still_a_503(client, graph, monkeypatch):
    def broken(thread_id, decision, selected):
        raise RuntimeError("checkpoint database is down")

    monkeypatch.setattr(main, "decide_plan", broken)
    response = approve(client, decision="Y", selected=0)
    assert response.status_code == 503 and "checkpoint" in response.json()["detail"]
