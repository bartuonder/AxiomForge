import json

import pytest
from fastapi.testclient import TestClient

import app.campaign.service as service
import app.campaign.store as store
import app.main as main
from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report
from app.datasets import benchmark_keys

KEYS = benchmark_keys()
MODELS = ["RandomForest", "MLP"]
CLAIMS = [{"id": "C1", "statement": "Forests beat nets", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"], "subject": ["RandomForest"], "other": ["MLP"]}]
SPEC = {"title": "Forests against nets", "models": MODELS, "params": {}, "tuning": {}, "claims": CLAIMS, "datasets": KEYS, "source": {}}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    return tmp_path / "campaigns"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: None)
    return TestClient(main.app)


def finished_campaign(campaign_id="done", spec=SPEC, with_spec=True):
    data = {
        "order": KEYS,
        "datasets": {
            key: {
                "summary": {"RandomForest": {f"{m}_mean": 0.9 + 0.001 * i for m in ("roc_auc", "pr_auc", "f1")}, "MLP": {f"{m}_mean": 0.8 for m in ("roc_auc", "pr_auc", "f1")}},
                "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
                "seconds": 1.0,
                "attempts": 1,
                "script": key,
            }
            for i, key in enumerate(KEYS)
        },
        "failed": {},
    }
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    store.save_state(campaign_id, {"id": campaign_id, "title": spec["title"], "status": "completed", "datasets": {key: {"status": "finished"} for key in KEYS}, "origin": "console"})
    store.save_artifacts(campaign_id, markdown, ledger, analysis, {})
    if with_spec:
        store.save_spec(campaign_id, spec)


class TestSpecStorage:
    def test_a_spec_round_trips(self):
        store.save_spec("abc", SPEC)
        assert store.load_spec("abc") == SPEC

    def test_a_missing_spec_is_none(self):
        assert store.load_spec("nothing") is None

    def test_an_unsafe_id_is_refused(self):
        with pytest.raises(store.CampaignStoreError):
            store.save_spec("../x", SPEC)

    def test_the_spec_is_written_next_to_the_state(self, root):
        store.save_spec("abc", SPEC)
        assert json.loads((root / "abc" / "spec.json").read_text(encoding="utf-8")) == SPEC

    def test_queueing_a_campaign_stores_its_spec(self):
        campaign_id, spec = service.queue_campaign({**SPEC, "datasets": KEYS[:7]})
        assert store.load_spec(campaign_id) == spec

    def test_queueing_once_stores_the_spec_only_the_first_time(self):
        spec, created = service.queue_once("g-1", {**SPEC, "datasets": KEYS[:7]})
        assert created and store.load_spec("g-1") == spec
        store.save_spec("g-1", {"changed": True})
        service.queue_once("g-1", {**SPEC, "datasets": KEYS[:7]})
        assert store.load_spec("g-1") == {"changed": True}

    def test_executing_a_campaign_stores_its_spec(self):
        spec = {**SPEC, "datasets": KEYS[:2]}
        service.execute_campaign(spec, "run-1", execute=lambda script, schema: (_ for _ in ()).throw(RuntimeError("stop")), attempts=1)
        assert store.load_spec("run-1")["title"] == "Forests against nets"


class TestOrigin:
    def test_the_api_marks_its_campaigns(self):
        campaign_id, _ = service.queue_campaign({**SPEC, "datasets": KEYS[:7]})
        assert store.load_state(campaign_id)["origin"] == "api"

    def test_the_origin_can_be_given(self):
        campaign_id, _ = service.queue_campaign({**SPEC, "datasets": KEYS[:7]}, origin="console")
        assert store.load_state(campaign_id)["origin"] == "console"

    def test_the_graph_marks_its_campaigns(self):
        service.queue_once("g-2", {**SPEC, "datasets": KEYS[:7]}, origin="console")
        assert store.load_state("g-2")["origin"] == "console"

    def test_a_run_from_the_command_line_is_marked_cli(self):
        spec = {**SPEC, "datasets": KEYS[:2]}
        state = service.execute_campaign(spec, "cli-1", execute=lambda script, schema: (_ for _ in ()).throw(RuntimeError("stop")), attempts=1)
        assert state["origin"] == "cli"

    def test_a_queued_campaign_keeps_its_origin_when_it_runs(self):
        spec = {**SPEC, "datasets": KEYS[:2]}
        service.queue_once("q-1", spec, origin="console")
        state = service.execute_campaign(spec, "q-1", execute=lambda script, schema: (_ for _ in ()).throw(RuntimeError("stop")), attempts=1)
        assert state["origin"] == "console"

    def test_the_list_carries_the_origin(self):
        assert service.campaign_summary({"id": "a", "status": "completed", "origin": "console"})["origin"] == "console"
        assert service.campaign_summary({"id": "a", "status": "completed"})["origin"] == "unknown"

    def test_the_list_endpoint_shows_it(self, client):
        finished_campaign("done")
        assert client.get("/campaigns").json()["items"][0]["origin"] == "console"


class TestEndpoint:
    def test_a_finished_campaign_has_a_summary(self, client):
        finished_campaign()
        body = client.get("/campaign/done/summary").json()
        assert body["language"] == "tr" and body["title"] == "Forests against nets"
        assert body["claims"][0]["verdict"]["label"] == "Doğrulandı"
        assert body["claims"][0]["headline"] == "Random Forest, Yapay sinir ağı (MLP) modelinden daha iyi çıktı"

    def test_the_language_can_be_chosen(self, client):
        finished_campaign()
        body = client.get("/campaign/done/summary", params={"lang": "en"}).json()
        assert body["language"] == "en" and body["claims"][0]["verdict"]["label"] == "Confirmed"

    def test_an_unknown_language_is_a_422(self, client):
        finished_campaign()
        response = client.get("/campaign/done/summary", params={"lang": "de"})
        assert response.status_code == 422 and "language" in response.json()["detail"]

    def test_an_old_campaign_without_a_stored_spec_still_has_a_summary(self, client):
        finished_campaign(with_spec=False)
        body = client.get("/campaign/done/summary").json()
        assert body["title"] == "Forests against nets" and body["claims"][0]["verdict"]["code"] == "replicated"

    def test_a_running_campaign_has_progress_but_no_claims(self, client):
        store.save_state("busy", {"id": "busy", "title": "T", "status": "running", "datasets": {"tb_credit": {"status": "finished"}, "tb_pol": {"status": "running"}}})
        body = client.get("/campaign/busy/summary").json()
        assert body["status"]["code"] == "running" and body["progress"]["percent"] == 50 and body["claims"] == []

    def test_an_unknown_campaign_is_a_404(self, client):
        assert client.get("/campaign/nothing/summary").status_code == 404

    def test_a_bad_id_is_a_400(self, client):
        assert client.get("/campaign/bad id/summary").status_code == 400

    def test_a_failed_campaign_is_explained(self, client):
        store.save_state("bad", {"id": "bad", "title": "T", "status": "failed", "error": "RuntimeError: boom", "datasets": {}})
        body = client.get("/campaign/bad/summary").json()
        assert body["status"]["code"] == "failed" and body["error"] == "RuntimeError: boom"


def test_the_console_flow_marks_its_campaign_as_console(monkeypatch):
    import app.graph.campaign_nodes as campaign_nodes

    monkeypatch.setattr(campaign_nodes, "_enqueue_campaign", lambda campaign_id, spec, thread_id: None)
    update = campaign_nodes.campaign_dispatch_node({"campaign_spec": {**SPEC, "datasets": KEYS[:7]}}, {"configurable": {"thread_id": "t-1"}})
    assert store.load_state(update["campaign_id"])["origin"] == "console"


def test_the_endpoint_prefers_the_stored_specification_for_the_title(client):
    finished_campaign()
    store.save_spec("done", {**SPEC, "title": "A better title"})
    assert client.get("/campaign/done/summary").json()["title"] == "A better title"


class TestGlossaryAndListSentence:
    def test_the_glossary_endpoint_serves_the_terms(self, client):
        from app.campaign.vocabulary import GLOSSARY

        assert client.get("/glossary").json() == {"language": "tr", "terms": GLOSSARY["tr"]}
        assert client.get("/glossary", params={"lang": "en"}).json() == {"language": "en", "terms": GLOSSARY["en"]}

    def test_an_unknown_glossary_language_is_a_422(self, client):
        assert client.get("/glossary", params={"lang": "de"}).status_code == 422

    def test_the_list_carries_the_first_claim_sentence(self):
        state = {"id": "a", "status": "completed", "verdicts": [{"id": "C1", "statement": "Trees beat nets", "verdict": "replicated"}]}
        assert service.campaign_summary(state)["statement"] == "Trees beat nets"
        assert service.campaign_summary({"id": "a", "status": "queued"})["statement"] == ""

    def test_the_list_verdicts_stay_small(self):
        state = {"id": "a", "status": "completed", "verdicts": [{"id": "C1", "statement": "Trees beat nets", "verdict": "replicated"}]}
        assert service.campaign_summary(state)["verdicts"] == [{"id": "C1", "verdict": "replicated"}]


class TestVocabularyEndpoint:
    def test_the_names_are_served(self, client):
        from app.campaign.vocabulary import DATASET_NAMES, METRIC_LABELS, MODEL_NAMES

        body = client.get("/vocabulary").json()
        assert body == {"language": "tr", "models": MODEL_NAMES["tr"], "datasets": DATASET_NAMES["tr"], "metrics": {key: value["name"] for key, value in METRIC_LABELS["tr"].items()}}

    def test_the_language_can_be_chosen(self, client):
        body = client.get("/vocabulary", params={"lang": "en"}).json()
        assert body["models"]["RandomForest"] == "Random forest" and body["metrics"]["roc_auc"] == "ROC-AUC"

    def test_an_unknown_language_is_a_422(self, client):
        assert client.get("/vocabulary", params={"lang": "de"}).status_code == 422
