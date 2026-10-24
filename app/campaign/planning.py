import math
import re
from typing import Any, Iterable

from app.campaign.protocol import ESTIMATORS
from app.campaign.runner import DEFAULT_WORKERS, MAX_ATTEMPTS
from app.campaign.spec import MAX_NOTES, validate_campaign
from app.campaign.stats import ALPHA
from app.datasets import BENCHMARK_ROWS, benchmark_keys, core_keys

MAX_PLAN_DATASETS = 10
POOLS = ("benchmark", "core", "all")
SECONDS_BASE = 20
SECONDS_PER_MODEL = 14

_MLP_NOTE = "{name} was represented by scikit-learn's MLPClassifier."
_LINEAR_NOTE = "{name} was represented by scikit-learn's LogisticRegression."
_BOOSTING_NOTE = "{name} was represented by scikit-learn's HistGradientBoostingClassifier."

_EXACT = {re.sub(r"[^a-z0-9]", "", key.lower()): key for key in ESTIMATORS}
_ALIASES: dict[str, tuple[str, str | None]] = {
    "rf": ("RandomForest", None),
    "randomforests": ("RandomForest", None),
    "svc": ("SVM", None),
    "svm": ("SVM", None),
    "supportvectormachine": ("SVM", None),
    "knearestneighbors": ("KNN", None),
    "nearestneighbors": ("KNN", None),
    "naivebayes": ("GaussianNB", None),
    "mlp": ("MLP", None),
    "multilayerperceptron": ("MLP", None),
    "neuralnetwork": ("MLP", _MLP_NOTE),
    "neuralnetworks": ("MLP", _MLP_NOTE),
    "deeplearning": ("MLP", _MLP_NOTE),
    "deepneuralnetwork": ("MLP", _MLP_NOTE),
    "dnn": ("MLP", _MLP_NOTE),
    "resnet": ("MLP", _MLP_NOTE),
    "fttransformer": ("MLP", _MLP_NOTE),
    "transformer": ("MLP", _MLP_NOTE),
    "saint": ("MLP", _MLP_NOTE),
    "logreg": ("LogisticRegression", None),
    "lr": ("LogisticRegression", None),
    "linearmodel": ("LogisticRegression", _LINEAR_NOTE),
    "linearmodels": ("LogisticRegression", _LINEAR_NOTE),
    "gradientboostedtrees": ("HistGradientBoosting", _BOOSTING_NOTE),
    "gradientboosteddecisiontrees": ("HistGradientBoosting", _BOOSTING_NOTE),
    "gbdt": ("HistGradientBoosting", _BOOSTING_NOTE),
    "gbt": ("HistGradientBoosting", _BOOSTING_NOTE),
    "gbm": ("HistGradientBoosting", _BOOSTING_NOTE),
}


class PlanningError(ValueError):
    pass


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def map_models(names: Iterable[str]) -> tuple[list[str], list[str], list[str]]:
    models: list[str] = []
    notes: list[str] = []
    unmapped: list[str] = []
    for name in names:
        key = _key(name)
        if key in _EXACT:
            target, template = _EXACT[key], None
        elif key in _ALIASES:
            target, template = _ALIASES[key]
        else:
            if str(name) not in unmapped:
                unmapped.append(str(name))
            continue
        if target not in models:
            models.append(target)
        if template:
            note = template.format(name=str(name).strip())
            if note not in notes:
                notes.append(note)
    return models, notes, unmapped


def select_datasets(pool: str = "benchmark", count: int | None = None) -> list[str]:
    if pool not in POOLS:
        raise PlanningError(f"unknown dataset pool {pool!r}; choose one of: " + ", ".join(POOLS))
    keys = {"benchmark": benchmark_keys(), "core": core_keys(), "all": benchmark_keys() + core_keys()}[pool]
    if count is None:
        count = min(len(keys), MAX_PLAN_DATASETS)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise PlanningError("the dataset count must be a positive integer")
    if count > MAX_PLAN_DATASETS:
        raise PlanningError(f"a campaign runs at most {MAX_PLAN_DATASETS} datasets")
    if count > len(keys):
        raise PlanningError(f"the {pool} pool has only {len(keys)} datasets")
    return keys[:count]


def minimum_adjusted_p(datasets: int, metrics: int) -> float:
    if datasets < 1 or metrics < 1:
        raise PlanningError("datasets and metrics must both be at least one")
    return min(1.0, metrics * 2.0 / 2.0**datasets)


def power_check(datasets: int, claims: list[dict[str, Any]]) -> None:
    widest = max((len(claim.get("metrics") or [claim.get("metric")]) for claim in claims), default=1)
    best = minimum_adjusted_p(datasets, widest)
    if best >= ALPHA:
        raise PlanningError(
            f"{datasets} datasets cannot reach p < {ALPHA} for a claim on {widest} metric(s): "
            f"even a win on every dataset gives an adjusted p of {best:.4f}; use more datasets or fewer metrics"
        )


def deviation_notes(datasets: list[str], params: dict[str, Any], mapped: list[str]) -> list[str]:
    notes = list(mapped)
    if params:
        notes.append("The listed parameters are single configurations chosen in advance, not the result of a hyperparameter search.")
    else:
        notes.append("No hyperparameter search: every model ran with library default parameters.")
    notes.append("Each dataset was evaluated with 80/20 stratified splits repeated over ten seeds instead of the evaluation protocol of the source.")
    benchmark = set(benchmark_keys())
    if any(key in benchmark for key in datasets):
        notes.append(
            f"Benchmark datasets were reduced to a fixed {BENCHMARK_ROWS}-row balanced sample, and only the numeric-feature "
            "classification datasets of the benchmark available on Hugging Face were used."
        )
    if any(key not in benchmark for key in datasets):
        notes.append(f"Larger core datasets were sampled to at most {BENCHMARK_ROWS} rows with a fixed seed.")
    return notes


def assemble_spec(
    title: str,
    models: list[str],
    claims: list[dict[str, Any]],
    source: dict[str, Any] | None = None,
    pool: str = "benchmark",
    dataset_count: int | None = None,
    mapped_notes: list[str] | None = None,
    params: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    datasets = select_datasets(pool, dataset_count)
    notes = deviation_notes(datasets, params or {}, mapped_notes or [])
    if len(notes) > MAX_NOTES:
        raise PlanningError(f"too many deviation notes ({len(notes)}); at most {MAX_NOTES} fit in a campaign")
    raw = {
        "title": title,
        "models": models,
        "params": params or {},
        "datasets": datasets,
        "claims": claims,
        "source": {**(source or {}), "deviations": notes},
    }
    spec = validate_campaign(raw)
    power_check(len(spec["datasets"]), spec["claims"])
    return spec


def estimate_cost(spec: dict[str, Any], workers: int = DEFAULT_WORKERS, attempts: int = MAX_ATTEMPTS) -> dict[str, int]:
    runs = len(spec["models"]) + len(spec.get("params") or {})
    per_dataset = SECONDS_BASE + SECONDS_PER_MODEL * runs
    datasets = len(spec["datasets"])
    waves = math.ceil(datasets / max(1, workers))
    return {
        "datasets": datasets,
        "model_runs": runs,
        "sandboxes": datasets,
        "max_sandboxes": datasets * attempts,
        "seconds_per_dataset": per_dataset,
        "estimated_seconds": waves * per_dataset,
        "worst_case_seconds": waves * per_dataset * attempts,
    }
