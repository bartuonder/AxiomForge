import os
import re
import sys

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow

from app.config import MLFLOW_TRACKING_URI

_ACCURACY = re.compile(r"accuracy\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_F1 = re.compile(r"\bf1(?:_score)?\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
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


def log_classification_run(
    metrics: dict[str, float],
    prompt_version: str,
    algorithm: str,
    model: str,
) -> str:
    _allow_unicode_logs()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("axiomforge")
    with mlflow.start_run() as run:
        mlflow.log_param("prompt_version", prompt_version)
        mlflow.log_param("algorithm", algorithm)
        mlflow.log_param("model", model)
        for name, value in metrics.items():
            mlflow.log_metric(name, value)
        return run.info.run_id
