import mlflow
import pytest

import app.tracking.mlflow_logger as logger_module
from app.graph.verifier import (
    instability_finding,
    performance_comparisons,
    seeded_rows,
    stability_decision,
    summarize_seed_runs,
    VERIFICATION_SEEDS,
)

SPLITS = len(VERIFICATION_SEEDS)
HI = ([0.90, 0.91, 0.89, 0.92, 0.90] * SPLITS)[:SPLITS]
LO = ([0.70, 0.72, 0.69, 0.71, 0.70] * SPLITS)[:SPLITS]


def row(model, value):
    return {
        "model": model,
        "accuracy": 0.9,
        "f1": value,
        "roc_auc": value,
        "pr_auc": value,
        "train_seconds": 0.1,
        "tn": 175.0,
        "fp": 5.0,
        "fn": 5.0,
        "tp": 15.0,
    }


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mlflow")
    patch = pytest.MonkeyPatch()
    patch.chdir(folder)
    uri = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"
    patch.setattr(logger_module, "MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield uri
    patch.undo()


def log_run(verdict=None):
    runs = [[row("Hi", HI[i]), row("Lo", LO[i])] for i in range(SPLITS)]
    summary = summarize_seed_runs(runs)
    decision = stability_decision(runs)
    decision["instability"] = instability_finding(summary)
    decision["performance"] = performance_comparisons(runs, 1000.0)
    if verdict is not None:
        decision["hypothesis"] = {"claim": None, "verdict": verdict, "evidence": {}}
    run_id = logger_module.log_verified_comparison(
        seeded_rows(runs),
        summary,
        decision,
        prompt_version="experiment-v7",
        model="gpt-4o",
        critic_rounds=0,
        hypothesis="Hi has a higher ROC-AUC than Lo",
        dataset={"dataset": "d", "samples": 1000.0, "features": 20.0, "negative_ratio": 0.9, "positive_ratio": 0.1},
        spec={"dataset": "imbalanced", "params": {}},
    )
    return mlflow.get_run(run_id)


def test_the_parent_run_carries_the_verified_summary_and_the_decision(store):
    run = log_run(verdict="supported")
    assert run.data.params["status"] == "Verified"
    assert run.data.params["prompt_version"] == "experiment-v7"
    assert run.data.params["seeds"] == ",".join(str(seed) for seed in VERIFICATION_SEEDS)
    assert run.data.metrics["Hi/roc_auc_mean"] == pytest.approx(sum(HI) / SPLITS)
    assert "Hi/roc_auc_std" in run.data.metrics and "Lo/roc_auc_variance" in run.data.metrics
    assert run.data.metrics["unstable"] == 0.0
    assert run.data.tags["outcome"] in {"tie", "winner"}


def test_the_hypothesis_verdict_is_a_tag(store):
    assert log_run(verdict="supported").data.tags["hypothesis_verdict"] == "supported"
    assert log_run(verdict="contradicted").data.tags["hypothesis_verdict"] == "contradicted"


def test_a_decision_without_a_verdict_is_logged_as_untested(store):
    assert log_run().data.tags["hypothesis_verdict"] == "untested"


def test_every_split_becomes_a_nested_run_with_its_seed(store):
    run = log_run(verdict="supported")
    experiment = mlflow.get_experiment_by_name("axiomforge")
    children = mlflow.search_runs(
        [experiment.experiment_id],
        filter_string=f"tags.mlflow.parentRunId = '{run.info.run_id}'",
    )
    assert len(children) == 2 * SPLITS
    assert children["params.model"].value_counts().to_dict() == {"Hi": SPLITS, "Lo": SPLITS}
    assert sorted(children["params.seed"].unique(), key=int) == [str(seed) for seed in sorted(VERIFICATION_SEEDS)]
