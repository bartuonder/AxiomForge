import argparse
import json
from typing import Any

import numpy as np

from app.campaign.hard_benchmark import wilson_interval
from app.campaign.stats import claim_verdict

METRIC_KEYS = ("roc_auc_mean", "pr_auc_mean", "f1_mean")
METRIC_NAMES = ("roc_auc", "pr_auc", "f1")
VERDICTS = ("replicated", "contradicted", "partially_replicated", "inconclusive", "not_testable")
SCENARIOS: list[tuple[str, float, float]] = [
    ("null (no true difference)", 0.0, 0.01),
    ("small true difference (+0.005)", 0.005, 0.01),
    ("moderate true difference (+0.01)", 0.01, 0.01),
    ("large true difference (+0.03)", 0.03, 0.01),
]


def draw_scores(rng: np.random.Generator, datasets: int, noise: float, effect: float, metrics: int, spread: float) -> dict[str, dict[str, dict[str, float]]]:
    scores: dict[str, dict[str, dict[str, float]]] = {}
    for index in range(datasets):
        base = rng.uniform(0.6, 0.95)
        noise_a, noise_b = rng.normal(0, noise), rng.normal(0, noise)
        entry: dict[str, dict[str, float]] = {"A": {}, "B": {}}
        for key in METRIC_KEYS[:metrics]:
            level = base + (rng.normal(0, spread) if spread else 0.0)
            entry["A"][key] = float(np.clip(level + effect + noise_a + rng.normal(0, noise / 3), 0.0, 1.0))
            entry["B"][key] = float(np.clip(level + noise_b + rng.normal(0, noise / 3), 0.0, 1.0))
        scores[f"d{index}"] = entry
    return scores


def simulate(replications: int, datasets: int, noise: float, effect: float, rng: np.random.Generator, metrics: int = 3, spread: float = 0.0) -> dict[str, Any]:
    claim = {"id": "C1", "statement": "A beats B", "metric": "roc_auc", "metrics": list(METRIC_NAMES[:metrics]), "subject": ["A"], "other": ["B"]}
    counts = {verdict: 0 for verdict in VERDICTS}
    for _ in range(replications):
        counts[claim_verdict(draw_scores(rng, datasets, noise, effect, metrics, spread), claim)["verdict"]] += 1
    decisive = counts["replicated"] + counts["contradicted"]
    anything = replications - counts["inconclusive"] - counts["not_testable"]
    return {"replications": replications, "verdicts": counts, "decisive_rate": decisive / replications, "any_claim_rate": anything / replications}


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate the verdict machinery of a campaign on simulated per-dataset scores.")
    parser.add_argument("--replications", type=_positive, default=2000)
    parser.add_argument("--datasets", type=_positive, default=9)
    parser.add_argument("--seed", type=int, default=0)
    arguments = parser.parse_args(argv)
    rng = np.random.default_rng(arguments.seed)
    for name, effect, noise in SCENARIOS:
        result = simulate(arguments.replications, arguments.datasets, noise, effect, rng)
        decisive = result["verdicts"]["replicated"] + result["verdicts"]["contradicted"]
        low, high = wilson_interval(decisive, arguments.replications)
        print(
            json.dumps(
                {"scenario": name, "datasets": arguments.datasets, **result, "wilson95": [round(low, 4), round(high, 4)]},
                ensure_ascii=False,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
