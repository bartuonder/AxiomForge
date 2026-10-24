import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.campaign.service as service
import app.campaign.store as store
import app.main as main
import app.tasks as tasks
from app.campaign.demos import demo_spec
from app.datasets import benchmark_keys

KEYS = benchmark_keys()[:7]


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    return tmp_path / "campaigns"


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: calls.append((task.name, args)))
    return calls


@pytest.fixture
def client(queued):
    return TestClient(main.app)


def test_starting_a_demo_stores_a_queued_campaign_and_enqueues_its_validated_spec(client, queued):
    response = client.post("/start_campaign", json={"demo": "grinsztajn-2022"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    name, (campaign_id, spec) = queued[0]
    assert name == "axiomforge.run_campaign" and campaign_id == body["campaign_id"]
    assert spec["datasets"] == benchmark_keys() and spec["claims"][0]["id"] == "C1" and spec["params"] == {}
    assert store.load_state(campaign_id)["status"] == "queued"


def test_the_datasets_of_the_request_replace_the_ones_of_the_demo(client, queued):
    client.post("/start_campaign", json={"demo": "grinsztajn-2022", "datasets": KEYS})
    assert queued[0][1][1]["datasets"] == KEYS
    assert list(store.load_state(queued[0][1][0])["datasets"]) == KEYS


def test_a_specification_can_be_posted_instead_of_a_demo(client, queued):
    spec = {**demo_spec("grinsztajn-2022"), "title": "Mine"}
    response = client.post("/start_campaign", json={"spec": spec})
    assert response.status_code == 200 and queued[0][1][1]["title"] == "Mine"


@pytest.mark.parametrize("body", [{}, {"demo": "grinsztajn-2022", "spec": {}}])
def test_exactly_one_of_demo_and_spec_is_required(client, queued, body):
    response = client.post("/start_campaign", json=body)
    assert response.status_code == 422 and "exactly one of demo and spec" in response.json()["detail"]
    assert queued == []


def test_an_unknown_demo_or_an_invalid_spec_is_refused_without_storing_anything(client, queued, root):
    response = client.post("/start_campaign", json={"demo": "nope"})
    assert response.status_code == 422 and "available: grinsztajn-2022" in response.json()["detail"]
    response = client.post("/start_campaign", json={"spec": {"title": "x"}})
    assert response.status_code == 422
    response = client.post("/start_campaign", json={"demo": "grinsztajn-2022", "datasets": ["tb_credit", "unknown"]})
    assert response.status_code == 422 and "unknown datasets: unknown" in response.json()["detail"]
    assert queued == [] and not root.exists()


def test_an_unavailable_queue_marks_the_stored_campaign_failed(monkeypatch, root):
    def down(task, *args):
        raise HTTPException(status_code=503, detail="task queue is unavailable: no broker")

    monkeypatch.setattr(main, "_enqueue", down)
    response = TestClient(main.app).post("/start_campaign", json={"demo": "grinsztajn-2022"})
    assert response.status_code == 503 and "no broker" in response.json()["detail"]
    [campaign_id] = store.list_campaigns()
    state = store.load_state(campaign_id)
    assert state["status"] == "failed" and "no broker" in state["error"]


def test_the_status_of_a_campaign_is_its_stored_state(client):
    campaign_id, _ = service.queue_campaign(demo_spec("grinsztajn-2022"))
    response = client.get(f"/campaign/{campaign_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued" and response.json()["id"] == campaign_id


def test_an_unknown_or_malformed_campaign_id_is_not_found_or_refused(client):
    assert client.get("/campaign/ghost").status_code == 404
    assert client.get("/campaign/ghost/report").status_code == 404
    response = client.get("/campaign/bad id")
    assert response.status_code == 400 and response.json()["detail"] == "invalid campaign id"
    assert client.get("/campaign/bad id/report").status_code == 400


def test_a_report_that_is_not_ready_is_not_found(client):
    campaign_id, _ = service.queue_campaign(demo_spec("grinsztajn-2022"))
    response = client.get(f"/campaign/{campaign_id}/report")
    assert response.status_code == 404 and response.json()["detail"] == "report not ready"


def test_a_finished_campaign_gives_its_report_and_ledger(client):
    campaign_id, spec = service.queue_campaign(demo_spec("grinsztajn-2022"))
    store.save_artifacts(campaign_id, "# Report\n", [{"id": "E1", "kind": "dataset"}], {}, {})
    assert client.get(f"/campaign/{campaign_id}/report").json() == {"markdown": "# Report\n", "ledger": [{"id": "E1", "kind": "dataset"}]}


def test_stored_campaigns_are_listed(client):
    assert client.get("/campaigns").json() == {"campaigns": []}
    first, _ = service.queue_campaign(demo_spec("grinsztajn-2022"))
    second, _ = service.queue_campaign(demo_spec("grinsztajn-2022"))
    assert client.get("/campaigns").json() == {"campaigns": sorted([first, second])}


def test_the_celery_task_executes_the_campaign_under_the_queued_id(monkeypatch):
    seen = []
    monkeypatch.setattr(tasks, "execute_campaign", lambda spec, campaign_id: seen.append((spec, campaign_id)))
    tasks.run_campaign_task("abc", {"title": "x"})
    assert seen == [({"title": "x"}, "abc")]
    assert tasks.run_campaign_task.name == "axiomforge.run_campaign"
