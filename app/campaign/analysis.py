from typing import Any

from app.campaign.stats import (
    ALPHA,
    METRICS,
    MIN_DATASETS,
    CampaignStatsError,
    claim_verdict,
    compare_scores,
    friedman_test,
    pairwise_comparisons,
    score_matrix,
)
from app.campaign.moderators import moderator_rows
from app.graph.stats import holm_adjust
from app.variants import baseline_name


def _parameter_effects(spec: dict[str, Any], per_dataset: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model, values in (spec.get("params") or {}).items():
        control = baseline_name(model)
        for metric in METRICS:
            _, names, matrix = score_matrix(per_dataset, metric, [model, control])
            rows.append({"model": model, "params": dict(values), "metric": metric, **compare_scores(matrix[:, 0], matrix[:, 1])})
    testable = [index for index, row in enumerate(rows) if row["testable"]]
    adjusted = holm_adjust([rows[index]["p_value"] for index in testable])
    for row in rows:
        row["adjusted_p_value"] = None
        row["significant"] = False
    for index, value in zip(testable, adjusted):
        rows[index]["adjusted_p_value"] = value
        rows[index]["significant"] = value < ALPHA
    return rows


def analyze_campaign(spec: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    finished = [dataset for dataset in outcome["order"] if dataset in outcome["datasets"]]
    coverage = {
        "requested": list(outcome["order"]),
        "finished": finished,
        "failed": dict(outcome.get("failed") or {}),
        "enough_for_tests": len(finished) >= MIN_DATASETS,
        "minimum": MIN_DATASETS,
    }
    if not finished:
        return {"coverage": coverage, "error": "no dataset finished, so nothing can be compared"}
    per_dataset = {dataset: outcome["datasets"][dataset]["summary"] for dataset in finished}
    models = list(spec["models"])
    try:
        return {
            "coverage": coverage,
            "models": models,
            "pairwise": {metric: pairwise_comparisons(per_dataset, metric, models) for metric in METRICS},
            "friedman": {metric: friedman_test(per_dataset, metric, models) for metric in METRICS},
            "claims": [claim_verdict(per_dataset, claim) | {"id": claim["id"], "statement": claim["statement"]} for claim in spec["claims"]],
            "parameter_effects": _parameter_effects(spec, per_dataset),
            "moderators": moderator_rows(
                spec["claims"],
                per_dataset,
                {dataset: outcome["datasets"][dataset].get("descriptors") or {} for dataset in finished},
                finished,
            ),
        }
    except CampaignStatsError as exc:
        return {"coverage": coverage, "error": str(exc)}
