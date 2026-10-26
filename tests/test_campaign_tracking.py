import mlflow
import pytest

import app.campaign.tracking as tracking
from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report
from app.datasets import benchmark_keys

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Trees beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc"], "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
]
SOURCE = {"title": "Why do tree-based models still outperform deep learning on tabular data?", "citation": "Grinsztajn et al., NeurIPS 2022", "url": "https://arxiv.org/abs/2207.08815"}
SPEC = {"title": "Trees against neural networks", "models": MODELS, "params": {"MLP": {"alpha": 0.01}}, "claims": CLAIMS, "source": SOURCE}
KEYS = benchmark_keys()
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80, "MLP__default": 0.84}


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mlflow_campaign")
    patch = pytest.MonkeyPatch()
    patch.chdir(folder)
    uri = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"
    patch.setattr(tracking, "MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield uri
    patch.undo()


def summary(shift):
    return {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}


def outcome(keys=KEYS, failed=None):
    return {
        "order": list(keys) + list(failed or {}),
        "datasets": {
            key: {
                "summary": summary(0.001 * index),
                "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
                "seconds": 12.5 + index,
                "attempts": 1,
                "script": f"script of {key}",
            }
            for index, key in enumerate(keys)
        },
        "failed": failed or {},
    }


def log(campaign_id="abc", spec=SPEC, **kwargs):
    data = outcome(**kwargs)
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    run_id = tracking.log_campaign(campaign_id, spec, data, analysis, markdown, ledger, "completed")
    return mlflow.get_run(run_id), analysis, ledger


def children(run):
    experiment = mlflow.get_experiment_by_name(tracking.EXPERIMENT)
    return mlflow.search_runs(experiment_ids=[experiment.experiment_id], filter_string=f"tags.mlflow.parentRunId = '{run.info.run_id}'")


def test_one_parent_run_per_campaign_in_its_own_experiment(store):
    run, _, _ = log("first")
    assert run.data.tags["mlflow.runName"] == "Campaign Run first"
    assert run.data.tags["run_type"] == "campaign" and run.data.tags["status"] == "completed"
    assert run.data.tags["title"] == "Trees against neural networks"
    assert mlflow.get_experiment(run.info.experiment_id).name == "axiomforge-campaigns"


def test_the_parent_run_records_what_was_run(store):
    run, _, _ = log("params")
    params = run.data.params
    assert params["campaign_id"] == "params" and params["models"] == ",".join(MODELS)
    assert params["datasets_requested"] == ",".join(KEYS) and params["datasets_finished"] == ",".join(KEYS)
    assert params.get("datasets_failed", "") == ""
    assert params["source_citation"] == "Grinsztajn et al., NeurIPS 2022" and params["source_url"] == "https://arxiv.org/abs/2207.08815"
    assert run.data.metrics["datasets_finished"] == 9.0 and run.data.metrics["datasets_failed"] == 0.0
    assert run.data.metrics["enough_for_tests"] == 1.0


def test_friedman_statistics_and_mean_ranks_are_metrics(store):
    run, analysis, _ = log("friedman")
    metrics = run.data.metrics
    result = analysis["friedman"]["roc_auc"]
    assert metrics["friedman/roc_auc/statistic"] == pytest.approx(result["statistic"])
    assert metrics["friedman/roc_auc/p_value"] == pytest.approx(result["p_value"])
    assert metrics["friedman/roc_auc/testable"] == 1.0 and metrics["friedman/roc_auc/datasets"] == 9.0
    assert metrics["friedman/roc_auc/mean_rank/HistGradientBoosting"] == pytest.approx(1.0)
    assert metrics["friedman/roc_auc/mean_rank/LogisticRegression"] == pytest.approx(4.0)


def test_wilcoxon_results_are_logged_for_every_pair_and_metric(store):
    run, analysis, _ = log("wilcoxon")
    metrics = run.data.metrics
    row = next(item for item in analysis["pairwise"]["roc_auc"] if item["a"] == "RandomForest" and item["b"] == "MLP")
    prefix = "wilcoxon/roc_auc/RandomForest__vs__MLP"
    assert metrics[f"{prefix}/p_value"] == pytest.approx(row["p_value"])
    assert metrics[f"{prefix}/adjusted_p_value"] == pytest.approx(row["adjusted_p_value"])
    assert metrics[f"{prefix}/wins"] == 9.0 and metrics[f"{prefix}/losses"] == 0.0
    assert metrics[f"{prefix}/median_difference"] == pytest.approx(row["median_difference"])
    assert metrics[f"{prefix}/rank_biserial"] == pytest.approx(1.0)
    assert len([name for name in metrics if name.startswith("wilcoxon/") and name.endswith("/p_value")]) == 18


def test_claim_verdicts_and_their_statistics_are_tags_and_metrics(store):
    run, analysis, _ = log("claims")
    assert run.data.tags["verdict/C1"] == "replicated"
    assert run.data.tags["claim/C1/roc_auc/verdict"] == "replicated"
    row = analysis["claims"][0]["rows"][0]
    assert run.data.metrics["claim/C1/roc_auc/adjusted_p_value"] == pytest.approx(row["adjusted_p_value"])
    assert run.data.metrics["claim/C1/pr_auc/p_value"] > 0
    assert run.data.metrics["claim/C1/roc_auc/wins"] == 9.0


def test_the_leaders_are_tagged_per_metric_and_overall(store):
    run, _, _ = log("leaders")
    assert run.data.tags["leader_roc_auc"] == "HistGradientBoosting"
    assert run.data.tags["leader_pr_auc"] == "HistGradientBoosting" and run.data.tags["leader_f1"] == "HistGradientBoosting"
    assert run.data.tags["overall_best"] == "HistGradientBoosting"


def test_parameter_effects_are_logged_with_their_count(store):
    run, analysis, _ = log("effects")
    assert run.data.metrics["significant_parameter_effects"] == float(sum(1 for item in analysis["parameter_effects"] if item["significant"]))
    assert run.data.metrics["effect/MLP/roc_auc/median_difference"] == pytest.approx(0.01)
    assert "effect/MLP/roc_auc/adjusted_p_value" in run.data.metrics
    assert run.data.metrics["effect/MLP/roc_auc/adjusted_p_value_all"] == pytest.approx(run.data.metrics["effect/MLP/roc_auc/adjusted_p_value"])
    assert run.data.metrics["significant_parameter_effects_all"] == float(sum(1 for item in analysis["parameter_effects"] if item["significant_all"]))


def test_each_dataset_is_a_nested_run_with_its_means_and_timing(store):
    run, _, _ = log("nested")
    nested = children(run)
    assert sorted(nested["tags.mlflow.runName"]) == sorted(KEYS)
    first = nested[nested["tags.mlflow.runName"] == KEYS[1]].iloc[0]
    assert first["params.dataset"] == KEYS[1] and first["tags.run_type"] == "campaign_dataset"
    assert first["metrics.seconds"] == pytest.approx(13.5) and first["metrics.attempts"] == 1.0
    assert first["metrics.RandomForest/roc_auc_mean"] == pytest.approx(0.901)
    assert first["metrics.MLP__default/f1_mean"] == pytest.approx(0.841)


def test_a_failed_dataset_gets_a_failed_nested_run_and_is_counted(store):
    run, _, _ = log("failed", keys=KEYS[:8], failed={KEYS[8]: {"error": "OutOfMemory", "attempts": 2}})
    assert run.data.params["datasets_failed"] == KEYS[8] and run.data.metrics["datasets_failed"] == 1.0
    nested = children(run)
    bad = nested[nested["tags.mlflow.runName"] == KEYS[8]].iloc[0]
    assert bad["tags.failed"] == "true" and bad["tags.error"] == "OutOfMemory" and bad["metrics.attempts"] == 2.0
    assert len(nested) == 9


def test_report_and_ledger_are_artifacts(store):
    run, _, ledger = log("artifacts")
    client = mlflow.MlflowClient()
    names = sorted(item.path for item in client.list_artifacts(run.info.run_id))
    assert names == ["ledger.json", "report.md"]
    assert run.data.metrics["ledger_entries"] == float(len(ledger))


def test_an_unreachable_artifact_store_does_not_lose_the_metrics(store, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("artifact store unreachable")

    monkeypatch.setattr(tracking.mlflow, "log_text", broken)
    run, _, _ = log("noartifacts")
    assert run.data.tags["verdict/C1"] == "replicated" and run.info.status == "FINISHED"


def test_a_campaign_where_nothing_finished_is_logged_without_statistics(store):
    failed = {key: {"error": "boom", "attempts": 2} for key in KEYS[:2]}
    spec = {**SPEC, "datasets": KEYS[:2]}
    data = {"order": list(failed), "datasets": {}, "failed": failed}
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    run = mlflow.get_run(tracking.log_campaign("none", spec, data, analysis, markdown, ledger, "completed"))
    assert "no dataset finished" in run.data.tags["analysis_error"]
    assert run.data.metrics["datasets_finished"] == 0.0 and run.data.metrics["datasets_failed"] == 2.0
    assert not any(name.startswith(("friedman/", "wilcoxon/")) for name in run.data.metrics)
    assert "overall_best" not in run.data.tags


def test_too_few_datasets_log_the_friedman_ranks_but_no_p_values(store):
    run, _, _ = log("few", keys=KEYS[:4])
    assert run.data.metrics["enough_for_tests"] == 0.0
    assert run.data.metrics["friedman/roc_auc/testable"] == 0.0
    assert "friedman/roc_auc/p_value" not in run.data.metrics
    assert "friedman/roc_auc/mean_rank/MLP" in run.data.metrics
    assert not any(name.endswith("/p_value") and name.startswith("wilcoxon/") for name in run.data.metrics)
    assert run.data.tags["verdict/C1"] == "not_testable"


def test_the_leaders_follow_the_best_mean_rank():
    analysis = {"friedman": {"roc_auc": {"mean_ranks": {"A": 2.0, "B": 1.0}}, "f1": {"mean_ranks": {"A": 1.0, "B": 2.0}}, "pr_auc": {"mean_ranks": {"A": 1.0, "B": 2.0}}}}
    assert tracking.metric_leaders(analysis) == {"roc_auc": "B", "f1": "A", "pr_auc": "A"}
    assert tracking.overall_leader(analysis) == "A"
    assert tracking.overall_leader({}) is None
    assert tracking.metric_leaders({}) == {}


def test_a_tie_in_rank_goes_to_the_first_name_alphabetically():
    analysis = {"friedman": {"roc_auc": {"mean_ranks": {"B": 1.5, "A": 1.5}}}}
    assert tracking.metric_leaders(analysis) == {"roc_auc": "A"}
    assert tracking.overall_leader(analysis) == "A"


def test_only_significant_parameter_effects_are_counted(store):
    data = outcome()
    for record in data["datasets"].values():
        record["summary"]["MLP__default"] = dict(record["summary"]["MLP"])
    analysis = analyze_campaign(SPEC, data)
    markdown, ledger = render_report(SPEC, data, analysis)
    run = mlflow.get_run(tracking.log_campaign("noeffect", SPEC, data, analysis, markdown, ledger, "completed"))
    assert len(analysis["parameter_effects"]) == 3
    assert run.data.metrics["significant_parameter_effects"] == 0.0


def test_an_artifact_failure_is_logged(store, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise OSError("artifact store unreachable")

    monkeypatch.setattr(tracking.mlflow, "log_dict", broken)
    with caplog.at_level("ERROR", logger="axiomforge"):
        log("loggedfailure")
    assert any("campaign loggedfailure: artifacts could not be uploaded" in record.getMessage() and record.exc_info for record in caplog.records)
