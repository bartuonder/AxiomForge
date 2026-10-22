import pytest

from app.agents.experiment import models_dict_error, requested_models


def keys(query):
    return [item["key"] for item in requested_models(query)]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Compare SVM and Random Forest", ["SVM", "RandomForest"]),
        ("Random Forest versus SVM", ["RandomForest", "SVM"]),
        ("RF vs XGB on churn", ["RandomForest", "XGBoost"]),
        ("lojistik regresyon ve karar ağacı", ["LogisticRegression", "DecisionTree"]),
        ("Compare SVM, svm and Support Vector Machine", ["SVM"]),
        ("a linear svc against knn", ["LinearSVC", "KNN"]),
        ("use RidgeClassifier and SVM", ["RidgeClassifier", "SVM"]),
        ("RandomForestClassifier and XGBClassifier", ["RandomForest", "XGBoost"]),
    ],
)
def test_requested_models(query, expected):
    assert keys(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "",
        "How does churn behave?",
        "perfect performance",
        "svmx and xrf",
    ],
)
def test_queries_without_a_model_name_return_nothing(query):
    assert requested_models(query) == []


def test_linear_svc_does_not_also_count_as_svm():
    assert keys("Compare linear svc and random forest") == ["LinearSVC", "RandomForest"]


GOOD_CODE = """
import subprocess
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
models = {"RandomForest": RandomForestClassifier(), "XGBoost": XGBClassifier()}
"""


def test_a_matching_models_dict_has_no_error():
    allowed = requested_models("Random Forest and XGBoost")
    assert models_dict_error(GOOD_CODE, allowed) == ""


def test_wrong_key_order_is_rejected():
    allowed = requested_models("XGBoost and Random Forest")
    assert "exactly these keys" in models_dict_error(GOOD_CODE, allowed)


def test_missing_key_is_rejected():
    allowed = requested_models("Random Forest, XGBoost and SVM")
    assert "exactly these keys" in models_dict_error(GOOD_CODE, allowed)


def test_two_models_assignments_are_rejected():
    code = GOOD_CODE + '\nmodels = {"RandomForest": RandomForestClassifier(), "XGBoost": XGBClassifier()}\n'
    assert "exactly these keys" in models_dict_error(code, requested_models("Random Forest and XGBoost"))


def test_a_non_literal_models_dict_is_rejected():
    code = "models = dict(RandomForest=1)\n"
    assert "exactly these keys" in models_dict_error(code, requested_models("Random Forest"))


def test_missing_constructor_is_reported():
    code = 'models = {"RandomForest": None}\n'
    error = models_dict_error(code, requested_models("Random Forest"))
    assert "construct its own estimator" in error
    assert "RandomForest" in error


def test_a_foreign_estimator_is_reported():
    code = (
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from sklearn.svm import SVC\n"
        'models = {"RandomForest": RandomForestClassifier()}\n'
        "extra = SVC()\n"
    )
    error = models_dict_error(code, requested_models("Random Forest"))
    assert "did not name" in error
    assert "SVC" in error


def test_an_unknown_classifier_is_reported_as_foreign():
    code = (
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from sklearn.linear_model import RidgeClassifier\n"
        'models = {"RandomForest": RandomForestClassifier()}\n'
        "extra = RidgeClassifier()\n"
    )
    assert "RidgeClassifier" in models_dict_error(code, requested_models("Random Forest"))


def test_a_syntax_error_is_left_to_the_sandbox():
    assert models_dict_error("models = {", requested_models("Random Forest")) == ""
