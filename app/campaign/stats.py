from itertools import combinations
from typing import Any

import numpy as np
from scipy import stats

from app.graph.stats import holm_adjust
from app.variants import is_baseline

ALPHA = 0.05
MIN_DATASETS = 6
MIN_FRIEDMAN_DATASETS = 5
METRICS = ("roc_auc", "pr_auc", "f1")


class CampaignStatsError(ValueError):
    pass


def score_matrix(
    per_dataset: dict[str, dict[str, Any]],
    metric: str,
    models: list[str] | None = None,
) -> tuple[list[str], list[str], np.ndarray]:
    datasets = list(per_dataset)
    if not datasets:
        raise CampaignStatsError("no dataset results")
    names = models or [name for name, record in per_dataset[datasets[0]].items() if isinstance(record, dict) and not is_baseline(name)]
    key = f"{metric}_mean"
    rows: list[list[float]] = []
    for dataset in datasets:
        record = per_dataset[dataset]
        try:
            rows.append([float(record[name][key]) for name in names])
        except (KeyError, TypeError) as exc:
            raise CampaignStatsError(f"{dataset} has no {metric} mean for every model") from exc
    return datasets, names, np.asarray(rows, dtype=float)


def family_scores(matrix: np.ndarray, names: list[str], members: list[str]) -> np.ndarray:
    missing = [member for member in members if member not in names]
    if not members or missing:
        raise CampaignStatsError("unknown or empty model group: " + ", ".join(missing or ["(empty)"]))
    columns = [names.index(member) for member in members]
    return matrix[:, columns].max(axis=1)


def compare_scores(first: np.ndarray, second: np.ndarray) -> dict[str, Any]:
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    if first.shape != second.shape or first.ndim != 1:
        raise CampaignStatsError("score vectors must have the same length")
    difference = first - second
    nonzero = difference[difference != 0.0]
    result: dict[str, Any] = {
        "datasets": int(difference.size),
        "wins": int((difference > 0).sum()),
        "losses": int((difference < 0).sum()),
        "ties": int((difference == 0).sum()),
        "mean_difference": float(difference.mean()) if difference.size else 0.0,
        "median_difference": float(np.median(difference)) if difference.size else 0.0,
        "testable": bool(nonzero.size >= MIN_DATASETS),
        "p_value": 1.0,
        "rank_biserial": 0.0,
    }
    if nonzero.size == 0:
        return result
    ranks = stats.rankdata(np.abs(nonzero))
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    result["rank_biserial"] = (positive - negative) / (positive + negative)
    if nonzero.size >= 2:
        result["p_value"] = float(stats.wilcoxon(nonzero, zero_method="wilcox", alternative="two-sided").pvalue)
    return result


def pairwise_comparisons(
    per_dataset: dict[str, dict[str, Any]],
    metric: str,
    models: list[str] | None = None,
) -> list[dict[str, Any]]:
    _, names, matrix = score_matrix(per_dataset, metric, models)
    rows: list[dict[str, Any]] = []
    for first, second in combinations(range(len(names)), 2):
        row = compare_scores(matrix[:, first], matrix[:, second])
        rows.append({"metric": metric, "a": names[first], "b": names[second], **row})
    testable = [index for index, row in enumerate(rows) if row["testable"]]
    adjusted = holm_adjust([rows[index]["p_value"] for index in testable])
    for row in rows:
        row["adjusted_p_value"] = None
        row["significant"] = False
    for index, value in zip(testable, adjusted):
        rows[index]["adjusted_p_value"] = value
        rows[index]["significant"] = value < ALPHA
    return rows


def friedman_test(
    per_dataset: dict[str, dict[str, Any]],
    metric: str,
    models: list[str] | None = None,
) -> dict[str, Any]:
    datasets, names, matrix = score_matrix(per_dataset, metric, models)
    ranks = np.vstack([stats.rankdata(-row) for row in matrix])
    mean_ranks = {name: float(value) for name, value in zip(names, ranks.mean(axis=0))}
    result: dict[str, Any] = {
        "metric": metric,
        "datasets": len(datasets),
        "mean_ranks": mean_ranks,
        "testable": bool(len(names) >= 3 and len(datasets) >= MIN_FRIEDMAN_DATASETS),
        "statistic": None,
        "p_value": None,
        "significant": False,
    }
    if result["testable"]:
        statistic, p_value = stats.friedmanchisquare(*[matrix[:, index] for index in range(len(names))])
        result["statistic"] = float(statistic)
        result["p_value"] = float(p_value)
        result["significant"] = bool(p_value < ALPHA)
    return result


def claim_verdict(
    per_dataset: dict[str, dict[str, Any]],
    claim: dict[str, Any],
) -> dict[str, Any]:
    subject = list(claim["subject"])
    other = list(claim["other"])
    metrics = list(claim.get("metrics") or [claim["metric"]])
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        _, names, matrix = score_matrix(per_dataset, metric)
        rows.append({"metric": metric, **compare_scores(family_scores(matrix, names, subject), family_scores(matrix, names, other))})
    testable = [index for index, row in enumerate(rows) if row["testable"]]
    adjusted = holm_adjust([rows[index]["p_value"] for index in testable])
    for row in rows:
        row["adjusted_p_value"] = None
        row["significant"] = False
    for index, value in zip(testable, adjusted):
        rows[index]["adjusted_p_value"] = value
        rows[index]["significant"] = value < ALPHA
    for row in rows:
        if not row["testable"]:
            row["verdict"] = "not_testable"
        elif not row["significant"]:
            row["verdict"] = "inconclusive"
        else:
            row["verdict"] = "replicated" if row["median_difference"] > 0 else "reversed"
    verdicts = {row["verdict"] for row in rows}
    if verdicts == {"replicated"}:
        overall = "replicated"
    elif "reversed" in verdicts and "replicated" not in verdicts:
        overall = "reversed"
    elif "replicated" in verdicts:
        overall = "partially_replicated"
    elif verdicts == {"not_testable"}:
        overall = "not_testable"
    else:
        overall = "inconclusive"
    return {"claim": claim, "rows": rows, "verdict": overall}
