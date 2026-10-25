import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.campaign.descriptors import dataset_descriptors, parse_descriptors
from app.campaign.protocol import build_script
from app.campaign.provenance import parse_provenance
from app.campaign.tuning import effective_params, parse_tuning
from app.graph.verifier import parameter_effects, performance_comparisons, summarize_seed_runs, without_baselines
from app.sandbox.e2b_runner import SandboxCodeError, run_classification, run_tuned_classification
from app.seeds import SPLIT_SEEDS
from app.tracking.mlflow_logger import parse_dataset_profile, parse_model_results
from app.variants import expected_keys

logger = logging.getLogger("axiomforge")

MAX_ATTEMPTS = 2
DEFAULT_WORKERS = 3
CSV_SCHEMA = "age:float, churn:int"


def _check_rows(rows: list[dict[str, Any]], models: list[str], params: dict[str, Any], seeds: tuple[int, ...]) -> None:
    spec = {"models": models, "params": params}
    expected = expected_keys(models, spec)
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["model"])] = counts.get(str(row["model"]), 0) + 1
    if set(counts) != set(expected) or any(counts[key] != len(seeds) for key in expected):
        raise RuntimeError(f"incomplete output: expected {len(seeds)} rows for each of {', '.join(expected)}, got {counts}")


def run_dataset(
    dataset: str,
    spec: dict[str, Any],
    execute: Callable[[str, str], str] | None = None,
    seeds: tuple[int, ...] = SPLIT_SEEDS,
    attempts: int = MAX_ATTEMPTS,
) -> dict[str, Any]:
    models, params, tuning = spec["models"], effective_params(spec), spec.get("tuning") or {}
    script = build_script(dataset, models, spec.get("params") or {}, seeds, tuning)
    execute = execute or (run_tuned_classification if tuning else run_classification)
    last_error = ""
    for attempt in range(1, attempts + 1):
        started = time.time()
        try:
            output = execute(script, CSV_SCHEMA)
            profile = parse_dataset_profile(output)
            rows = parse_model_results(output)
            _check_rows(rows, models, params, seeds)
        except (SandboxCodeError, RuntimeError) as exc:
            if "E2B_API_KEY is missing" in str(exc):
                raise
            last_error = str(exc)
            logger.error("campaign dataset=%s attempt=%s/%s failed: %s", dataset, attempt, attempts, last_error[:500])
            continue
        samples = float(profile["samples"])
        main_runs = without_baselines([rows])
        return {
            "status": "finished",
            "dataset": dataset,
            "attempts": attempt,
            "seconds": time.time() - started,
            "profile": profile,
            "provenance": parse_provenance(output),
            "tuning": parse_tuning(output) if tuning else {},
            "descriptors": dataset_descriptors(profile, parse_descriptors(output)),
            "summary": summarize_seed_runs([rows]),
            "performance": performance_comparisons(main_runs, samples),
            "parameter_effects": parameter_effects([rows], samples, params),
            "script": script,
        }
    return {"status": "failed", "dataset": dataset, "attempts": attempts, "error": last_error}


def run_campaign(
    spec: dict[str, Any],
    execute: Callable[[str, str], str] | None = None,
    workers: int = DEFAULT_WORKERS,
    on_update: Callable[[str, dict[str, Any]], None] | None = None,
    seeds: tuple[int, ...] = SPLIT_SEEDS,
    attempts: int = MAX_ATTEMPTS,
) -> dict[str, Any]:
    datasets = list(spec["datasets"])

    def work(dataset: str) -> dict[str, Any]:
        if on_update:
            on_update(dataset, {"status": "running"})
        result = run_dataset(dataset, spec, execute, seeds, attempts)
        if on_update:
            on_update(dataset, result)
        return result

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(work, datasets))
    finished = {item["dataset"]: item for item in results if item["status"] == "finished"}
    failed = {item["dataset"]: {"error": item["error"], "attempts": item["attempts"]} for item in results if item["status"] == "failed"}
    return {"order": datasets, "datasets": finished, "failed": failed}
