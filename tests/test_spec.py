import json

import pytest

from app.agents.experiment import requested_models
from app.agents.planner import _plan
from app.agents.spec import (
    MODEL_PARAMS,
    SpecError,
    allowed_params_text,
    spec_brief,
    spec_code_error,
    validate_spec,
)

KEYS = ["RandomForest", "XGBoost"]
MODELS = requested_models("Compare Random Forest and XGBoost")


def raw(**overrides):
    base = {"statement": "RandomForest is more stable", "dataset": "imbalanced", "params": {}}
    base.update(overrides)
    return base


def test_a_valid_spec_is_normalised():
    spec = validate_spec(
        raw(statement="  s  ", params={"RandomForest": {"n_estimators": 300, "class_weight": "balanced"}}),
        KEYS,
    )
    assert spec == {
        "statement": "s",
        "models": KEYS,
        "dataset": "imbalanced",
        "params": {"RandomForest": {"n_estimators": 300, "class_weight": "balanced"}},
    }


def test_models_always_come_from_the_query_not_the_planner():
    spec = validate_spec(raw(models=["SVM"]), KEYS)
    assert spec["models"] == KEYS


def test_missing_params_become_empty():
    assert validate_spec({"statement": "s", "dataset": "breast_cancer"}, KEYS)["params"] == {}


def test_empty_parameter_objects_are_dropped():
    assert validate_spec(raw(params={"XGBoost": {}}), KEYS)["params"] == {}


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (["not", "an", "object"], "JSON object"),
        (raw(statement=""), "statement"),
        (raw(statement=3), "statement"),
        (raw(dataset="mnist"), "dataset must be one of"),
        (raw(params=[1]), "params must be"),
        (raw(params={"SVM": {"C": 1}}), "did not name"),
        (raw(params={"XGBoost": [1]}), "must be a JSON object"),
        (raw(params={"XGBoost": {"booster": "gbtree"}}), "does not allow parameter booster"),
        (raw(params={"XGBoost": {"max_depth": True}}), "must be a number"),
        (raw(params={"XGBoost": {"max_depth": [3]}}), "must be a number"),
    ],
)
def test_invalid_specs_are_rejected(bad, message):
    with pytest.raises(SpecError, match=message):
        validate_spec(bad, KEYS)


def test_a_model_without_parameters_allows_none():
    assert MODEL_PARAMS["LDA"] == ()
    with pytest.raises(SpecError, match="allowed: none"):
        validate_spec(raw(params={"LDA": {"shrinkage": 0.1}}), ["LDA"])


def test_allowed_params_text_lists_each_model():
    text = allowed_params_text(["RandomForest", "LDA"])
    assert "RandomForest: n_estimators" in text
    assert "LDA: no parameters" in text


def test_spec_brief_states_dataset_and_literal_parameters():
    spec = validate_spec(raw(params={"RandomForest": {"n_estimators": 300}}), KEYS)
    brief = spec_brief(spec)
    assert "make_classification" in brief
    assert "RandomForest" in brief
    assert "n_estimators=300" in brief


IMBALANCED_CODE = """
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
X, y = make_classification(n_samples=2000, weights=[0.9, 0.1], class_sep=0.5, random_state=1)
models = {"RandomForest": RandomForestClassifier(n_estimators=300, class_weight="balanced"), "XGBoost": XGBClassifier()}
"""

PARAMS = {"RandomForest": {"n_estimators": 300, "class_weight": "balanced"}}


def test_code_that_follows_the_spec_passes():
    spec = validate_spec(raw(params=PARAMS), KEYS)
    assert spec_code_error(IMBALANCED_CODE, spec, MODELS) == ""


def test_a_wrong_parameter_value_is_reported():
    spec = validate_spec(raw(params=PARAMS), KEYS)
    error = spec_code_error(IMBALANCED_CODE.replace("300", "100"), spec, MODELS)
    assert "RandomForest.n_estimators=300" in error


def test_a_missing_parameter_is_reported():
    spec = validate_spec(raw(params={"XGBoost": {"max_depth": 3}}), KEYS)
    assert "XGBoost.max_depth=3" in spec_code_error(IMBALANCED_CODE, spec, MODELS)


def test_negative_literals_are_matched():
    spec = validate_spec(raw(params={"XGBoost": {"max_depth": -1}}), KEYS)
    code = IMBALANCED_CODE.replace("XGBClassifier()", "XGBClassifier(max_depth=-1)")
    assert spec_code_error(code, spec, MODELS) == ""


def test_imbalanced_dataset_needs_weights():
    spec = validate_spec(raw(), KEYS)
    code = IMBALANCED_CODE.replace("weights=[0.9, 0.1], ", "")
    assert "weights" in spec_code_error(code, spec, MODELS)


def test_breast_cancer_spec_rejects_a_generated_dataset():
    spec = validate_spec(raw(dataset="breast_cancer"), KEYS)
    assert "load_breast_cancer" in spec_code_error(IMBALANCED_CODE, spec, MODELS)


def test_breast_cancer_spec_accepts_the_loader():
    spec = validate_spec(raw(dataset="breast_cancer"), KEYS)
    code = "from sklearn.datasets import load_breast_cancer\nX, y = load_breast_cancer(return_X_y=True)\n"
    assert spec_code_error(code, spec, MODELS) == ""


def test_both_loaders_in_one_script_are_rejected():
    spec = validate_spec(raw(dataset="breast_cancer"), KEYS)
    code = (
        "from sklearn.datasets import load_breast_cancer, make_classification\n"
        "a = load_breast_cancer()\nb = make_classification(weights=[0.5, 0.5])\n"
    )
    assert spec_code_error(code, spec, MODELS) != ""


def test_a_syntax_error_is_left_to_the_sandbox():
    spec = validate_spec(raw(), KEYS)
    assert spec_code_error("x = (", spec, MODELS) == ""


def plan(hypotheses, note=""):
    return json.dumps({"memory_note": note, "hypotheses": hypotheses})


def item(statement="s", dataset="breast_cancer", params=None):
    return {"statement": statement, "dataset": dataset, "params": params or {}}


def test_planner_returns_three_validated_specs_and_the_note():
    specs, note = _plan(plan([item("a"), item("b"), item("c"), item("extra")], " note "), KEYS)
    assert [spec["statement"] for spec in specs] == ["a", "b", "c"]
    assert all(spec["models"] == KEYS for spec in specs)
    assert note == "note"


def test_planner_needs_three_hypotheses():
    with pytest.raises(SpecError, match="3 hypotheses"):
        _plan(plan([item(), item()]), KEYS)


def test_planner_rejects_an_invalid_spec_with_the_reason():
    with pytest.raises(SpecError, match="dataset must be one of"):
        _plan(plan([item(), item(dataset="mnist"), item()]), KEYS)


def test_planner_rejects_non_json():
    with pytest.raises(RuntimeError, match="invalid JSON"):
        _plan("not json", KEYS)


def test_planner_rejects_missing_hypotheses_key():
    with pytest.raises(RuntimeError, match="did not return hypotheses"):
        _plan(json.dumps({"memory_note": ""}), KEYS)


def test_planner_ignores_a_non_string_note():
    _, note = _plan(json.dumps({"memory_note": 5, "hypotheses": [item(), item(), item()]}), KEYS)
    assert note == ""
