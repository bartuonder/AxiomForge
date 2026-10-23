import json
from types import SimpleNamespace

import pytest

import app.agents.planner as planner
from app.agents.experiment import requested_models
from app.agents.spec import (
    DEFAULT_PARAMS,
    MODEL_PARAMS,
    SpecError,
    allowed_params_text,
    is_default,
    validate_spec,
)

KEYS = ["RandomForest", "KNN"]
MODELS = requested_models("Compare Random Forest and KNN")
CLAIM = {"kind": "performance", "metric": "roc_auc", "subject": "RandomForest", "other": "KNN"}
STATEMENT = "RandomForest has a higher ROC-AUC than KNN"


def raw(params):
    return {"statement": STATEMENT, "claim": CLAIM, "dataset": "customer_churn", "params": params}


def test_every_model_has_defaults_for_exactly_its_allowed_parameters():
    assert set(DEFAULT_PARAMS) == set(MODEL_PARAMS) - {"LDA"}
    for model, names in MODEL_PARAMS.items():
        if model in DEFAULT_PARAMS:
            assert set(DEFAULT_PARAMS[model]) == set(names), model


def sklearn_estimators():
    from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis
    from sklearn.ensemble import (
        AdaBoostClassifier,
        ExtraTreesClassifier,
        GradientBoostingClassifier,
        HistGradientBoostingClassifier,
        RandomForestClassifier,
    )
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import GaussianNB
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.svm import SVC, LinearSVC
    from sklearn.tree import DecisionTreeClassifier

    return {
        "LinearSVC": LinearSVC,
        "SVM": SVC,
        "RandomForest": RandomForestClassifier,
        "LogisticRegression": LogisticRegression,
        "DecisionTree": DecisionTreeClassifier,
        "GradientBoosting": GradientBoostingClassifier,
        "HistGradientBoosting": HistGradientBoostingClassifier,
        "KNN": KNeighborsClassifier,
        "GaussianNB": GaussianNB,
        "MLP": MLPClassifier,
        "AdaBoost": AdaBoostClassifier,
        "ExtraTrees": ExtraTreesClassifier,
        "QDA": QuadraticDiscriminantAnalysis,
    }


@pytest.mark.parametrize("model", sorted(sklearn_estimators()))
def test_the_listed_defaults_are_the_installed_sklearn_defaults(model):
    actual = sklearn_estimators()[model]().get_params()
    for name, value in DEFAULT_PARAMS[model].items():
        assert actual[name] == value, f"{model}.{name}"


@pytest.mark.parametrize(
    ("model", "name", "value", "expected"),
    [
        ("KNN", "n_neighbors", 5, True),
        ("KNN", "n_neighbors", 5.0, True),
        ("KNN", "n_neighbors", 7, False),
        ("KNN", "weights", "uniform", True),
        ("KNN", "weights", "distance", False),
        ("RandomForest", "n_estimators", 100, True),
        ("RandomForest", "n_estimators", 200, False),
        ("RandomForest", "max_depth", None, True),
        ("RandomForest", "max_depth", 10, False),
        ("RandomForest", "class_weight", None, True),
        ("RandomForest", "class_weight", "balanced", False),
        ("SVM", "kernel", "rbf", True),
        ("SVM", "kernel", "linear", False),
        ("LogisticRegression", "C", 1.0, True),
        ("LogisticRegression", "C", 1, True),
        ("LogisticRegression", "C", 0.5, False),
        ("GradientBoosting", "max_depth", None, False),
        ("KNN", "n_neighbors", "5", False),
        ("LDA", "solver", "svd", False),
        ("Unknown", "x", 1, False),
        ("KNN", "metric", "euclidean", False),
    ],
)
def test_a_value_counts_as_default_only_when_it_equals_the_library_default(model, name, value, expected):
    assert is_default(model, name, value) is expected


def test_the_validator_rejects_a_default_value_with_a_reason():
    with pytest.raises(SpecError, match="KNN.n_neighbors=5 is already the library default"):
        validate_spec(raw({"KNN": {"n_neighbors": 5}}), KEYS)


def test_the_validator_accepts_a_value_that_differs_from_the_default():
    spec = validate_spec(raw({"KNN": {"n_neighbors": 7}, "RandomForest": {"n_estimators": 300}}), KEYS)
    assert spec["params"] == {"KNN": {"n_neighbors": 7}, "RandomForest": {"n_estimators": 300}}


def test_defaults_are_dropped_on_request_and_the_rest_is_kept():
    spec = validate_spec(
        raw({"KNN": {"n_neighbors": 5, "weights": "distance"}, "RandomForest": {"n_estimators": 100}}),
        KEYS,
        drop_defaults=True,
    )
    assert spec["params"] == {"KNN": {"weights": "distance"}}


def test_a_model_whose_only_parameter_was_a_default_gets_no_control_group():
    from app.variants import configured_models

    spec = validate_spec(raw({"KNN": {"n_neighbors": 5}}), KEYS, drop_defaults=True)
    assert spec["params"] == {}
    assert configured_models(spec) == []


def test_the_planner_sees_every_default_next_to_its_parameter():
    text = allowed_params_text(["RandomForest", "KNN", "LDA"])
    assert "n_estimators (default 100)" in text
    assert "max_depth (default None)" in text
    assert "n_neighbors (default 5)" in text
    assert "weights (default 'uniform')" in text
    assert "LDA: no parameters" in text


def test_the_planner_prompt_explains_why_a_default_is_not_a_tuning():
    assert "listed with its library default" in planner.SYSTEM_PROMPT
    assert "differs from the default" in planner.SYSTEM_PROMPT
    assert "default-parameter control" in planner.SYSTEM_PROMPT


class FakeCompletions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.prompts = []

    def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][1]["content"])
        content = self.contents.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def plan(params):
    items = [
        {"statement": f"{STATEMENT} ({tag})", "claim": CLAIM, "dataset": "customer_churn", "params": params}
        for tag in "abc"
    ]
    return json.dumps({"memory_note": "", "hypotheses": items})


@pytest.fixture
def client(monkeypatch):
    def install(contents):
        completions = FakeCompletions(contents)
        fake = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        monkeypatch.setattr(planner, "OpenAI", lambda api_key: fake)
        monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")
        return completions

    return install


def test_a_plan_with_a_default_is_sent_back_once_with_the_reason(client):
    completions = client([plan({"KNN": {"n_neighbors": 5}}), plan({"KNN": {"n_neighbors": 7}})])
    specs, _ = planner.run_planner_agent("q", [], [], MODELS)
    assert len(completions.prompts) == 2
    assert "is already the library default" in completions.prompts[1]
    assert all(spec["params"] == {"KNN": {"n_neighbors": 7}} for spec in specs)


def test_a_second_plan_that_still_repeats_a_default_is_cleaned_instead_of_failing_the_run(client):
    completions = client([plan({"KNN": {"n_neighbors": 5}}), plan({"KNN": {"n_neighbors": 5}, "RandomForest": {"n_estimators": 200}})])
    specs, _ = planner.run_planner_agent("q", [], [], MODELS)
    assert len(completions.prompts) == 2
    assert all(spec["params"] == {"RandomForest": {"n_estimators": 200}} for spec in specs)


def test_a_plan_without_defaults_needs_one_call(client):
    completions = client([plan({"KNN": {"n_neighbors": 9}})])
    planner.run_planner_agent("q", [], [], MODELS)
    assert len(completions.prompts) == 1


def test_another_invalid_field_still_fails_after_two_attempts(client):
    broken = json.dumps({"memory_note": "", "hypotheses": [{"statement": STATEMENT, "claim": CLAIM, "dataset": "mnist", "params": {}}] * 3})
    client([broken, broken])
    with pytest.raises(RuntimeError, match="invalid experiment spec: dataset must be one of"):
        planner.run_planner_agent("q", [], [], MODELS)
