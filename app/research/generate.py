from typing import Any

import numpy as np

from app.research.protocol import PRIMARY_METRIC, ExplorationView, Hypothesis, Registry
from app.variants import base_model, is_baseline

DEFAULT_EFFECT = 0.01
DEFAULT_CONSISTENCY = 5 / 6
TUNING_TRIGGER = 0.02
ALREADY_REGISTERED = "already registered in this session"
ALREADY_KNOWN = "already confirmed in an earlier session"


def statement(subject: str, other: str, metric: str, stage: str) -> str:
    return f"{subject} scores higher than {other} on {metric} ({stage} stage)"


def model_names(view: ExplorationView) -> list[str]:
    first = view.per_dataset[view.datasets[0]]
    key = f"{PRIMARY_METRIC}_mean"
    return sorted(name for name, record in first.items() if isinstance(record, dict) and key in record)


def pair_allowed(first: str, second: str) -> bool:
    if is_baseline(first) or is_baseline(second):
        return base_model(first) == base_model(second)
    return True


def exploration_evidence(view: ExplorationView, subject: str, other: str) -> dict[str, Any]:
    key = f"{PRIMARY_METRIC}_mean"
    difference = np.asarray([float(view.per_dataset[dataset][subject][key]) - float(view.per_dataset[dataset][other][key]) for dataset in view.datasets])
    return {"median_difference": float(np.median(difference)), "wins": int((difference > 0).sum()), "datasets": len(view.datasets), "scope": "exploration"}


def propose(
    view: ExplorationView,
    registry: Registry,
    stage: str,
    count: int,
    effect: float = DEFAULT_EFFECT,
    consistency: float = DEFAULT_CONSISTENCY,
    known: frozenset[tuple[tuple[str, ...], tuple[str, ...]]] | set[tuple[tuple[str, ...], tuple[str, ...]]] = frozenset(),
) -> tuple[list[Hypothesis], list[dict[str, str]]]:
    names = model_names(view)
    key = f"{PRIMARY_METRIC}_mean"
    scores = {name: np.asarray([float(view.per_dataset[dataset][name][key]) for dataset in view.datasets]) for name in names}
    candidates: list[tuple[float, int, str, str]] = []
    for position, first in enumerate(names):
        for second in names[position + 1 :]:
            if not pair_allowed(first, second):
                continue
            difference = scores[first] - scores[second]
            median = float(np.median(difference))
            if median == 0.0:
                continue
            winner, loser = (first, second) if median > 0 else (second, first)
            wins = int((difference > 0).sum()) if median > 0 else int((difference < 0).sum())
            if abs(median) + 1e-12 < effect or wins / len(difference) + 1e-12 < consistency:
                continue
            candidates.append((abs(median), wins, winner, loser))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    proposals: list[Hypothesis] = []
    skipped: list[dict[str, str]] = []
    capacity = min(count, registry.remaining)
    for size, wins, winner, loser in candidates:
        if len(proposals) >= capacity:
            break
        text = statement(winner, loser, PRIMARY_METRIC, stage)
        item = Hypothesis(
            id=f"H{len(registry.records) + len(proposals) + 1}",
            subject=(winner,),
            other=(loser,),
            stage=stage,
            metric=PRIMARY_METRIC,
            statement=text,
            evidence={"median_difference": size, "wins": wins, "datasets": len(view.datasets), "scope": "exploration"},
        )
        if registry.has(item):
            skipped.append({"statement": text, "reason": ALREADY_REGISTERED})
        elif ((winner,), (loser,)) in known:
            skipped.append({"statement": text, "reason": ALREADY_KNOWN})
        else:
            proposals.append(item)
    return proposals, skipped


def needs_tuning(proposals: list[Hypothesis], threshold: float = TUNING_TRIGGER) -> bool:
    return any(item.evidence["median_difference"] + 1e-12 >= threshold for item in proposals)
