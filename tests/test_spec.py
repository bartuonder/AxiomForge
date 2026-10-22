import json
from types import SimpleNamespace

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


CLAIM = {"kind": "performance", "metric": "roc_auc", "subject": "RandomForest", "other": "XGBoost"}
STATEMENT = "RandomForest has a higher ROC-AUC than XGBoost"


def raw(**overrides):
    base = {"statement": STATEMENT, "claim": dict(CLAIM), "dataset": "imbalanced", "params": {}}
    base.update(overrides)
    return base


def test_a_valid_spec_is_normalised():
    spec = validate_spec(
        raw(statement="  " + STATEMENT + "  ", params={"RandomForest": {"n_estimators": 300, "class_weight": "balanced"}}),
        KEYS,
    )
    assert spec == {
        "statement": STATEMENT,
        "models": KEYS,
        "claim": CLAIM,
        "dataset": "imbalanced",
        "params": {"RandomForest": {"n_estimators": 300, "class_weight": "balanced"}},
    }


def test_models_always_come_from_the_query_not_the_planner():
    spec = validate_spec(raw(models=["SVM"]), KEYS)
    assert spec["models"] == KEYS


def test_missing_params_become_empty():
    assert validate_spec({"statement": STATEMENT, "claim": CLAIM, "dataset": "breast_cancer"}, KEYS)["params"] == {}


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


def item(statement=STATEMENT, dataset="breast_cancer", params=None):
    return {"statement": statement, "claim": dict(CLAIM), "dataset": dataset, "params": params or {}}


def test_planner_returns_three_validated_specs_and_the_note():
    statements = [STATEMENT + f" ({tag})" for tag in ("a", "b", "c", "extra")]
    specs, note = _plan(plan([item(text) for text in statements], " note "), KEYS)
    assert [spec["statement"] for spec in specs] == statements[:3]
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


def claim_spec(claim, statement=STATEMENT, keys=KEYS):
    return validate_spec(raw(claim=claim, statement=statement), keys)


def test_a_valid_claim_is_kept_as_given():
    assert claim_spec(dict(CLAIM))["claim"] == CLAIM


def test_extra_claim_fields_are_dropped():
    assert claim_spec({**CLAIM, "confidence": "high"})["claim"] == CLAIM


@pytest.mark.parametrize("metric", ["roc_auc", "pr_auc", "f1"])
def test_a_performance_claim_may_use_each_tested_metric(metric):
    assert claim_spec({**CLAIM, "metric": metric})["claim"]["metric"] == metric


def test_a_stability_claim_is_about_roc_auc_only():
    stability = {**CLAIM, "kind": "stability"}
    assert claim_spec(stability)["claim"]["kind"] == "stability"
    with pytest.raises(SpecError, match="claim.metric must be one of roc_auc for a stability claim"):
        claim_spec({**stability, "metric": "f1"})


@pytest.mark.parametrize(
    ("claim", "message"),
    [
        (None, "claim is missing"),
        ("RandomForest is better", "claim is missing"),
        ({**CLAIM, "kind": "improvement"}, "claim.kind"),
        ({**CLAIM, "metric": "accuracy"}, "claim.metric"),
        ({**CLAIM, "subject": "SVM"}, "models the query named"),
        ({**CLAIM, "other": "SVM"}, "models the query named"),
        ({**CLAIM, "other": "RandomForest"}, "two different models"),
    ],
)
def test_an_invalid_claim_is_rejected(claim, message):
    with pytest.raises(SpecError, match=message):
        claim_spec(claim)


def test_a_claim_is_required_for_every_hypothesis_of_a_two_model_query():
    without = raw()
    del without["claim"]
    with pytest.raises(SpecError, match="claim is missing"):
        validate_spec(without, KEYS)


@pytest.mark.parametrize(
    "statement",
    [
        "RandomForest has a higher ROC-AUC",
        "XGBoost has a lower ROC-AUC",
        "Class weights improve the ROC-AUC",
    ],
)
def test_the_statement_must_name_both_models_of_the_claim(statement):
    with pytest.raises(SpecError, match="must name both models"):
        claim_spec(dict(CLAIM), statement=statement)


def test_model_names_in_the_statement_may_use_spaces_and_case():
    spec = claim_spec(
        {**CLAIM, "subject": "RandomForest", "other": "XGBoost"},
        statement="Random forest is more stable than xgboost across splits",
    )
    assert spec["claim"]["subject"] == "RandomForest"


def test_a_single_model_query_has_no_claim():
    spec = validate_spec({"statement": "RandomForest reaches a high F1", "dataset": "breast_cancer"}, ["RandomForest"])
    assert spec["claim"] is None


def test_a_single_model_query_ignores_a_claim_the_planner_added():
    spec = validate_spec(raw(statement="RandomForest reaches a high ROC-AUC"), ["RandomForest"])
    assert spec["claim"] is None


@pytest.mark.parametrize(
    "statement",
    [
        "XGBoost with n_estimators set to 100 has a higher ROC-AUC than XGBoost with n_estimators set to 50",
        "XGBoost with learning_rate 0.1 improves the PR-AUC",
        "XGBoost is more stable in ROC-AUC variance with max_depth 6",
        "XGBoost outperforms its default configuration",
        "XGBoost versus its tuned version on F1",
        "XGBoost reaches a lower F1 on the imbalanced set",
        "XGBoost compared to a baseline",
        "XGBoost gives a better PR-AUC",
    ],
)
def test_a_single_model_statement_may_not_compare_anything(statement):
    with pytest.raises(SpecError, match="nothing to compare it with"):
        validate_spec({"statement": statement, "dataset": "imbalanced"}, ["XGBoost"])


@pytest.mark.parametrize(
    "statement",
    [
        "XGBoost reaches an ROC-AUC above 0.9 on the imbalanced dataset",
        "XGBoost keeps a high F1 on the breast cancer dataset",
        "XGBoost with n_estimators 100 yields a PR-AUC near 0.8",
    ],
)
def test_an_absolute_single_model_statement_is_accepted(statement):
    spec = validate_spec({"statement": statement, "dataset": "imbalanced"}, ["XGBoost"])
    assert spec["claim"] is None
    assert spec["statement"] == statement


def test_a_comparison_word_is_fine_when_two_models_are_compared():
    spec = validate_spec(raw(), KEYS)
    assert "higher" in spec["statement"] and "than" in spec["statement"]
    assert spec["claim"] == CLAIM


def test_three_models_allow_any_pair():
    keys = ["SVM", "KNN", "RandomForest"]
    claim = {"kind": "stability", "metric": "roc_auc", "subject": "KNN", "other": "SVM"}
    spec = validate_spec(raw(claim=claim, statement="KNN is more stable than SVM"), keys)
    assert spec["claim"] == claim


def test_the_planner_prompt_limits_hypotheses_to_model_comparisons():
    from app.agents.planner import SYSTEM_PROMPT

    assert "comparison claim between two of the Allowed models" in SYSTEM_PROMPT
    assert "must never claim that a parameter, a dataset or a method improves" in SYSTEM_PROMPT
    assert "only decide how each model is configured" in SYSTEM_PROMPT
    assert "claim" in SYSTEM_PROMPT


class FakeCompletions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.prompts = []

    def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][-1]["content"])
        content = self.contents.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def planner_client(monkeypatch):
    import app.agents.planner as planner

    holder = SimpleNamespace(completions=None)

    def install(contents):
        holder.completions = FakeCompletions(contents)
        fake = SimpleNamespace(chat=SimpleNamespace(completions=holder.completions))
        monkeypatch.setattr(planner, "OpenAI", lambda api_key: fake)
        monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")
        return holder.completions

    return SimpleNamespace(install=install, run=lambda: planner.run_planner_agent("q", [], [], MODELS))


def three(claim_free=False):
    items = [item(STATEMENT + f" ({tag})") for tag in "abc"]
    if claim_free:
        for entry in items:
            del entry["claim"]
    return plan(items)


def test_the_planner_is_asked_again_once_when_a_claim_is_missing(planner_client):
    completions = planner_client.install([three(claim_free=True), three()])
    specs, _ = planner_client.run()
    assert len(specs) == 3
    assert all(spec["claim"] == CLAIM for spec in specs)
    assert len(completions.prompts) == 2
    assert "Your previous plan was rejected: claim is missing" in completions.prompts[1]
    assert "previous plan was rejected" not in completions.prompts[0]


def test_the_run_stops_when_the_second_plan_is_still_invalid(planner_client):
    completions = planner_client.install([three(claim_free=True), three(claim_free=True)])
    with pytest.raises(RuntimeError, match="invalid experiment spec: claim is missing"):
        planner_client.run()
    assert len(completions.prompts) == 2


def test_a_valid_first_plan_is_used_without_a_second_call(planner_client):
    completions = planner_client.install([three()])
    planner_client.run()
    assert len(completions.prompts) == 1


def test_the_prompt_lists_the_models_the_claim_may_use(planner_client):
    completions = planner_client.install([three()])
    planner_client.run()
    assert "Allowed models: RandomForest, XGBoost" in completions.prompts[0]


def test_the_planner_is_asked_again_when_a_one_model_plan_compares_configurations(monkeypatch):
    import app.agents.planner as planner

    single = requested_models("Evaluate XGBoost on an imbalanced fraud dataset")
    comparing = [
        {"statement": f"XGBoost with depth {n} has a higher ROC-AUC than XGBoost with depth 3", "dataset": "imbalanced", "params": {}}
        for n in (4, 5, 6)
    ]
    absolute = [
        {"statement": f"XGBoost reaches an ROC-AUC above 0.{n} on the imbalanced dataset", "dataset": "imbalanced", "params": {}}
        for n in (7, 8, 9)
    ]
    completions = FakeCompletions([plan(comparing), plan(absolute)])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(planner, "OpenAI", lambda api_key: fake)
    monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")
    specs, _ = planner.run_planner_agent("q", [], [], single)
    assert [spec["claim"] for spec in specs] == [None, None, None]
    assert len(completions.prompts) == 2
    assert "nothing to compare it with" in completions.prompts[1]


def test_the_planner_prompt_forbids_comparison_words_for_a_single_model():
    from app.agents.planner import SYSTEM_PROMPT

    assert "without any comparison word" in SYSTEM_PROMPT
    assert "no second configuration" in SYSTEM_PROMPT
