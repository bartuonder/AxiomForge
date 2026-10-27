import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from app.campaign.analysis import analyze_campaign
from app.campaign.hard_benchmark import wilson_interval
from app.campaign.runner import DEFAULT_WORKERS, run_campaign
from app.campaign.spec import validate_campaign
from app.datasets import benchmark_keys

MODELS = ["RandomForest", "ExtraTrees", "MLP", "DecisionTree", "GradientBoosting", "AdaBoost"]
CONTROL_SEED = 0
ALT_SEED = 1
METRICS = ("roc_auc", "pr_auc", "f1")


def null_spec(models: list[str] | None = None, seed: int = ALT_SEED, datasets: list[str] | None = None) -> dict[str, Any]:
    if seed == CONTROL_SEED:
        raise ValueError(f"the seed must differ from the control seed {CONTROL_SEED}")
    models = list(models or MODELS)
    base = {
        "title": "Null comparison: the same models with another random seed",
        "models": models,
        "params": {},
        "claims": [{"statement": f"{models[0]} beats {models[1]}", "metric": "roc_auc", "subject": [models[0]], "other": [models[1]]}],
        "datasets": list(datasets or benchmark_keys()),
        "source": {},
    }
    spec = validate_campaign(base)
    return {**spec, "params": {model: {"random_state": seed} for model in models}}


def _rate(count: int, total: int) -> tuple[float | None, list[float] | None]:
    if total == 0:
        return None, None
    low, high = wilson_interval(count, total)
    return count / total, [low, high]


def summarize(analysis: dict[str, Any]) -> dict[str, Any]:
    if "error" in analysis:
        raise ValueError(str(analysis["error"]))
    rows = analysis["parameter_effects"]
    by_model: dict[str, dict[str, Any]] = {}
    for model in analysis["models"]:
        own = [row for row in rows if row["model"] == model]
        by_model[model] = {
            "effects": len(own),
            "testable": sum(1 for row in own if row["testable"]),
            "raw_significant": sum(1 for row in own if row["testable"] and row["p_value"] < 0.05),
            "family_significant": sum(1 for row in own if row["significant"]),
            "strict_significant": sum(1 for row in own if row["significant_all"]),
            "median_differences": {row["metric"]: row["median_difference"] for row in own},
        }
    testable = sum(item["testable"] for item in by_model.values())
    raw = sum(item["raw_significant"] for item in by_model.values())
    rate, interval = _rate(raw, testable)
    return {
        "models": list(analysis["models"]),
        "effects": len(rows),
        "testable": testable,
        "raw_significant": raw,
        "family_significant": sum(item["family_significant"] for item in by_model.values()),
        "strict_significant": sum(item["strict_significant"] for item in by_model.values()),
        "raw_rate": rate,
        "raw_rate_interval": interval,
        "by_model": by_model,
    }


def run(
    models: list[str],
    seed: int,
    datasets: list[str],
    execute: Callable[[str, str], str] | None = None,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, Any]:
    spec = null_spec(models, seed, datasets)
    outcome = run_campaign(spec, execute, workers)
    analysis = analyze_campaign(spec, outcome)
    return {
        "seed": seed,
        "finished": len(outcome["datasets"]),
        "failed": outcome["failed"],
        "summary": summarize(analysis),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare each model with a copy of itself that differs only in its random seed, and count the effects the campaign machinery reports.")
    parser.add_argument("--seed", type=int, default=ALT_SEED, help="random seed of the copy; the control uses 0")
    parser.add_argument("--models", help="comma separated model keys; default: " + ", ".join(MODELS))
    parser.add_argument("--datasets", help="comma separated dataset keys; default: the benchmark datasets")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--out", help="write the result as JSON to this path")
    arguments = parser.parse_args(argv)
    models = arguments.models.split(",") if arguments.models else MODELS
    datasets = arguments.datasets.split(",") if arguments.datasets else benchmark_keys()
    try:
        result = run(models, arguments.seed, datasets, workers=arguments.workers)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if arguments.out:
        Path(arguments.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
