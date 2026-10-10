import os
import re

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow

from app.config import MLFLOW_TRACKING_URI

_ACCURACY = re.compile(r"accuracy\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_F1 = re.compile(r"f1\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def parse_metrics(output: str) -> tuple[float, float]:
    accuracy = _ACCURACY.search(output)
    f1 = _F1.search(output)
    if accuracy is None or f1 is None:
        raise RuntimeError(f"metrics missing from sandbox output: {output}")
    return float(accuracy.group(1)), float(f1.group(1))


def log_classification_metrics(accuracy: float, f1: float) -> str:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("axiomforge")
    with mlflow.start_run() as run:
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1", f1)
        return run.info.run_id
