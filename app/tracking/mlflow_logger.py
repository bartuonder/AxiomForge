import os
import re
import sys

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow

from app.config import MLFLOW_TRACKING_URI

_ACCURACY = re.compile(r"accuracy\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_F1 = re.compile(r"\bf1(?:_score)?\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_MODEL_LINE = re.compile(
    r"model\s*=\s*(?P<model>[A-Za-z0-9_+\-]+)\s+"
    r"accuracy\s*=\s*(?P<accuracy>[0-9]*\.?[0-9]+)\s+"
    r"f1\s*=\s*(?P<f1>[0-9]*\.?[0-9]+)\s+"
    r"train_seconds\s*=\s*(?P<train_seconds>[0-9]*\.?[0-9]+)",
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


def parse_model_results(output: str) -> list[dict[str, str | float]]:
    results: list[dict[str, str | float]] = []
    for match in _MODEL_LINE.finditer(output):
        results.append(
            {
                "model": match.group("model"),
                "accuracy": float(match.group("accuracy")),
                "f1": float(match.group("f1")),
                "train_seconds": float(match.group("train_seconds")),
            }
        )
    if results:
        return results
    metrics = parse_metrics(output)
    return [
        {
            "model": "classifier",
            "accuracy": float(metrics.get("accuracy", 0.0)),
            "f1": float(metrics.get("f1", 0.0)),
            "train_seconds": 0.0,
        }
    ]


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
) -> str:
    _start_experiment()
    with mlflow.start_run() as parent:
        mlflow.log_param("prompt_version", prompt_version)
        mlflow.log_param("algorithm", algorithm)
        mlflow.log_param("model", model)
        mlflow.log_param("attempts", str(attempts))
        mlflow.log_param("status", "Finished")
        mlflow.log_param("compared_models", ",".join(str(item["model"]) for item in results))
        for item in results:
            with mlflow.start_run(nested=True, run_name=str(item["model"])):
                mlflow.log_param("model", str(item["model"]))
                mlflow.log_metric("accuracy", float(item["accuracy"]))
                mlflow.log_metric("f1", float(item["f1"]))
                mlflow.log_metric("train_seconds", float(item["train_seconds"]))
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
