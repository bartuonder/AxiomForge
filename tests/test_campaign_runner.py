import threading

import pytest

from app.campaign.protocol import build_script
from app.datasets import DATASETS
from app.campaign.runner import CSV_SCHEMA, MAX_ATTEMPTS, run_campaign, run_dataset
from app.sandbox.e2b_runner import SandboxCodeError
from app.seeds import SPLIT_SEEDS
from app.variants import expected_keys

MODELS = ["RandomForest", "LogisticRegression", "KNN"]
PARAMS = {"KNN": {"n_neighbors": 10}}
SPEC = {
    "models": MODELS,
    "params": PARAMS,
    "datasets": ["tb_credit", "tb_california", "tb_pol"],
}
BASE = {"RandomForest": 0.90, "LogisticRegression": 0.80, "KNN": 0.85, "KNN__default": 0.83}


def fake_output(dataset, models=MODELS, params=PARAMS, seeds=SPLIT_SEEDS, samples=6000, drop=None):
    lines = [f"dataset={dataset} samples={samples} features=10 negative_ratio=0.50 positive_ratio=0.50"]
    for index, seed in enumerate(seeds):
        for key in expected_keys(models, {"models": models, "params": params}):
            if drop == (key, index):
                continue
            value = BASE[key] + 0.001 * (index % 3)
            lines.append(
                f"model={key} accuracy={value:.4f} f1={value - 0.05:.4f} roc_auc={value:.4f} pr_auc={value - 0.02:.4f} "
                f"train_seconds=0.1000 tn=500 fp=100 fn=100 tp=500"
            )
    return "\n".join(lines)


def execute_for(dataset):
    return lambda script, schema: fake_output(dataset)


def test_one_dataset_finishes_with_its_summary_comparisons_and_effects():
    result = run_dataset("tb_credit", SPEC, execute_for("tb_credit"))
    assert result["status"] == "finished" and result["attempts"] == 1
    assert result["profile"]["dataset"] == "tb_credit" and result["profile"]["samples"] == 6000.0
    summary = result["summary"]
    assert set(k for k, v in summary.items() if isinstance(v, dict)) == {"RandomForest", "LogisticRegression", "KNN", "KNN__default"}
    assert summary["RandomForest"]["roc_auc_mean"] == pytest.approx(0.9 + 0.001 * 0.9, abs=1e-6)
    pairs = {(row["a"], row["b"], row["metric"]) for row in result["performance"]}
    assert ("RandomForest", "LogisticRegression", "roc_auc") in pairs
    assert not any("__default" in row["a"] + row["b"] for row in result["performance"])
    assert len(result["parameter_effects"]) == 3
    assert {row["model"] for row in result["parameter_effects"]} == {"KNN"}
    assert all(row["mean_difference"] > 0 for row in result["parameter_effects"] if row["metric"] == "roc_auc")


def test_the_script_sent_to_the_sandbox_is_the_protocol_script():
    seen = []

    def execute(script, schema):
        seen.append((script, schema))
        return fake_output("tb_pol")

    result = run_dataset("tb_pol", SPEC, execute)
    assert seen == [(build_script("tb_pol", MODELS, PARAMS), CSV_SCHEMA)]
    assert result["script"] == seen[0][0]


def test_a_failed_attempt_is_retried_and_the_second_one_counts():
    calls = []

    def execute(script, schema):
        calls.append(1)
        if len(calls) == 1:
            raise SandboxCodeError("ValueError: boom")
        return fake_output("tb_credit")

    result = run_dataset("tb_credit", SPEC, execute)
    assert result["status"] == "finished" and result["attempts"] == 2 and len(calls) == 2


def test_a_dataset_that_keeps_failing_is_reported_with_its_error():
    def execute(script, schema):
        raise SandboxCodeError("KeyError: price")

    result = run_dataset("tb_credit", SPEC, execute)
    assert result == {"status": "failed", "dataset": "tb_credit", "attempts": MAX_ATTEMPTS, "error": "KeyError: price"}


def test_an_infrastructure_error_is_retried_too():
    calls = []

    def execute(script, schema):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("sandbox timed out")
        return fake_output("tb_credit")

    assert run_dataset("tb_credit", SPEC, execute)["status"] == "finished"


def test_a_missing_sandbox_key_stops_everything_at_once():
    def execute(script, schema):
        raise RuntimeError("E2B_API_KEY is missing")

    with pytest.raises(RuntimeError, match="E2B_API_KEY is missing"):
        run_dataset("tb_credit", SPEC, execute)
    with pytest.raises(RuntimeError, match="E2B_API_KEY is missing"):
        run_campaign(SPEC, execute)


def test_incomplete_output_counts_as_a_failed_attempt():
    outputs = [fake_output("tb_credit", drop=("KNN", 4)), fake_output("tb_credit")]
    result = run_dataset("tb_credit", SPEC, lambda script, schema: outputs.pop(0))
    assert result["status"] == "finished" and result["attempts"] == 2


def test_incomplete_output_that_never_improves_fails_with_the_counts():
    result = run_dataset("tb_credit", SPEC, lambda script, schema: fake_output("tb_credit", drop=("KNN__default", 0)))
    assert result["status"] == "failed"
    assert "incomplete output" in result["error"] and "KNN__default" in result["error"]


def test_output_without_a_dataset_line_fails():
    result = run_dataset("tb_credit", SPEC, lambda script, schema: "model=RandomForest accuracy=0.9")
    assert result["status"] == "failed"
    assert "dataset profile missing" in result["error"]


def test_the_campaign_runs_every_dataset_and_keeps_the_spec_order():
    def execute(script, schema):
        dataset = next(key for key in SPEC["datasets"] if DATASETS[key]["config"] in script)
        return fake_output(dataset)

    outcome = run_campaign(SPEC, execute, workers=3)
    assert outcome["order"] == ["tb_credit", "tb_california", "tb_pol"]
    assert list(outcome["datasets"]) == ["tb_credit", "tb_california", "tb_pol"]
    assert outcome["failed"] == {}


def test_one_failing_dataset_does_not_stop_the_others():
    def execute(script, schema):
        if DATASETS["tb_california"]["config"] in script:
            raise SandboxCodeError("OutOfMemory")
        name = "tb_credit" if DATASETS["tb_credit"]["config"] in script else "tb_pol"
        return fake_output(name)

    outcome = run_campaign(SPEC, execute, workers=2)
    assert list(outcome["datasets"]) == ["tb_credit", "tb_pol"]
    assert outcome["failed"] == {"tb_california": {"error": "OutOfMemory", "attempts": MAX_ATTEMPTS}}


def test_datasets_run_in_parallel_up_to_the_worker_limit():
    barrier = threading.Barrier(3, timeout=5)

    def execute(script, schema):
        barrier.wait()
        return fake_output("tb_credit")

    outcome = run_campaign(SPEC, execute, workers=3)
    assert len(outcome["datasets"]) == 3


def test_a_single_worker_runs_them_one_after_another():
    active, peak = [0], [0]
    lock = threading.Lock()

    def execute(script, schema):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            return fake_output("tb_credit")
        finally:
            with lock:
                active[0] -= 1

    run_campaign(SPEC, execute, workers=1)
    assert peak[0] == 1


def test_progress_events_report_running_and_the_result_for_every_dataset():
    events = []
    lock = threading.Lock()

    def on_update(dataset, payload):
        with lock:
            events.append((dataset, payload["status"]))

    run_campaign(SPEC, execute_for("tb_credit"), workers=1, on_update=on_update)
    assert events == [
        ("tb_credit", "running"), ("tb_credit", "finished"),
        ("tb_california", "running"), ("tb_california", "finished"),
        ("tb_pol", "running"), ("tb_pol", "finished"),
    ]


def test_a_failed_dataset_is_announced_as_failed():
    events = []

    def execute(script, schema):
        raise SandboxCodeError("x")

    run_campaign({**SPEC, "datasets": ["tb_credit", "tb_pol"]}, execute, workers=1, on_update=lambda d, p: events.append((d, p["status"])))
    assert events == [("tb_credit", "running"), ("tb_credit", "failed"), ("tb_pol", "running"), ("tb_pol", "failed")]


def test_custom_seeds_and_attempts_are_honoured():
    seeds = (1, 2, 3)
    calls = []

    def execute(script, schema):
        calls.append(script)
        return fake_output("tb_credit", seeds=seeds)

    result = run_dataset("tb_credit", SPEC, execute, seeds=seeds)
    assert "seeds = [1, 2, 3]" in calls[0] and result["status"] == "finished"
    failing = run_dataset("tb_credit", SPEC, lambda s, c: (_ for _ in ()).throw(SandboxCodeError("e")), attempts=3)
    assert failing["attempts"] == 3


def test_a_campaign_without_parameters_has_no_effects():
    plain = {**SPEC, "params": {}}
    result = run_dataset("tb_credit", plain, lambda s, c: fake_output("tb_credit", params={}))
    assert result["parameter_effects"] == []
    assert "KNN__default" not in result["summary"]


def test_zero_workers_still_runs_the_campaign_one_at_a_time():
    outcome = run_campaign(SPEC, execute_for("tb_credit"), workers=0)
    assert len(outcome["datasets"]) == 3


def test_the_campaign_passes_its_attempt_limit_down_to_every_dataset():
    def execute(script, schema):
        raise SandboxCodeError("bad")

    outcome = run_campaign({**SPEC, "datasets": ["tb_credit", "tb_pol"]}, execute, workers=1, attempts=1)
    assert [item["attempts"] for item in outcome["failed"].values()] == [1, 1]
