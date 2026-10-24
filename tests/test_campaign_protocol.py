import ast
import contextlib
import io
import sys
import types

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification

from app.agents.experiment import models_dict_error, requested_models, split_contract_error
from app.agents.spec import MODEL_PARAMS, spec_code_error, validate_spec
from app.campaign.protocol import ESTIMATORS, MIN_CAMPAIGN_MODELS, ProtocolError, build_script
from app.datasets import DATASETS, benchmark_keys, dataset_code_error
from app.seeds import SPLIT_SEEDS
from app.tracking.mlflow_logger import parse_dataset_profile, parse_model_results

QUERY = "Compare Random Forest, Logistic Regression and KNN"
MODELS = ["RandomForest", "LogisticRegression", "KNN"]
PARAMS = {"RandomForest": {"n_estimators": 150}, "KNN": {"n_neighbors": 10}}


def test_every_supported_model_has_an_estimator_entry():
    assert set(ESTIMATORS) == set(MODEL_PARAMS)


def test_the_script_is_plain_python_without_comments():
    script = build_script("tb_credit", MODELS, PARAMS)
    ast.parse(script)
    assert "#" not in script


def test_the_script_is_deterministic():
    assert build_script("tb_credit", MODELS, PARAMS) == build_script("tb_credit", MODELS, PARAMS)


def test_the_script_passes_every_existing_code_check():
    script = build_script("tb_credit", MODELS, PARAMS)
    allowed = requested_models(QUERY)
    spec = validate_spec(
        {
            "statement": "RandomForest has a higher ROC-AUC than KNN",
            "claim": {"kind": "performance", "metric": "roc_auc", "subject": "RandomForest", "other": "KNN"},
            "dataset": "tb_credit",
            "params": PARAMS,
        },
        MODELS,
    )
    assert dataset_code_error(script, "tb_credit") == ""
    assert split_contract_error(script) == ""
    assert models_dict_error(script, allowed, spec) == ""
    assert spec_code_error(script, spec, allowed) == ""


@pytest.mark.parametrize("dataset", ["breast_cancer", "adult_income", "tb_pol", "tb_electricity"])
def test_every_dataset_block_is_embedded_unchanged(dataset):
    assert dataset_code_error(build_script(dataset, MODELS, None), dataset) == ""


def test_listed_parameters_are_literal_on_the_configured_entry_and_absent_from_its_control():
    script = build_script("tb_credit", MODELS, PARAMS)
    assert "'RandomForest': " not in script
    assert '"RandomForest": with_preprocessing(RandomForestClassifier(random_state=0, n_estimators=150))' in script
    assert '"RandomForest__default": with_preprocessing(RandomForestClassifier(random_state=0))' in script
    assert '"KNN": with_preprocessing(KNeighborsClassifier(n_neighbors=10))' in script
    assert '"KNN__default": with_preprocessing(KNeighborsClassifier())' in script
    assert "LogisticRegression__default" not in script


def test_a_listed_parameter_overrides_a_fixed_one():
    script = build_script("tb_credit", ["MLP", "KNN"], {"MLP": {"max_iter": 100}})
    assert "MLPClassifier(max_iter=100, random_state=0)" in script
    assert "MLPClassifier(max_iter=500, random_state=0)" in script


def test_only_the_split_seeds_of_the_protocol_are_used():
    script = build_script("tb_credit", MODELS, None)
    assert f"seeds = {list(SPLIT_SEEDS)!r}" in script
    assert "random_state=seed, stratify=y" in script


def test_extra_packages_are_installed_before_they_are_imported():
    script = build_script("tb_credit", ["XGBoost", "LightGBM", "RandomForest"], None)
    assert script.index("pip', 'install', '-q', 'xgboost'") < script.index("from xgboost import")
    assert script.index("pip', 'install', '-q', 'lightgbm'") < script.index("from lightgbm import")
    assert "catboost" not in script
    assert "subprocess" not in build_script("tb_credit", MODELS, None)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"dataset": "nope", "models": MODELS}, "unknown dataset"),
        ({"dataset": "tb_credit", "models": ["RandomForest"]}, "at least two different models"),
        ({"dataset": "tb_credit", "models": ["KNN", "KNN"]}, "at least two different models"),
        ({"dataset": "tb_credit", "models": ["KNN", "Prophet"]}, "unknown models: Prophet"),
        ({"dataset": "tb_credit", "models": MODELS, "params": {"SVM": {"C": 2}}}, "not in the campaign: SVM"),
        ({"dataset": "tb_credit", "models": MODELS, "seeds": ()}, "at least one split seed"),
    ],
)
def test_an_invalid_campaign_is_refused_with_the_reason(kwargs, message):
    with pytest.raises(ProtocolError, match=message):
        build_script(**kwargs)


def test_empty_parameter_objects_create_no_control_group():
    assert "__default" not in build_script("tb_credit", MODELS, {"KNN": {}})


def test_the_minimum_matches_the_two_model_rule():
    assert MIN_CAMPAIGN_MODELS == 2


def fake_hub(monkeypatch, key, rows=7000):
    entry = DATASETS[key]
    features, labels = make_classification(
        n_samples=rows, n_features=10, n_informative=6, class_sep=0.6, random_state=3
    )
    frame = pd.DataFrame(features, columns=[f"f{index}" for index in range(10)])
    positive = entry["positive"]
    negative = "other" if isinstance(positive, str) else (0 if positive != 0 else 1)
    frame[entry["target"]] = np.where(labels == 1, positive, negative)
    for name in entry["drop"]:
        frame[name] = 0
    monkeypatch.setitem(
        sys.modules,
        "datasets",
        types.SimpleNamespace(load_dataset=lambda *args, **kwargs: types.SimpleNamespace(to_pandas=lambda: frame)),
    )


def run_locally(script):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(compile(script, "campaign", "exec"), {})
    return buffer.getvalue()


@pytest.mark.parametrize("dataset", ["tb_credit", "tb_electricity"])
def test_the_script_runs_and_prints_what_the_parsers_expect(monkeypatch, dataset):
    fake_hub(monkeypatch, dataset)
    seeds = (1, 2, 3)
    output = run_locally(build_script(dataset, ["LogisticRegression", "DecisionTree", "GaussianNB"], {"DecisionTree": {"max_depth": 3}}, seeds))
    profile = parse_dataset_profile(output)
    assert profile["dataset"] == dataset
    assert profile["samples"] == 6000.0
    rows = parse_model_results(output)
    assert len(rows) == 3 * 4
    counts = {}
    for row in rows:
        counts[row["model"]] = counts.get(row["model"], 0) + 1
    assert counts == {"LogisticRegression": 3, "DecisionTree": 3, "DecisionTree__default": 3, "GaussianNB": 3}
    for row in rows:
        assert 0.5 <= row["roc_auc"] <= 1.0
        assert row["tn"] + row["fp"] + row["fn"] + row["tp"] == 1200
    assert [row["model"] for row in rows[:4]] == ["LogisticRegression", "DecisionTree", "DecisionTree__default", "GaussianNB"]


def test_the_split_loop_is_ready_for_the_verifier_without_a_rewrite(monkeypatch):
    from app.graph.verifier import has_split_loop

    fake_hub(monkeypatch, "tb_credit")
    output = run_locally(build_script("tb_credit", ["LogisticRegression", "GaussianNB"], None, SPLIT_SEEDS))
    assert has_split_loop(parse_model_results(output))


def test_every_benchmark_dataset_gets_a_valid_script():
    for key in benchmark_keys():
        script = build_script(key, MODELS, None)
        assert dataset_code_error(script, key) == ""
        assert split_contract_error(script) == ""


def test_a_model_without_probabilities_is_scored_with_its_decision_function(monkeypatch):
    fake_hub(monkeypatch, "tb_credit")
    output = run_locally(build_script("tb_credit", ["LinearSVC", "GaussianNB"], None, (1, 2)))
    rows = parse_model_results(output)
    assert {row["model"] for row in rows} == {"LinearSVC", "GaussianNB"}
    assert all(0.5 < row["roc_auc"] <= 1.0 and 0.0 < row["pr_auc"] <= 1.0 for row in rows)
