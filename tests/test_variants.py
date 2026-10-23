from app.agents.experiment import _task, models_dict_error, requested_models
from app.agents.spec import spec_brief, spec_code_error, validate_spec
from app.variants import (
    base_model,
    baseline_name,
    configured_models,
    display_name,
    expected_keys,
    is_baseline,
)

KEYS = ["RandomForest", "XGBoost"]
MODELS = requested_models("Compare Random Forest and XGBoost")
CLAIM = {"kind": "performance", "metric": "roc_auc", "subject": "RandomForest", "other": "XGBoost"}
STATEMENT = "RandomForest has a higher ROC-AUC than XGBoost"


def make_spec(params):
    return validate_spec(
        {"statement": STATEMENT, "claim": CLAIM, "dataset": "breast_cancer", "params": params},
        KEYS,
    )


CONTROLLED = """
from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
X, y = load_breast_cancer(return_X_y=True)
models = {
    "RandomForest": RandomForestClassifier(n_estimators=300, random_state=0),
    "RandomForest__default": RandomForestClassifier(random_state=0),
    "XGBoost": XGBClassifier(),
}
"""

UNCONTROLLED = CONTROLLED.replace('    "RandomForest__default": RandomForestClassifier(random_state=0),\n', "")


def test_names_round_trip():
    assert baseline_name("SVM") == "SVM__default"
    assert is_baseline("SVM__default")
    assert not is_baseline("SVM")
    assert base_model("SVM__default") == "SVM"
    assert base_model("SVM") == "SVM"
    assert display_name("SVM__default") == "SVM (default)"
    assert display_name("SVM") == "SVM"


def test_only_models_with_parameters_are_configured():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    assert configured_models(spec) == ["RandomForest"]
    assert configured_models(make_spec({})) == []
    assert configured_models(None) == []


def test_a_baseline_key_follows_each_configured_model():
    spec = make_spec({"XGBoost": {"max_depth": 3}})
    assert expected_keys(KEYS, spec) == ["RandomForest", "XGBoost", "XGBoost__default"]
    assert expected_keys(KEYS, make_spec({})) == KEYS
    assert expected_keys(KEYS, None) == KEYS


def test_the_contract_demands_the_baseline_entry():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    assert models_dict_error(CONTROLLED, MODELS, spec) == ""
    assert "RandomForest__default" in models_dict_error(UNCONTROLLED, MODELS, spec)


def test_the_contract_without_parameters_is_unchanged():
    assert models_dict_error(UNCONTROLLED, MODELS, make_spec({})) == ""
    assert models_dict_error(UNCONTROLLED, MODELS) == ""


def test_a_baseline_entry_must_build_the_same_estimator_class():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    code = CONTROLLED.replace('"RandomForest__default": RandomForestClassifier(random_state=0)', '"RandomForest__default": XGBClassifier()')
    assert "RandomForest__default" in spec_code_error(code, spec, MODELS)


def test_the_task_lists_the_baseline_names():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    task = _task("prompt", "schema", MODELS, spec)
    assert "RandomForest__default" in task


def test_the_brief_describes_the_control_group():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    brief = spec_brief(spec)
    assert "RandomForest__default" in brief
    assert "XGBoost__default" not in brief
    assert "Control group" not in spec_brief(make_spec({}))


def test_the_configured_entry_must_carry_the_parameters():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    assert spec_code_error(CONTROLLED, spec, MODELS) == ""
    swapped = CONTROLLED.replace("n_estimators=300, ", "")
    assert "RandomForest.n_estimators=300" in spec_code_error(swapped, spec, MODELS)


def test_the_parameters_must_not_sit_only_on_the_baseline_entry():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    moved = (
        CONTROLLED.replace("n_estimators=300, ", "")
        .replace('"RandomForest__default": RandomForestClassifier(', '"RandomForest__default": RandomForestClassifier(n_estimators=300, ')
    )
    assert "RandomForest.n_estimators=300" in spec_code_error(moved, spec, MODELS)


def test_the_baseline_entry_must_not_carry_the_listed_parameters():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    leaky = CONTROLLED.replace("RandomForestClassifier(random_state=0)", "RandomForestClassifier(n_estimators=300, random_state=0)")
    assert "RandomForest__default.n_estimators" in spec_code_error(leaky, spec, MODELS)


def test_the_baseline_may_set_unlisted_arguments():
    spec = make_spec({"RandomForest": {"n_estimators": 300}})
    assert spec_code_error(CONTROLLED, spec, MODELS) == ""
