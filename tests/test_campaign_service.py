import json
import threading

import pytest

import app.campaign.service as service
import app.campaign.store as store
from app.campaign.spec import CampaignSpecError
from app.datasets import DATASETS, benchmark_keys
from app.sandbox.e2b_runner import SandboxCodeError
from app.seeds import SPLIT_SEEDS
from app.variants import expected_keys

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
PARAMS = {"MLP": {"alpha": 0.01}}
KEYS = benchmark_keys()[:6]
SPEC = {
    "title": "Trees against neural networks",
    "models": MODELS,
    "params": PARAMS,
    "datasets": KEYS,
    "claims": [
        {"statement": "Tree-based models beat the MLP", "metric": "roc_auc", "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    ],
    "source": {"title": "Why do tree-based models still outperform deep learning on tabular data?", "citation": "Grinsztajn et al., NeurIPS 2022", "deviations": ["no search"]},
}
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80, "MLP__default": 0.84}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    return tmp_path / "campaigns"


def dataset_of(script):
    return next(key for key in KEYS if DATASETS[key]["config"] in script)


def fake_output(dataset, seeds=SPLIT_SEEDS):
    shift = 0.002 * KEYS.index(dataset)
    lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
    for _ in seeds:
        for key in expected_keys(MODELS, {"models": MODELS, "params": PARAMS}):
            value = BASE[key] + shift
            lines.append(
                f"model={key} accuracy={value:.4f} f1={value - 0.05:.4f} roc_auc={value:.4f} pr_auc={value - 0.02:.4f} "
                f"train_seconds=0.1000 tn=500 fp=100 fn=100 tp=500"
            )
    return "\n".join(lines)


def healthy(script, schema):
    return fake_output(dataset_of(script))


def test_a_campaign_runs_to_completion_and_stores_the_report_ledger_and_scripts(root):
    state = service.execute_campaign(SPEC, "abc", healthy, workers=2)
    assert state["status"] == "completed" and state["issues"] == []
    assert state["started"].endswith("+00:00") and state["finished"].endswith("+00:00")
    assert state["finished_datasets"] == 6 and state["failed_datasets"] == 0
    assert state["verdicts"] == [{"id": "C1", "statement": "Tree-based models beat the MLP", "verdict": "replicated"}]
    folder = root / "abc"
    assert "## Evidence ledger" in store.load_report("abc")
    assert json.loads((folder / "ledger.json").read_text(encoding="utf-8"))[0]["id"] == "E1"
    assert json.loads((folder / "analysis.json").read_text(encoding="utf-8"))["claims"][0]["verdict"] == "replicated"
    assert sorted(path.stem for path in (folder / "scripts").iterdir()) == sorted(KEYS)
    assert store.load_state("abc") == state | {"updated": store.load_state("abc")["updated"]}


def test_the_state_on_disk_follows_the_progress_of_each_dataset():
    seen = []

    def execute(script, schema):
        seen.append({key: item["status"] for key, item in store.load_state("abc")["datasets"].items()})
        return healthy(script, schema)

    service.execute_campaign(SPEC, "abc", execute, workers=1)
    assert seen[0] == {key: "running" if key == KEYS[0] else "queued" for key in KEYS}
    assert seen[-1][KEYS[-1]] == "running" and all(seen[-1][key] == "finished" for key in KEYS[:-1])
    final = store.load_state("abc")["datasets"]
    assert all(final[key]["status"] == "finished" and final[key]["attempts"] == 1 for key in KEYS)
    assert "script" not in final[KEYS[0]] and "summary" not in final[KEYS[0]]


def test_the_state_is_saved_before_any_dataset_starts(monkeypatch):
    saved = []
    real = store.save_state
    monkeypatch.setattr(service.store, "save_state", lambda campaign_id, state: (saved.append(json.loads(json.dumps(state))), real(campaign_id, state)))
    service.execute_campaign(SPEC, "abc", healthy, workers=1)
    assert saved[0]["status"] == "running"
    assert {item["status"] for item in saved[0]["datasets"].values()} == {"queued"}


def test_the_first_state_is_running_with_every_dataset_queued():
    seen = {}

    def execute(script, schema):
        seen.setdefault("first", store.load_state("abc"))
        return healthy(script, schema)

    service.execute_campaign(SPEC, "abc", execute, workers=1)
    assert seen["first"]["status"] == "running" and seen["first"]["title"] == "Trees against neural networks"
    assert seen["first"]["started"].endswith("+00:00") and "finished" not in seen["first"]


def test_a_failing_dataset_is_recorded_and_the_rest_still_gives_a_report():
    def execute(script, schema):
        if dataset_of(script) == KEYS[0]:
            raise SandboxCodeError("OutOfMemory")
        return healthy(script, schema)

    state = service.execute_campaign(SPEC, "abc", execute, workers=2)
    assert state["status"] == "completed"
    assert state["finished_datasets"] == 5 and state["failed_datasets"] == 1
    assert state["datasets"][KEYS[0]] == {"status": "failed", "attempts": service.MAX_ATTEMPTS, "error": "OutOfMemory"}
    assert state["verdicts"][0]["verdict"] == "not_testable"
    assert f"| failure | {KEYS[0]} |" in store.load_report("abc")


def test_a_campaign_where_nothing_finishes_still_stores_an_honest_report():
    def execute(script, schema):
        raise SandboxCodeError("boom")

    state = service.execute_campaign(SPEC, "abc", execute, workers=2, attempts=1)
    assert state["status"] == "completed" and state["finished_datasets"] == 0 and state["failed_datasets"] == 6
    assert state["verdicts"] == []
    assert [item["attempts"] for item in state["datasets"].values()] == [1] * 6
    assert "No claim could be assessed" in store.load_report("abc")
    assert store.load_state("abc")["status"] == "completed"


def test_a_report_with_traceability_issues_needs_review(monkeypatch):
    monkeypatch.setattr(service, "report_issues", lambda markdown, ledger: ["E9 is cited but not in the ledger"])
    state = service.execute_campaign(SPEC, "abc", healthy, workers=2)
    assert state["status"] == "needs_review" and state["issues"] == ["E9 is cited but not in the ledger"]
    assert store.load_report("abc") is not None


def test_an_unexpected_failure_marks_the_campaign_failed_and_keeps_the_error(monkeypatch):
    def broken(spec, outcome, analysis):
        raise ValueError("render exploded")

    monkeypatch.setattr(service, "render_report", broken)
    state = service.execute_campaign(SPEC, "abc", healthy, workers=2)
    assert state["status"] == "failed" and state["error"] == "ValueError: render exploded"
    assert state["finished"].endswith("+00:00")
    assert store.load_state("abc")["status"] == "failed"
    assert store.load_report("abc") is None


def test_a_missing_sandbox_key_fails_the_campaign_instead_of_retrying():
    calls = []

    def execute(script, schema):
        calls.append(dataset_of(script))
        raise SandboxCodeError("E2B_API_KEY is missing")

    state = service.execute_campaign(SPEC, "abc", execute, workers=1)
    assert state["status"] == "failed" and "E2B_API_KEY is missing" in state["error"]
    assert len(calls) == len(set(calls))


def test_the_split_seeds_given_to_the_service_reach_every_dataset():
    seeds = (3, 4)
    state = service.execute_campaign(SPEC, "abc", lambda script, schema: fake_output(dataset_of(script), seeds), workers=2, seeds=seeds)
    assert state["status"] == "completed" and state["finished_datasets"] == 6


def test_an_unexpected_failure_is_logged_with_the_campaign_id(monkeypatch, caplog):
    monkeypatch.setattr(service, "render_report", lambda spec, outcome, analysis: 1 / 0)
    with caplog.at_level("ERROR", logger="axiomforge"):
        service.execute_campaign(SPEC, "abc", healthy, workers=2)
    assert any("campaign abc failed" in record.getMessage() and record.exc_info for record in caplog.records)


def test_an_invalid_spec_is_refused_before_anything_is_stored(root):
    with pytest.raises(CampaignSpecError):
        service.execute_campaign({**SPEC, "models": ["RandomForest"]}, "abc", healthy)
    assert not root.exists()


def test_a_campaign_gets_a_fresh_id_when_none_is_given(root):
    first = service.execute_campaign(SPEC, execute=healthy, workers=2)
    second = service.execute_campaign(SPEC, execute=healthy, workers=2)
    assert first["id"] != second["id"]
    assert sorted(store.list_campaigns()) == sorted([first["id"], second["id"]])


def test_progress_updates_from_parallel_datasets_never_corrupt_the_state():
    barrier = threading.Barrier(3, timeout=10)

    def execute(script, schema):
        barrier.wait()
        return healthy(script, schema)

    state = service.execute_campaign(SPEC, "abc", execute, workers=3)
    assert state["status"] == "completed"
    assert all(item["status"] == "finished" for item in store.load_state("abc")["datasets"].values())


def test_only_progress_fields_reach_the_state():
    result = {"status": "finished", "attempts": 2, "seconds": 3.5, "script": "x", "summary": {}, "profile": {}, "error": "e"}
    assert service._progress(result) == {"status": "finished", "attempts": 2, "seconds": 3.5, "error": "e"}


def test_a_queued_campaign_is_stored_with_every_dataset_queued_before_it_runs():
    campaign_id, spec = service.queue_campaign(SPEC)
    state = store.load_state(campaign_id)
    assert state["status"] == "queued" and state["title"] == SPEC["title"]
    assert state["queued"].endswith("+00:00") and "started" not in state
    assert state["datasets"] == {key: {"status": "queued"} for key in KEYS}
    assert spec["datasets"] == KEYS and spec["claims"][0]["id"] == "C1"


def test_a_queued_campaign_gets_a_unique_id_each_time():
    first, _ = service.queue_campaign(SPEC)
    second, _ = service.queue_campaign(SPEC)
    assert first != second


def test_an_invalid_spec_is_not_queued(root):
    with pytest.raises(CampaignSpecError):
        service.queue_campaign({**SPEC, "claims": []})
    assert not root.exists()


def test_the_validated_spec_can_be_executed_under_the_queued_id():
    campaign_id, spec = service.queue_campaign(SPEC)
    state = service.execute_campaign(spec, campaign_id, healthy, workers=2)
    assert state["id"] == campaign_id and state["status"] == "completed"
    assert store.list_campaigns() == [campaign_id]


def test_a_rejected_campaign_keeps_its_datasets_and_records_the_reason():
    campaign_id, _ = service.queue_campaign(SPEC)
    service.reject_campaign(campaign_id, "task queue is unavailable")
    state = store.load_state(campaign_id)
    assert state["status"] == "failed" and state["error"] == "task queue is unavailable"
    assert state["finished"].endswith("+00:00") and set(state["datasets"]) == set(KEYS)


def test_rejecting_an_unknown_campaign_does_nothing(root):
    service.reject_campaign("ghost", "whatever")
    assert not root.exists()


def test_without_a_tracker_nothing_is_logged_and_no_run_id_is_stored():
    state = service.execute_campaign(SPEC, "abc", healthy, workers=2)
    assert "mlflow_run_id" not in state


def test_the_tracker_gets_the_finished_campaign_and_its_run_id_is_stored():
    seen = []

    def tracker(campaign_id, spec, outcome, analysis, markdown, ledger, status):
        seen.append((campaign_id, spec["title"], sorted(outcome["datasets"]), analysis["claims"][0]["verdict"], markdown.startswith("# "), ledger[0]["id"], status))
        return "run-123"

    state = service.execute_campaign(SPEC, "abc", healthy, workers=2, tracker=tracker)
    assert seen == [("abc", SPEC["title"], sorted(KEYS), "replicated", True, "E1", "completed")]
    assert state["mlflow_run_id"] == "run-123" and store.load_state("abc")["mlflow_run_id"] == "run-123"


def test_the_tracker_sees_the_review_status(monkeypatch):
    monkeypatch.setattr(service, "report_issues", lambda markdown, ledger: ["E9 is cited but not in the ledger"])
    statuses = []
    state = service.execute_campaign(SPEC, "abc", healthy, workers=2, tracker=lambda *args: statuses.append(args[-1]) or "r")
    assert statuses == ["needs_review"] and state["status"] == "needs_review"


def test_the_tracker_runs_after_the_artifacts_are_stored():
    seen = []

    def tracker(*args):
        seen.append(store.load_report("abc") is not None)
        return "r"

    service.execute_campaign(SPEC, "abc", healthy, workers=2, tracker=tracker)
    assert seen == [True]


def test_a_failing_tracker_does_not_fail_the_campaign_and_leaves_an_empty_run_id(caplog):
    def broken(*args):
        raise ConnectionError("mlflow is down")

    with caplog.at_level("ERROR", logger="axiomforge"):
        state = service.execute_campaign(SPEC, "abc", healthy, workers=2, tracker=broken)
    assert state["status"] == "completed" and state["mlflow_run_id"] == ""
    assert any("campaign abc: MLflow logging failed" in record.getMessage() and record.exc_info for record in caplog.records)
    assert store.load_report("abc") is not None


def test_a_campaign_that_fails_before_reporting_is_not_tracked(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "render_report", lambda spec, outcome, analysis: 1 / 0)
    state = service.execute_campaign(SPEC, "abc", healthy, workers=2, tracker=lambda *args: calls.append(args) or "r")
    assert state["status"] == "failed" and calls == [] and "mlflow_run_id" not in state


def test_the_summary_counts_datasets_and_keeps_the_verdicts():
    state = {
        "id": "abc",
        "title": "T",
        "status": "completed",
        "updated": "2026-10-24T10:00:00+00:00",
        "datasets": {"a": {"status": "finished"}, "b": {"status": "failed"}, "c": {"status": "finished"}, "d": {"status": "running"}},
        "verdicts": [{"id": "C1", "statement": "long statement", "verdict": "replicated"}],
        "issues": ["x"],
    }
    assert service.campaign_summary(state) == {
        "id": "abc",
        "title": "T",
        "status": "completed",
        "updated": "2026-10-24T10:00:00+00:00",
        "origin": "unknown",
        "statement": "long statement",
        "datasets": 4,
        "finished": 2,
        "failed": 1,
        "verdicts": [{"id": "C1", "verdict": "replicated"}],
    }


def test_the_summary_of_a_queued_campaign_has_no_verdicts_and_no_progress():
    campaign_id, _ = service.queue_campaign(SPEC)
    summary = service.campaign_summary(store.load_state(campaign_id))
    assert summary["status"] == "queued" and summary["datasets"] == 6
    assert summary["finished"] == 0 and summary["failed"] == 0 and summary["verdicts"] == []
    assert summary["title"] == SPEC["title"] and summary["updated"].endswith("+00:00")
