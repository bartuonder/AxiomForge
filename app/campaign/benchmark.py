from typing import Any

from app.campaign.planning import assemble_spec
from app.campaign.spec import validate_campaign

TRUE = "replicated"
REVERSED = "contradicted"

CASES: list[dict[str, Any]] = [
    {"id": "B1", "subject": ["RandomForest"], "other": ["DecisionTree"], "expected": TRUE, "query": "Random forests outperform a single decision tree on tabular classification data."},
    {"id": "B2", "subject": ["GradientBoosting"], "other": ["DecisionTree"], "expected": TRUE, "query": "Gradient boosting outperforms a single decision tree on tabular classification data."},
    {"id": "B3", "subject": ["HistGradientBoosting"], "other": ["GaussianNB"], "expected": TRUE, "query": "Histogram gradient boosting outperforms Gaussian naive Bayes on tabular classification data."},
    {"id": "B4", "subject": ["RandomForest"], "other": ["KNN"], "expected": TRUE, "query": "Random forests outperform k-nearest neighbours on tabular classification data."},
    {"id": "B5", "subject": ["HistGradientBoosting"], "other": ["MLP"], "expected": TRUE, "query": "Histogram gradient boosting outperforms a multilayer perceptron on tabular classification data."},
    {"id": "B6", "subject": ["DecisionTree"], "other": ["RandomForest"], "expected": REVERSED, "query": "A single decision tree outperforms random forests on tabular classification data."},
    {"id": "B7", "subject": ["DecisionTree"], "other": ["GradientBoosting"], "expected": REVERSED, "query": "A single decision tree outperforms gradient boosting on tabular classification data."},
    {"id": "B8", "subject": ["GaussianNB"], "other": ["HistGradientBoosting"], "expected": REVERSED, "query": "Gaussian naive Bayes outperforms histogram gradient boosting on tabular classification data."},
    {"id": "B9", "subject": ["KNN"], "other": ["RandomForest"], "expected": REVERSED, "query": "k-nearest neighbours outperform random forests on tabular classification data."},
    {"id": "B10", "subject": ["MLP"], "other": ["HistGradientBoosting"], "expected": REVERSED, "query": "A multilayer perceptron outperforms histogram gradient boosting on tabular classification data."},
]


def benchmark_models() -> list[str]:
    models: list[str] = []
    for case in CASES:
        for name in case["subject"] + case["other"]:
            if name not in models:
                models.append(name)
    return models


def benchmark_claims() -> list[dict[str, Any]]:
    return [
        {
            "id": case["id"],
            "statement": case["query"].rstrip("."),
            "metrics": ["roc_auc", "pr_auc", "f1"],
            "subject": list(case["subject"]),
            "other": list(case["other"]),
        }
        for case in CASES
    ]


def benchmark_spec(pool: str = "benchmark", dataset_count: int | None = None) -> dict[str, Any]:
    spec = assemble_spec("Benchmark of ten known claims", benchmark_models(), benchmark_claims(), pool=pool, dataset_count=dataset_count)
    return validate_campaign(spec)


def score_campaign(analysis: dict[str, Any]) -> dict[str, Any]:
    verdicts = {claim["id"]: claim["verdict"] for claim in analysis.get("claims") or []}
    rows = []
    for case in CASES:
        verdict = verdicts.get(case["id"], "missing")
        if verdict == case["expected"]:
            outcome = "correct"
        elif verdict in (TRUE, REVERSED):
            outcome = "wrong"
        else:
            outcome = "undecided"
        rows.append({"id": case["id"], "expected": case["expected"], "verdict": verdict, "outcome": outcome})
    counts = {name: sum(1 for row in rows if row["outcome"] == name) for name in ("correct", "wrong", "undecided")}
    return {"rows": rows, **counts, "total": len(rows), "accuracy": counts["correct"] / len(rows)}


def score_plan(case: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    subject, other = set(case["subject"]), set(case["other"])
    found = []
    for candidate in candidates:
        match = "none"
        for claim in candidate["spec"]["claims"]:
            claimed = (set(claim["subject"]), set(claim["other"]))
            if claimed == (subject, other):
                match = "exact"
                break
            if claimed == (other, subject):
                match = "reversed"
        found.append(match)
    best = "exact" if "exact" in found else "reversed" if "reversed" in found else "none"
    return {"id": case["id"], "candidates": len(candidates), "first": found[0] if found else "none", "best": best, "matches": found}
