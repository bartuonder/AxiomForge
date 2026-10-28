import argparse
import json
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Callable

import numpy as np

from app.campaign.hard_benchmark import wilson_interval
from app.campaign.stats import compare_scores, holm_adjust
from app.research import generate, protocol
from app.research.protocol import ExplorationView, Registry

ALPHA = protocol.ALPHA
DATASETS = 16
EXPLORE = 6
PER_STAGE = 8
PROPOSE_EFFECT = 0.0
PROPOSE_CONSISTENCY = 0.5
AGENTS = ("uncorrected_all_pairs", "same_data_holm", "all_pairs_holm", "protocol")
BASE_LEVEL = 0.8
BASE_SPREAD = 0.07


@dataclass(frozen=True)
class World:
    models: list[str]
    abilities: dict[str, float]
    interaction: float
    datasets: int = DATASETS


def draw_scores(rng: np.random.Generator, world: World) -> np.ndarray:
    base = rng.normal(BASE_LEVEL, BASE_SPREAD, world.datasets)
    ability = np.asarray([world.abilities[model] for model in world.models])
    return base[:, None] + ability[None, :] + rng.normal(0.0, world.interaction, (world.datasets, len(world.models)))


def dataset_names(count: int) -> list[str]:
    return [f"d{index:02d}" for index in range(count)]


def as_per_dataset(scores: np.ndarray, models: list[str], datasets: list[str]) -> dict[str, dict[str, Any]]:
    return {
        dataset: {model: {f"{metric}_mean": float(scores[row, column]) for metric in ("roc_auc", "pr_auc", "f1")} for column, model in enumerate(models)}
        for row, dataset in enumerate(datasets)
    }


def is_true(subject: str, other: str, abilities: dict[str, float]) -> bool:
    return abilities[subject] > abilities[other]


def real_pairs(abilities: dict[str, float]) -> int:
    return sum(1 for first, second in combinations(abilities, 2) if abilities[first] != abilities[second])


def tally(reports: list[tuple[str, str]], abilities: dict[str, float]) -> dict[str, int]:
    return {
        "reported": len(reports),
        "false": sum(1 for subject, other in reports if not is_true(subject, other, abilities)),
        "true": len({(subject, other) for subject, other in reports if is_true(subject, other, abilities)}),
    }


def summarize(tallies: list[dict[str, int]], real: int) -> dict[str, Any]:
    total = len(tallies)
    wrong = sum(1 for item in tallies if item["false"] > 0)
    low, high = wilson_interval(wrong, total)
    return {
        "family_wise_error": wrong / total,
        "family_wise_error_interval": [low, high],
        "false_discovery_proportion": sum(item["false"] / max(item["reported"], 1) for item in tallies) / total,
        "power": None if real == 0 else sum(item["true"] / real for item in tallies) / total,
        "mean_reported": sum(item["reported"] for item in tallies) / total,
    }


def _pair_tests(scores: np.ndarray, models: list[str]) -> list[tuple[str, str, float]]:
    tests = []
    for first, second in combinations(range(len(models)), 2):
        result = compare_scores(scores[:, first], scores[:, second])
        winner, loser = (first, second) if result["median_difference"] > 0 else (second, first)
        tests.append((models[winner], models[loser], result["p_value"] if result["testable"] else 1.0))
    return tests


def agent_uncorrected(scores: np.ndarray, models: list[str]) -> list[tuple[str, str]]:
    return [(winner, loser) for winner, loser, p_value in _pair_tests(scores, models) if p_value < ALPHA]


def agent_all_pairs_holm(scores: np.ndarray, models: list[str]) -> list[tuple[str, str]]:
    tests = _pair_tests(scores, models)
    adjusted = holm_adjust([p_value for _, _, p_value in tests])
    return [(winner, loser) for (winner, loser, _), value in zip(tests, adjusted) if value < ALPHA]


def _reported(registry: Registry, results: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    records = {item["id"]: item for item in registry.records}
    return [(records[item["id"]]["subject"][0], records[item["id"]]["other"][0]) for item in protocol.confirm(registry, {"default": results}) if item["status"] == "confirmed"]


def agent_same_data(scores: np.ndarray, models: list[str]) -> list[tuple[str, str]]:
    names = dataset_names(scores.shape[0])
    results = as_per_dataset(scores, models, names)
    registry = Registry(protocol.max_hypotheses(len(names)))
    proposals, _ = generate.propose(ExplorationView(results, names), registry, "default", PER_STAGE, PROPOSE_EFFECT, PROPOSE_CONSISTENCY)
    for item in proposals:
        registry.register(item)
    return _reported(registry, results)


def agent_protocol(scores: np.ndarray, models: list[str]) -> list[tuple[str, str]]:
    names = dataset_names(scores.shape[0])
    results = as_per_dataset(scores, models, names)
    explore, confirm = protocol.split_pool(names, EXPLORE, 0)
    registry = Registry(protocol.max_hypotheses(len(confirm)))
    proposals, _ = generate.propose(ExplorationView(results, explore), registry, "default", PER_STAGE, PROPOSE_EFFECT, PROPOSE_CONSISTENCY)
    for item in proposals:
        registry.register(item)
    return _reported(registry, {name: results[name] for name in confirm})


AGENT_FUNCTIONS: dict[str, Callable[[np.ndarray, list[str]], list[tuple[str, str]]]] = {
    "uncorrected_all_pairs": agent_uncorrected,
    "same_data_holm": agent_same_data,
    "all_pairs_holm": agent_all_pairs_holm,
    "protocol": agent_protocol,
}


def evaluate(reps: int, deltas: list[float], strong: int, sigma: float, models: list[str], seed: int) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for delta in deltas:
        world = World(models=models, abilities={model: (delta if index < strong else 0.0) for index, model in enumerate(models)}, interaction=sigma)
        tallies: dict[str, list[dict[str, int]]] = {agent: [] for agent in AGENTS}
        for _ in range(reps):
            scores = draw_scores(rng, world)
            for agent in AGENTS:
                tallies[agent].append(tally(AGENT_FUNCTIONS[agent](scores, models), world.abilities))
        real = real_pairs(world.abilities)
        for agent in AGENTS:
            rows.append({"delta": delta, "agent": agent, "reps": reps, "strong": strong, "sigma": sigma, "real_pairs": real, **summarize(tallies[agent], real)})
    return rows


def _table(rows: list[dict[str, Any]]) -> str:
    lines = [f"{'delta':>6} {'agent':<24} {'family-wise error':>18} {'false discovery':>16} {'power':>7} {'reported':>9}"]
    for row in rows:
        power = "n/a" if row["power"] is None else f"{row['power']:.3f}"
        low, high = row["family_wise_error_interval"]
        lines.append(f"{row['delta']:>6.3f} {row['agent']:<24} {row['family_wise_error']:>7.3f} [{low:.2f},{high:.2f}] {row['false_discovery_proportion']:>16.3f} {power:>7} {row['mean_reported']:>9.2f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare the research protocol with naive agents on simulated worlds with planted effects.")
    parser.add_argument("--reps", type=int, default=300)
    parser.add_argument("--deltas", default="0,0.01,0.02,0.03")
    parser.add_argument("--strong", type=int, default=3, help="number of models that are really better by delta")
    parser.add_argument("--models", type=int, default=8)
    parser.add_argument("--sigma", type=float, default=0.01, help="spread of the dataset by model interaction")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", help="write the rows as JSON to this path")
    arguments = parser.parse_args(argv)
    if arguments.reps < 1 or arguments.models < 2 or not 0 <= arguments.strong <= arguments.models:
        print("reps must be at least 1, models at least 2 and strong between 0 and models")
        return 2
    rows = evaluate(arguments.reps, [float(item) for item in arguments.deltas.split(",")], arguments.strong, arguments.sigma, [f"M{index}" for index in range(arguments.models)], arguments.seed)
    if arguments.out:
        with open(arguments.out, "w", encoding="utf-8") as stream:
            json.dump(rows, stream, ensure_ascii=False, indent=1)
    print(_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
