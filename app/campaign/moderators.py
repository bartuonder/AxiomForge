from typing import Any

import numpy as np
from scipy import stats

from app.campaign.descriptors import DESCRIPTORS
from app.campaign.stats import ALPHA
from app.graph.stats import holm_adjust

MIN_MODERATOR_DATASETS = 6


def family_score(summary: dict[str, Any], members: list[str], metric: str) -> float:
    return max(float(summary[member][f"{metric}_mean"]) for member in members)


def effects(claim: dict[str, Any], metric: str, summaries: dict[str, dict[str, Any]], datasets: list[str]) -> list[float]:
    return [
        family_score(summaries[dataset], claim["subject"], metric) - family_score(summaries[dataset], claim["other"], metric)
        for dataset in datasets
    ]


def moderator_rows(
    claims: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    descriptors: dict[str, dict[str, float]],
    datasets: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    usable = [dataset for dataset in datasets if dataset in descriptors]
    for claim in claims:
        for metric in claim["metrics"]:
            gaps = np.asarray(effects(claim, metric, summaries, usable), dtype=float) if usable else np.asarray([])
            family: list[dict[str, Any]] = []
            for descriptor in DESCRIPTORS:
                values = np.asarray([descriptors[dataset].get(descriptor, np.nan) for dataset in usable], dtype=float)
                row = {
                    "claim": claim["id"],
                    "metric": metric,
                    "descriptor": descriptor,
                    "datasets": int(values.size),
                    "testable": False,
                    "rho": 0.0,
                    "p_value": 1.0,
                    "adjusted_p_value": None,
                    "significant": False,
                }
                valid = ~np.isnan(values)
                if valid.sum() >= MIN_MODERATOR_DATASETS and np.unique(values[valid]).size > 1 and np.unique(gaps[valid]).size > 1:
                    result = stats.spearmanr(values[valid], gaps[valid])
                    row.update(datasets=int(valid.sum()), testable=True, rho=float(result.statistic), p_value=float(result.pvalue))
                family.append(row)
            testable = [index for index, row in enumerate(family) if row["testable"]]
            adjusted = holm_adjust([family[index]["p_value"] for index in testable])
            for index, value in zip(testable, adjusted):
                family[index]["adjusted_p_value"] = float(value)
                family[index]["significant"] = bool(value < ALPHA)
            rows.extend(family)
    return rows
