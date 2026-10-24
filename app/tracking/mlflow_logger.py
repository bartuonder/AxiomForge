import json
import os
import re
import sys
from typing import Any

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow

from app.config import MLFLOW_TRACKING_URI

_NUMBER = r"(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_ACCURACY = re.compile(rf"accuracy\s*[:=]\s*({_NUMBER})", re.IGNORECASE)
_F1 = re.compile(rf"\bf1(?:_score)?\s*[:=]\s*({_NUMBER})", re.IGNORECASE)
_DATASET_LINE = re.compile(
    r"dataset\s*=\s*(?P<dataset>[A-Za-z0-9_]+)\s+"
    r"samples\s*=\s*(?P<samples>\d+)\s+"
    r"features\s*=\s*(?P<features>\d+)\s+"
    rf"negative_ratio\s*=\s*(?P<negative_ratio>{_NUMBER})\s+"
    rf"positive_ratio\s*=\s*(?P<positive_ratio>{_NUMBER})",
    re.IGNORECASE,
)
_MODEL_LINE = re.compile(
    r"model\s*=\s*(?P<model>[A-Za-z0-9_+\-]+)\s+"
    rf"accuracy\s*=\s*(?P<accuracy>{_NUMBER})\s+"
    rf"f1\s*=\s*(?P<f1>{_NUMBER})\s+"
    rf"roc_auc\s*=\s*(?P<roc_auc>{_NUMBER})\s+"
    rf"pr_auc\s*=\s*(?P<pr_auc>{_NUMBER})\s+"
    rf"train_seconds\s*=\s*(?P<train_seconds>{_NUMBER})\s+"
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


def log_verified_comparison(
    rows: list[dict[str, str | float | None]],
    summary: dict[str, dict[str, float] | str],
    decision: dict[str, Any],
    prompt_version: str,
    model: str,
    critic_rounds: int,
    hypothesis: str,
    dataset: dict[str, str | float] | None = None,
    spec: dict[str, Any] | None = None,
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
    models = [name for name, record in summary.items() if isinstance(record, dict)]
    seeds = sorted({int(item["seed"]) for item in rows if item["seed"] is not None})
    with mlflow.start_run() as parent:
        mlflow.log_param("prompt_version", prompt_version)
        mlflow.log_param("model", model)
        mlflow.log_param("status", "Verified")
        mlflow.log_param("critic_rounds", str(critic_rounds))
        mlflow.log_param("compared_models", ",".join(models))
        mlflow.log_param("seeds", ",".join(str(seed) for seed in seeds))
        mlflow.log_param("n_splits", str(decision.get("n_splits", 0)))
        mlflow.log_param("stability_test", str(decision.get("test", "")))
        mlflow.set_tag("hypothesis", hypothesis[:5000])
        mlflow.set_tag("outcome", str(decision.get("outcome", "none")))
        mlflow.set_tag("winner", str(decision.get("winner", "")))
        mlflow.set_tag("hypothesis_verdict", str((decision.get("hypothesis") or {}).get("verdict", "untested")))
        overall = decision.get("overall") or {}
        mlflow.set_tag("overall_best", str(overall.get("model") or "none"))
        for metric, leader in (overall.get("leaders") or {}).items():
            mlflow.set_tag(f"leader_{metric}", str(leader))
        if spec:
            mlflow.log_param("spec_dataset", str(spec.get("dataset", "")))
            mlflow.log_param("spec_params", json.dumps(spec.get("params", {}), ensure_ascii=False)[:500])
        if dataset:
            mlflow.log_param("dataset", str(dataset["dataset"]))
            mlflow.log_metric("samples", float(dataset["samples"]))
            mlflow.log_metric("features", float(dataset["features"]))
            mlflow.log_metric("negative_ratio", float(dataset["negative_ratio"]))
            mlflow.log_metric("positive_ratio", float(dataset["positive_ratio"]))
        for name in models:
            for key, value in summary[name].items():
                mlflow.log_metric(f"{name}/{key}", float(value))
        mlflow.log_metric("min_adjusted_p", float(decision.get("min_adjusted_p", 1.0)))
        instability = decision.get("instability") or {}
        mlflow.log_metric("unstable", 1.0 if instability.get("unstable") else 0.0)
        performance = decision.get("performance") or []
        mlflow.log_metric(
            "significant_performance_differences",
            float(sum(1 for item in performance if item.get("significant"))),
        )
        effects = decision.get("parameter_effects") or []
        mlflow.log_metric(
            "significant_parameter_effects",
            float(sum(1 for item in effects if item.get("significant"))),
        )
        for item in effects:
            prefix = f"effect/{item['model']}/{item['metric']}"
            mlflow.log_metric(f"{prefix}/mean_difference", float(item["mean_difference"]))
            mlflow.log_metric(f"{prefix}/adjusted_p_value", float(item["adjusted_p_value"]))
        conclusion = summary.get("statistical_conclusion")
        if isinstance(conclusion, str) and conclusion:
            mlflow.set_tag("statistical_conclusion", conclusion[:5000])
        for item in rows:
            seed = "unknown" if item["seed"] is None else str(item["seed"])
            with mlflow.start_run(nested=True, run_name=f"{item['model']} seed={seed}"):
                mlflow.log_param("model", str(item["model"]))
                mlflow.log_param("seed", seed)
                mlflow.log_param("split_index", str(item["split_index"]))
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
