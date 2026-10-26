import pytest

from app.tracking.mlflow_logger import (
    detect_algorithm,
    parse_dataset_profile,
    parse_model_results,
)

MODEL_LINE = (
    "model={model} accuracy=0.91 f1=0.8 roc_auc=0.95 pr_auc=0.7 "
    "train_seconds={seconds} tn=50 fp=5 fn=4 tp=41"
)
DATASET_LINE = "dataset=breast_cancer samples=569 features=30 negative_ratio=0.37 positive_ratio=0.63"


def model_output(*pairs):
    return "\n".join(MODEL_LINE.format(model=model, seconds=seconds) for model, seconds in pairs)


def test_model_rows_keep_their_order_and_values():
    rows = parse_model_results(model_output(("RandomForest", "1.25"), ("XGBoost", "0.5")))
    assert [row["model"] for row in rows] == ["RandomForest", "XGBoost"]
    assert rows[0]["roc_auc"] == 0.95
    assert rows[0]["tp"] == 41.0
    assert rows[1]["train_seconds"] == 0.5


@pytest.mark.parametrize(
    ("text", "value"),
    [("4.5e-05", 4.5e-05), ("1E-4", 1e-4), ("2e+1", 20.0), ("3.", 3.0), (".5", 0.5), ("12", 12.0)],
)
def test_train_seconds_accepts_scientific_and_loose_notation(text, value):
    rows = parse_model_results(model_output(("GaussianNB", text)))
    assert rows[0]["train_seconds"] == pytest.approx(value)


def test_a_scientific_line_does_not_drop_the_rows_around_it():
    output = model_output(("A", "1.5"), ("B", "4.5e-05"), ("C", "2.0"))
    assert [row["model"] for row in parse_model_results(output)] == ["A", "B", "C"]


def test_noise_around_model_lines_is_ignored():
    output = "warming up\n" + model_output(("SVM", "0.2")) + "\nfinished"
    assert [row["model"] for row in parse_model_results(output)] == ["SVM"]


def test_missing_model_lines_raise():
    with pytest.raises(RuntimeError, match="model metrics missing"):
        parse_model_results("nothing useful here")


def test_a_line_with_nan_is_not_read():
    output = MODEL_LINE.format(model="SVM", seconds="nan")
    with pytest.raises(RuntimeError):
        parse_model_results(output)


def test_dataset_profile_values():
    profile = parse_dataset_profile(DATASET_LINE)
    assert profile == {
        "dataset": "breast_cancer",
        "samples": 569.0,
        "features": 30.0,
        "negative_ratio": 0.37,
        "positive_ratio": 0.63,
    }


def test_dataset_profile_accepts_scientific_ratios():
    profile = parse_dataset_profile(
        "dataset=d samples=500 features=20 negative_ratio=9e-01 positive_ratio=1.0e-1"
    )
    assert profile["negative_ratio"] == pytest.approx(0.9)
    assert profile["positive_ratio"] == pytest.approx(0.1)


def test_missing_dataset_profile_raises():
    with pytest.raises(RuntimeError, match="dataset profile missing"):
        parse_dataset_profile("model=SVM accuracy=0.9")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("m = RandomForestClassifier()", "RandomForestClassifier"),
        ("m = XGBClassifier()", "XGBClassifier"),
        ("m = Something()", "unknown"),
    ],
)
def test_detect_algorithm(source, expected):
    assert detect_algorithm(source) == expected
