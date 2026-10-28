import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.campaign.stats import ALPHA, CampaignStatsError, compare_scores, family_scores, holm_adjust, score_matrix

PRIMARY_METRIC = "roc_auc"
MIN_EXPLORE = 3
MIN_CONFIRM = 6
STATUSES = ("confirmed", "reversed", "not_confirmed", "not_testable")


class ProtocolError(ValueError):
    pass


def split_pool(pool: list[str], explore: int, seed: int) -> tuple[list[str], list[str]]:
    if len(set(pool)) != len(pool):
        raise ProtocolError("the pool has a duplicate dataset")
    if explore < MIN_EXPLORE:
        raise ProtocolError(f"at least {MIN_EXPLORE} datasets are needed to explore")
    if len(pool) - explore < MIN_CONFIRM:
        raise ProtocolError(f"at least {MIN_CONFIRM} datasets are needed to confirm")
    ranked = sorted(pool, key=lambda key: hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest())
    chosen = set(ranked[:explore])
    return [key for key in pool if key in chosen], [key for key in pool if key not in chosen]


def min_p_value(count: int) -> float:
    return 2 / 2**count


def max_hypotheses(count: int, alpha: float = ALPHA) -> int:
    return math.ceil(alpha * 2 ** (count - 1)) - 1


def bh_adjust(p_values: list[float]) -> list[float]:
    count = len(p_values)
    order = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [0.0] * count
    running = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        running = min(running, p_values[index] * count / rank)
        adjusted[index] = running
    return adjusted


def _digest(identifier: str, subject: Any, other: Any, stage: str, metric: str) -> str:
    payload = {"id": identifier, "subject": sorted(subject), "other": sorted(other), "stage": stage, "metric": metric}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Hypothesis:
    id: str
    subject: tuple[str, ...]
    other: tuple[str, ...]
    stage: str
    metric: str
    statement: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, tuple[str, ...], tuple[str, ...], str]:
        return (self.stage, tuple(sorted(self.subject)), tuple(sorted(self.other)), self.metric)

    def digest(self) -> str:
        return _digest(self.id, self.subject, self.other, self.stage, self.metric)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registry:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self._records: list[dict[str, Any]] = []

    @property
    def records(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._records)

    @property
    def remaining(self) -> int:
        return self.budget - len(self._records)

    def has(self, item: Hypothesis) -> bool:
        return any(_key_of(record) == item.key for record in self._records)

    def register(self, item: Hypothesis) -> dict[str, Any]:
        if self.remaining <= 0:
            raise ProtocolError(f"the budget of {self.budget} hypotheses is used up")
        if any(record["id"] == item.id for record in self._records):
            raise ProtocolError(f"the id {item.id} is already used")
        if self.has(item):
            raise ProtocolError(f"{item.statement!r} is already registered")
        record = {
            "id": item.id,
            "subject": list(item.subject),
            "other": list(item.other),
            "stage": item.stage,
            "metric": item.metric,
            "statement": item.statement,
            "evidence": copy.deepcopy(item.evidence),
            "digest": item.digest(),
            "registered_at": _now(),
        }
        self._records.append(record)
        return copy.deepcopy(record)

    @classmethod
    def restore(cls, budget: int, records: list[dict[str, Any]]) -> "Registry":
        registry = cls(budget)
        for record in records:
            if _digest(record["id"], record["subject"], record["other"], record["stage"], record["metric"]) != record["digest"]:
                raise ProtocolError(f"the digest of {record['id']} does not match its content")
            registry._records.append(copy.deepcopy(record))
        return registry


def _key_of(record: dict[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...], str]:
    return (record["stage"], tuple(sorted(record["subject"])), tuple(sorted(record["other"])), record["metric"])


class ExplorationView:
    def __init__(self, per_dataset: dict[str, dict[str, Any]], explore: list[str]) -> None:
        missing = [key for key in explore if key not in per_dataset]
        if missing:
            raise ProtocolError("no result for the exploration datasets: " + ", ".join(missing))
        self.datasets = list(explore)
        self.per_dataset = {key: copy.deepcopy(per_dataset[key]) for key in explore}


def confirm(registry: Registry, results_by_stage: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for record in registry.records:
        stage = record["stage"]
        if stage not in results_by_stage:
            raise ProtocolError(f"no confirmation results for the stage {stage}")
        names = list(dict.fromkeys([*record["subject"], *record["other"]]))
        try:
            _, ordered, matrix = score_matrix(results_by_stage[stage], record["metric"], names)
            comparison = compare_scores(family_scores(matrix, ordered, record["subject"]), family_scores(matrix, ordered, record["other"]))
        except CampaignStatsError as exc:
            raise ProtocolError(str(exc)) from exc
        outcomes.append({"id": record["id"], "stage": stage, "testable": comparison["testable"], "comparison": comparison})
    p_values = [item["comparison"]["p_value"] if item["testable"] else 1.0 for item in outcomes]
    holm = holm_adjust(p_values)
    benjamini = bh_adjust(p_values)
    results: list[dict[str, Any]] = []
    for item, adjusted, q_value in zip(outcomes, holm, benjamini):
        comparison = item["comparison"]
        if not item["testable"]:
            status = "not_testable"
        elif adjusted < ALPHA:
            status = "confirmed" if comparison["median_difference"] > 0 else "reversed"
        else:
            status = "not_confirmed"
        results.append(
            {
                "id": item["id"],
                "stage": item["stage"],
                "status": status,
                "p_value": comparison["p_value"] if item["testable"] else None,
                "adjusted_p_value": adjusted if item["testable"] else None,
                "q_value": q_value if item["testable"] else None,
                "median_difference": comparison["median_difference"],
                "wins": comparison["wins"],
                "losses": comparison["losses"],
                "ties": comparison["ties"],
                "datasets": comparison["datasets"],
            }
        )
    return results
