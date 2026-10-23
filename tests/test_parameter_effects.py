import pytest

import app.graph.nodes as nodes
from app.graph.verifier import (
    VERIFICATION_SEEDS,
    instability_finding,
    parameter_effects,
    performance_comparisons,
    stability_decision,
    summarize_seed_runs,
    without_baselines,
)

HI = [0.90, 0.91, 0.89, 0.92, 0.90, 0.91, 0.90, 0.89, 0.92, 0.91]
LO = [0.70, 0.72, 0.69, 0.71, 0.70, 0.73, 0.68, 0.70, 0.72, 0.71]
NEAR = [0.91, 0.90, 0.92, 0.91, 0.89, 0.92, 0.91, 0.90, 0.90, 0.92]
OTHER = [0.80, 0.82, 0.79, 0.81, 0.80, 0.83, 0.78, 0.80, 0.82, 0.81]
SPLITS = len(VERIFICATION_SEEDS)
WILD = ([0.95, 0.60, 0.97, 0.70, 0.99] * SPLITS)[:SPLITS]
STEADY = ([0.90, 0.91, 0.89, 0.92, 0.90] * SPLITS)[:SPLITS]
PARAMS = {"A": {"n_estimators": 300}}


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


def runs_for(series):
    length = len(next(iter(series.values())))
    return [[row(name, series[name][index]) for name in series] for index in range(length)]


def test_baseline_rows_are_removed_from_the_main_family():
    runs = runs_for({"A": HI, "A__default": LO, "B": OTHER})
    assert [item["model"] for item in without_baselines(runs)[0]] == ["A", "B"]


def test_a_significant_effect_is_reported_with_its_direction_and_size():
    effects = parameter_effects(runs_for({"A": HI, "A__default": LO, "B": OTHER}), 1000.0, PARAMS)
    assert [item["metric"] for item in effects] == ["roc_auc", "pr_auc", "f1"]
    first = effects[0]
    assert first["model"] == "A"
    assert first["params"] == {"n_estimators": 300}
    assert first["mean_difference"] > 0.15
    assert first["effect_size_dz"] > 0
    assert first["adjusted_p_value"] < 0.05
    assert first["significant"] is True


def test_a_worse_configuration_has_a_negative_difference():
    effects = parameter_effects(runs_for({"A": LO, "A__default": HI, "B": OTHER}), 1000.0, PARAMS)
    assert effects[0]["mean_difference"] < 0
    assert effects[0]["significant"] is True


def test_a_negligible_effect_is_not_significant():
    effects = parameter_effects(runs_for({"A": HI, "A__default": NEAR, "B": OTHER}), 1000.0, PARAMS)
    assert all(item["significant"] is False for item in effects)


def test_the_effect_family_is_corrected_together():
    effects = parameter_effects(runs_for({"A": HI, "A__default": LO, "B": OTHER}), 1000.0, PARAMS)
    assert all(item["adjusted_p_value"] >= item["p_value"] for item in effects)


def test_every_configured_model_gets_its_own_rows():
    runs = runs_for({"A": HI, "A__default": LO, "B": OTHER, "B__default": NEAR})
    effects = parameter_effects(runs, 1000.0, {"A": {"x": 1}, "B": {"y": 2}})
    assert {item["model"] for item in effects} == {"A", "B"}
    assert len(effects) == 6


def test_a_model_without_a_baseline_series_has_no_effect_row():
    assert parameter_effects(runs_for({"A": HI, "B": OTHER}), 1000.0, PARAMS) == []


def test_no_parameters_means_no_effects():
    runs = runs_for({"A": HI, "A__default": LO})
    assert parameter_effects(runs, 1000.0, {}) == []
    assert parameter_effects(runs, 1000.0, None) == []


def test_missing_confusion_counts_mean_no_effects():
    runs = runs_for({"A": HI, "A__default": LO})
    for run in runs:
        for item in run:
            del item["tn"]
    assert parameter_effects(runs, 1000.0, PARAMS) == []


def test_baselines_do_not_enter_the_stability_decision():
    runs = runs_for({"A": HI, "A__default": LO, "B": OTHER})
    decision = stability_decision(without_baselines(runs))
    assert {name for item in decision["comparisons"] for name in (item["a"], item["b"])} == {"A", "B"}


def test_baselines_do_not_enter_the_performance_comparisons():
    runs = without_baselines(runs_for({"A": HI, "A__default": LO, "B": OTHER}))
    comparisons = performance_comparisons(runs, 1000.0)
    assert {name for item in comparisons for name in (item["a"], item["b"])} == {"A", "B"}


def test_an_unstable_baseline_is_not_an_instability_finding():
    wild = [0.95, 0.60, 0.97, 0.70, 0.99] * 2
    summary = summarize_seed_runs(runs_for({"A": HI, "A__default": wild, "B": OTHER}))
    assert "A__default" in summary
    assert instability_finding(summary)["unstable"] is False


def test_the_conclusion_sentence_ignores_baselines():
    summary = summarize_seed_runs(runs_for({"A": HI, "A__default": LO, "B": OTHER}))
    assert "A__default" not in str(summary["statistical_conclusion"])


LINE = (
    "model={model} accuracy=0.9 f1=0.8 roc_auc={roc} pr_auc=0.8 "
    "train_seconds=1.0 tn=50 fp=5 fn=5 tp=40"
)
PROFILE = {"dataset": "d", "samples": 500.0, "features": 20.0, "negative_ratio": 0.9, "positive_ratio": 0.1}
SPEC = {"statement": "stmt", "dataset": "customer_churn", "models": ["A", "B"], "params": {}}
CONTROLLED_SPEC = {
    **SPEC,
    "params": {"A": {"n_estimators": 300}},
    "claim": {"kind": "performance", "metric": "roc_auc", "subject": "A", "other": "B"},
}


def controlled_output(a, default, b):
    lines = [LINE.format(model="A", roc=value) for value in a]
    lines += [LINE.format(model="A__default", roc=value) for value in default]
    lines += [LINE.format(model="B", roc=value) for value in b]
    return "\n".join(lines)


def state(spec):
    return {
        "query": "Compare A and B",
        "hypotheses": ["stmt"],
        "experiment_specs": [spec],
        "current_experiment_code": "x = 1",
        "experiment_metrics": {"accuracy": 0.9, "f1": 0.8},
        "dataset_profile": PROFILE,
        "critic_rounds": 0,
    }


@pytest.fixture
def sandbox(monkeypatch):
    class Sandbox:
        output = ""

    box = Sandbox()
    monkeypatch.setattr(nodes, "save_experiment", lambda **kwargs: "memory-id")
    monkeypatch.setattr(nodes, "run_classification", lambda code, schema: box.output)
    monkeypatch.setattr(nodes, "judge_data_leakage", lambda code: (False, ""))
    monkeypatch.setattr(nodes, "log_verified_comparison", lambda *args, **kwargs: "run-id")
    return box


def test_the_verifier_keeps_the_baseline_out_of_the_claim_and_reports_the_effect(sandbox):
    sandbox.output = controlled_output(STEADY, WILD, STEADY)
    result = nodes.verifier_node(state(CONTROLLED_SPEC))
    decision = result["statistical_decision"]
    assert "A__default" in result["statistical_results"]
    assert {name for item in decision["performance"] for name in (item["a"], item["b"])} == {"A", "B"}
    assert {item["model"] for item in decision["parameter_effects"]} == {"A"}
    assert decision["instability"]["unstable"] is False


def test_a_run_without_parameters_has_no_effects(sandbox):
    sandbox.output = "\n".join(
        [LINE.format(model="A", roc=value) for value in STEADY]
        + [LINE.format(model="B", roc=value) for value in WILD]
    )
    result = nodes.verifier_node(state(SPEC))
    assert result["statistical_decision"]["parameter_effects"] == []
