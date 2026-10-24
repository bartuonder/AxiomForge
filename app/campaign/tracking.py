import logging
from typing import Any

import mlflow

from app.config import MLFLOW_TRACKING_URI
from app.tracking.mlflow_logger import _allow_unicode_logs

logger = logging.getLogger("axiomforge")

EXPERIMENT = "axiomforge-campaigns"
TEXT_LIMIT = 5000


def metric_leaders(analysis: dict[str, Any]) -> dict[str, str]:
    leaders: dict[str, str] = {}
    for metric, result in (analysis.get("friedman") or {}).items():
        ranks = result.get("mean_ranks") or {}
        if ranks:
            leaders[metric] = min(ranks, key=lambda model: (ranks[model], model))
    return leaders


def overall_leader(analysis: dict[str, Any]) -> str | None:
    tables = [result["mean_ranks"] for result in (analysis.get("friedman") or {}).values() if result.get("mean_ranks")]
    if not tables:
        return None
    models = sorted(tables[0])
    average = {model: sum(table[model] for table in tables) / len(tables) for model in models}
    return min(models, key=lambda model: (average[model], model))


def _log_analysis(analysis: dict[str, Any]) -> None:
    for metric, result in (analysis.get("friedman") or {}).items():
        mlflow.log_metric(f"friedman/{metric}/datasets", float(result["datasets"]))
        mlflow.log_metric(f"friedman/{metric}/testable", 1.0 if result["testable"] else 0.0)
        if result["testable"]:
            mlflow.log_metric(f"friedman/{metric}/statistic", float(result["statistic"]))
            mlflow.log_metric(f"friedman/{metric}/p_value", float(result["p_value"]))
        for model, rank in result["mean_ranks"].items():
            mlflow.log_metric(f"friedman/{metric}/mean_rank/{model}", float(rank))
    for metric, rows in (analysis.get("pairwise") or {}).items():
        for row in rows:
            prefix = f"wilcoxon/{metric}/{row['a']}__vs__{row['b']}"
            mlflow.log_metric(f"{prefix}/wins", float(row["wins"]))
            mlflow.log_metric(f"{prefix}/losses", float(row["losses"]))
            mlflow.log_metric(f"{prefix}/median_difference", float(row["median_difference"]))
            mlflow.log_metric(f"{prefix}/rank_biserial", float(row["rank_biserial"]))
            if row["testable"]:
                mlflow.log_metric(f"{prefix}/p_value", float(row["p_value"]))
            if row["adjusted_p_value"] is not None:
                mlflow.log_metric(f"{prefix}/adjusted_p_value", float(row["adjusted_p_value"]))
    for claim in analysis.get("claims") or []:
        mlflow.set_tag(f"verdict/{claim['id']}", claim["verdict"])
        for row in claim["rows"]:
            prefix = f"claim/{claim['id']}/{row['metric']}"
            mlflow.set_tag(f"{prefix}/verdict", row["verdict"])
            mlflow.log_metric(f"{prefix}/wins", float(row["wins"]))
            mlflow.log_metric(f"{prefix}/losses", float(row["losses"]))
            mlflow.log_metric(f"{prefix}/median_difference", float(row["median_difference"]))
            mlflow.log_metric(f"{prefix}/rank_biserial", float(row["rank_biserial"]))
            if row["testable"]:
                mlflow.log_metric(f"{prefix}/p_value", float(row["p_value"]))
            if row["adjusted_p_value"] is not None:
                mlflow.log_metric(f"{prefix}/adjusted_p_value", float(row["adjusted_p_value"]))
    effects = analysis.get("parameter_effects") or []
    mlflow.log_metric("significant_parameter_effects", float(sum(1 for item in effects if item.get("significant"))))
    for item in effects:
        prefix = f"effect/{item['model']}/{item['metric']}"
        mlflow.log_metric(f"{prefix}/median_difference", float(item["median_difference"]))
        if item.get("adjusted_p_value") is not None:
            mlflow.log_metric(f"{prefix}/adjusted_p_value", float(item["adjusted_p_value"]))


def log_campaign(
    campaign_id: str,
    spec: dict[str, Any],
    outcome: dict[str, Any],
    analysis: dict[str, Any],
    markdown: str,
    ledger: list[dict[str, Any]],
    status: str,
) -> str:
    _allow_unicode_logs()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)
    coverage = analysis["coverage"]
    source = spec.get("source") or {}
    with mlflow.start_run(run_name=f"Campaign Run {campaign_id}") as parent:
        mlflow.set_tag("run_type", "campaign")
        mlflow.set_tag("status", status)
        mlflow.set_tag("title", spec["title"][:TEXT_LIMIT])
        mlflow.log_param("campaign_id", campaign_id)
        mlflow.log_param("models", ",".join(spec["models"]))
        mlflow.log_param("datasets_requested", ",".join(coverage["requested"]))
        mlflow.log_param("datasets_finished", ",".join(coverage["finished"]))
        mlflow.log_param("datasets_failed", ",".join(coverage["failed"]))
        if source.get("citation"):
            mlflow.log_param("source_citation", source["citation"][:500])
        if source.get("url"):
            mlflow.log_param("source_url", source["url"][:500])
        mlflow.log_metric("datasets_finished", float(len(coverage["finished"])))
        mlflow.log_metric("datasets_failed", float(len(coverage["failed"])))
        mlflow.log_metric("enough_for_tests", 1.0 if coverage["enough_for_tests"] else 0.0)
        mlflow.log_metric("ledger_entries", float(len(ledger)))
        if "error" in analysis:
            mlflow.set_tag("analysis_error", analysis["error"][:TEXT_LIMIT])
        else:
            for metric, model in metric_leaders(analysis).items():
                mlflow.set_tag(f"leader_{metric}", model)
            mlflow.set_tag("overall_best", overall_leader(analysis) or "none")
            _log_analysis(analysis)
        try:
            mlflow.log_text(markdown, "report.md")
            mlflow.log_dict(ledger, "ledger.json")
        except Exception:
            logger.exception("campaign %s: artifacts could not be uploaded to MLflow", campaign_id)
        for dataset in coverage["finished"]:
            record = outcome["datasets"][dataset]
            with mlflow.start_run(nested=True, run_name=dataset):
                mlflow.set_tag("run_type", "campaign_dataset")
                mlflow.log_param("dataset", dataset)
                mlflow.log_metric("seconds", float(record["seconds"]))
                mlflow.log_metric("attempts", float(record["attempts"]))
                for model, values in record["summary"].items():
                    if isinstance(values, dict):
                        for key, value in values.items():
                            mlflow.log_metric(f"{model}/{key}", float(value))
        for dataset, failure in coverage["failed"].items():
            with mlflow.start_run(nested=True, run_name=dataset):
                mlflow.set_tag("run_type", "campaign_dataset")
                mlflow.set_tag("failed", "true")
                mlflow.log_param("dataset", dataset)
                mlflow.set_tag("error", str(failure["error"])[:TEXT_LIMIT])
                mlflow.log_metric("attempts", float(failure["attempts"]))
        return parent.info.run_id
