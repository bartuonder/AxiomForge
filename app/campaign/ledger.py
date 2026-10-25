import hashlib
from typing import Any

from app.campaign.stats import METRICS
from app.datasets import DATASETS


def script_digest(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _means(summary: dict[str, Any], models: list[str]) -> dict[str, dict[str, float]]:
    return {
        model: {metric: float(summary[model][f"{metric}_mean"]) for metric in METRICS if f"{metric}_mean" in summary.get(model, {})}
        for model in models
        if isinstance(summary.get(model), dict)
    }


def build_ledger(spec: dict[str, Any], outcome: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def add(kind: str, key: str, **data: Any) -> None:
        entries.append({"id": f"E{len(entries) + 1}", "kind": kind, "key": key, **data})

    models = list(spec["models"])
    for dataset in analysis["coverage"]["finished"]:
        result = outcome["datasets"][dataset]
        registry = DATASETS[dataset]
        profile = result["profile"]
        add(
            "dataset",
            dataset,
            source=registry["hf_id"] + (f" ({registry['config']})" if registry.get("config") else ""),
            samples=float(profile["samples"]),
            features=float(profile["features"]),
            positive_ratio=float(profile["positive_ratio"]),
            seconds=float(result["seconds"]),
            attempts=int(result["attempts"]),
            script_sha256=script_digest(result["script"]),
            provenance=result.get("provenance") or {},
            means=_means(result["summary"], models),
        )
    for dataset, failure in analysis["coverage"]["failed"].items():
        add("failure", dataset, error=str(failure["error"])[:300], attempts=int(failure["attempts"]))
    if "error" in analysis:
        return entries
    for claim in analysis["claims"]:
        for row in claim["rows"]:
            add("claim", f"{claim['id']}:{row['metric']}", claim=claim["id"], **row)
    for metric in METRICS:
        add("friedman", metric, **analysis["friedman"][metric])
    for metric in METRICS:
        for row in analysis["pairwise"][metric]:
            add("pairwise", f"{metric}:{row['a']}:{row['b']}", **row)
    for row in analysis["parameter_effects"]:
        add("effect", f"{row['model']}:{row['metric']}", **row)
    return entries


def find(ledger: list[dict[str, Any]], kind: str, key: str) -> dict[str, Any]:
    for entry in ledger:
        if entry["kind"] == kind and entry["key"] == key:
            return entry
    raise KeyError(f"{kind} {key} is not in the ledger")
