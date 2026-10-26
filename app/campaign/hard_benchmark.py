import math
from typing import Any

from app.campaign.benchmark import CASES, benchmark_claims
from app.campaign.planning import assemble_spec
from app.campaign.spec import validate_campaign

DECISIVE = ("replicated", "contradicted")
NEAR_PAIRS: list[tuple[str, str]] = [
    ("RandomForest", "ExtraTrees"),
    ("HistGradientBoosting", "GradientBoosting"),
    ("LogisticRegression", "LinearSVC"),
]
NEAR_NAMES = {
    "RandomForest": ("random forests", "outperform"),
    "ExtraTrees": ("extremely randomized trees", "outperform"),
    "HistGradientBoosting": ("histogram gradient boosting", "outperforms"),
    "GradientBoosting": ("gradient boosting", "outperforms"),
    "LogisticRegression": ("logistic regression", "outperforms"),
    "LinearSVC": ("a linear support vector machine", "outperforms"),
}
WILSON_Z = 1.96

HARD_PLAN_CASES: list[dict[str, Any]] = [
    {"id": "H1", "query": "Random forests do not outperform a single decision tree on tabular data.", "pair": (["RandomForest"], ["DecisionTree"]), "accept": {"exact", "unsupported"}},
    {"id": "H2", "query": "Which is better for tabular data, random forests or gradient boosting?", "pair": (["RandomForest"], ["GradientBoosting"]), "accept": {"exact", "reversed", "unsupported"}},
    {"id": "H3", "query": "Convolutional networks outperform random forests on image classification.", "pair": None, "accept": {"unsupported"}},
    {"id": "H4", "query": "Transformers outperform support vector machines on tabular classification data.", "pair": (["MLP"], ["SVM"]), "accept": {"exact"}},
    {"id": "H5", "query": "Random forests are at least as good as gradient boosting on tabular classification data.", "pair": (["RandomForest"], ["GradientBoosting"]), "accept": {"exact", "unsupported"}},
    {"id": "H6", "query": "In my experience gradient boosting beats everything else on tabular data.", "pair": None, "accept": {"exact", "other", "unsupported"}},
    {"id": "H7", "query": "The weather will be sunny tomorrow.", "pair": None, "accept": {"unsupported"}},
    {"id": "H8", "query": "Logistic regression outperforms random forests on tabular data with many noisy features.", "pair": (["LogisticRegression"], ["RandomForest"]), "accept": {"exact", "unsupported"}},
]


def near_cases() -> list[dict[str, Any]]:
    cases = []
    for number, (first, second) in enumerate(NEAR_PAIRS):
        for offset, (subject, other) in enumerate(((first, second), (second, first))):
            cases.append(
                {
                    "id": f"N{2 * number + offset + 1}",
                    "pair": number,
                    "subject": [subject],
                    "other": [other],
                    "query": f"{NEAR_NAMES[subject][0].capitalize()} {NEAR_NAMES[subject][1]} {NEAR_NAMES[other][0]} on tabular classification data.",
                }
            )
    return cases


def hard_models() -> list[str]:
    models: list[str] = []
    for case in CASES + near_cases():
        for name in case["subject"] + case["other"]:
            if name not in models:
                models.append(name)
    return models


def hard_claims() -> list[dict[str, Any]]:
    claims = benchmark_claims()
    for case in near_cases():
        claims.append(
            {
                "id": case["id"],
                "statement": case["query"].rstrip("."),
                "metrics": ["roc_auc", "pr_auc", "f1"],
                "subject": list(case["subject"]),
                "other": list(case["other"]),
            }
        )
    return claims


def hard_spec(tuning: dict[str, int] | None = None, pool: str = "benchmark", dataset_count: int | None = None) -> dict[str, Any]:
    spec = assemble_spec("Benchmark of known and near-equal claims", hard_models(), hard_claims(), pool=pool, dataset_count=dataset_count, tuning=tuning)
    return validate_campaign(spec)


def score_near_equal(analysis: dict[str, Any]) -> dict[str, Any]:
    verdicts = {claim["id"]: claim["verdict"] for claim in analysis.get("claims") or []}
    cases = near_cases()
    pairs = []
    for number in range(len(NEAR_PAIRS)):
        forward, backward = [verdicts.get(case["id"], "missing") for case in cases if case["pair"] == number]
        if forward == "replicated" and backward == "replicated":
            state = "contradictory"
        elif forward in DECISIVE or backward in DECISIVE:
            state = "decisive"
        else:
            state = "undecided"
        pairs.append({"pair": list(NEAR_PAIRS[number]), "forward": forward, "backward": backward, "state": state})
    decisive = sum(1 for case in cases if verdicts.get(case["id"]) in DECISIVE)
    return {
        "pairs": pairs,
        "claims": len(cases),
        "decisive_claims": decisive,
        "decisive_rate": decisive / len(cases),
        "contradictory_pairs": sum(1 for pair in pairs if pair["state"] == "contradictory"),
    }


def effect_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    rows = analysis.get("parameter_effects") or []
    return {
        "effects": len(rows),
        "models": len({row["model"] for row in rows}),
        "testable": sum(1 for row in rows if row["adjusted_p_value"] is not None),
        "significant": sum(1 for row in rows if row["significant"]),
        "significant_all": sum(1 for row in rows if row["significant_all"]),
    }


def wilson_interval(successes: int, total: int, z: float = WILSON_Z) -> tuple[float, float]:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("successes must lie between 0 and a positive total")
    share = successes / total
    denominator = 1 + z * z / total
    centre = (share + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def classify_plan(case: dict[str, Any], candidates: list[dict[str, Any]], unsupported: bool = False) -> dict[str, Any]:
    if unsupported or not candidates:
        tag = "unsupported"
    else:
        tags = []
        for candidate in candidates:
            tag = "other"
            for claim in candidate["spec"]["claims"]:
                claimed = (set(claim["subject"]), set(claim["other"]))
                if case["pair"] and claimed == (set(case["pair"][0]), set(case["pair"][1])):
                    tag = "exact"
                    break
                if case["pair"] and claimed == (set(case["pair"][1]), set(case["pair"][0])):
                    tag = "reversed"
            tags.append(tag)
        tag = tags[0]
    return {"id": case["id"], "outcome": tag, "accepted": tag in case["accept"]}
