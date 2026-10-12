import os
import re
import sys

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow

from app.config import MLFLOW_TRACKING_URI

_ACCURACY = re.compile(r"accuracy\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_F1 = re.compile(r"\bf1(?:_score)?\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_DATASET_LINE = re.compile(
    r"dataset\s*=\s*(?P<dataset>[A-Za-z0-9_]+)\s+"
    r"samples\s*=\s*(?P<samples>\d+)\s+"
    r"features\s*=\s*(?P<features>\d+)\s+"
    r"negative_ratio\s*=\s*(?P<negative_ratio>[0-9]*\.?[0-9]+)\s+"
    r"positive_ratio\s*=\s*(?P<positive_ratio>[0-9]*\.?[0-9]+)",
    re.IGNORECASE,
)
_MODEL_LINE = re.compile(
    r"model\s*=\s*(?P<model>[A-Za-z0-9_+\-]+)\s+"
    r"accuracy\s*=\s*(?P<accuracy>[0-9]*\.?[0-9]+)\s+"
    r"f1\s*=\s*(?P<f1>[0-9]*\.?[0-9]+)\s+"
    r"roc_auc\s*=\s*(?P<roc_auc>[0-9]*\.?[0-9]+)\s+"
    r"pr_auc\s*=\s*(?P<pr_auc>[0-9]*\.?[0-9]+)\s+"
    r"train_seconds\s*=\s*(?P<train_seconds>[0-9]*\.?[0-9]+)\s+"
    r"tn\s*=\s*(?P<tn>\d+)\s+"
    r"fp\s*=\s*(?P<fp>\d+)\s+"
    r"fn\s*=\s*(?P<fn>\d+)\s+"
    r"tp\s*=\s*(?P<tp>\d+)",
    re.IGNORECASE,
)
_ALGORITHM = re.compile(
    r"\b("
    r"RandomForestClassifier|LogisticRegression|GradientBoostingClassifier|"
    r"SVC|KNeighborsClassifier|DecisionTreeClassifier|AdaBoostClassifier|"
    r"ExtraTreesClassifier|MLPClassifier|GaussianNB|XGBClassifier"
    r")\b"
)


def detect_algorithm(source: str) -> str:
    match = _ALGORITHM.search(source)
    if match is None:
        return "unknown"
    return match.group(1)


def parse_dataset_profile(output: str) -> dict[str, str | float]:
    match = _DATASET_LINE.search(output)
    if match is None:
        raise RuntimeError(f"dataset profile missing from sandbox output: {output}")
    return {
        "dataset": match.group("dataset"),
        "samples": float(match.group("samples")),
        "features": float(match.group("features")),
        "negative_ratio": float(match.group("negative_ratio")),
        "positive_ratio": float(match.group("positive_ratio")),
    }


def parse_model_results(output: str) -> list[dict[str, str | float]]:
    results: list[dict[str, str | float]] = []
    for match in _MODEL_LINE.finditer(output):
        results.append(
            {
                "model": match.group("model"),
                "accuracy": float(match.group("accuracy")),
                "f1": float(match.group("f1")),
                "roc_auc": float(match.group("roc_auc")),
                "pr_auc": float(match.group("pr_auc")),
                "train_seconds": float(match.group("train_seconds")),
                "tn": float(match.group("tn")),
                "fp": float(match.group("fp")),
                "fn": float(match.group("fn")),
                "tp": float(match.group("tp")),
            }
        )
    if not results:
        raise RuntimeError(f"model metrics missing from sandbox output: {output}")
    return results


def parse_metrics(output: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    accuracy = _ACCURACY.search(output)
    f1 = _F1.search(output)
    if accuracy is not None:
        metrics["accuracy"] = float(accuracy.group(1))
    if f1 is not None:
        metrics["f1"] = float(f1.group(1))
    if not metrics:
        raise RuntimeError(f"metrics missing from sandbox output: {output}")
    return metrics


def _allow_unicode_logs() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _start_experiment() -> None:
    _allow_unicode_logs()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("axiomforge")


def log_model_comparison(
    results: list[dict[str, str | float]],
    prompt_version: str,
    algorithm: str,
    model: str,
    attempts: int,
    dataset: dict[str, str | float] | None = None,
) -> str:
    _start_experiment()
    metric_names = (
        "accuracy",
        "f1",
        "roc_auc",
        "pr_auc",
        "train_seconds",
        "tn",
        "fp",
        "fn",
        "tp",
    )
    with mlflow.start_run() as parent:
        mlflow.log_param("prompt_version", prompt_version)
        mlflow.log_param("algorithm", algorithm)
        mlflow.log_param("model", model)
        mlflow.log_param("attempts", str(attempts))
        mlflow.log_param("status", "Finished")
        mlflow.log_param("compared_models", ",".join(str(item["model"]) for item in results))
        if dataset:
            mlflow.log_param("dataset", str(dataset["dataset"]))
            mlflow.log_metric("samples", float(dataset["samples"]))
            mlflow.log_metric("features", float(dataset["features"]))
            mlflow.log_metric("negative_ratio", float(dataset["negative_ratio"]))
            mlflow.log_metric("positive_ratio", float(dataset["positive_ratio"]))
        for item in results:
            with mlflow.start_run(nested=True, run_name=str(item["model"])):
                mlflow.log_param("model", str(item["model"]))
                for name in metric_names:
                    mlflow.log_metric(name, float(item[name]))
        return parent.info.run_id


def log_classification_run(
    metrics: dict[str, float],
    prompt_version: str,
    algorithm: str,
    model: str,
    attempts: int,
) -> str:
    _start_experiment()
    with mlflow.start_run() as run:
        mlflow.log_param("prompt_version", prompt_version)
        mlflow.log_param("algorithm", algorithm)
        mlflow.log_param("model", model)
        mlflow.log_param("attempts", str(attempts))
        mlflow.log_param("status", "Finished")
        for name, value in metrics.items():
            mlflow.log_metric(name, value)
        return run.info.run_id


def log_failed_run(
    prompt_version: str,
    algorithm: str,
    model: str,
    attempts: int,
    error: str,
) -> str:
    _start_experiment()
    run = mlflow.start_run()
    run_id = run.info.run_id
    try:
        mlflow.log_param("prompt_version", prompt_version)
        mlflow.log_param("algorithm", algorithm)
        mlflow.log_param("model", model)
        mlflow.log_param("attempts", str(attempts))
        mlflow.log_param("status", "Failed")
        mlflow.set_tag("error", error[:4000])
    finally:
        mlflow.end_run(status="FAILED")
    return run_id
