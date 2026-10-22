import ast
import json
from itertools import combinations
from typing import Any

import numpy as np
from openai import OpenAI

from app.config import OPENAI_API_KEY
from app.graph.stats import MIN_SPLITS, corrected_resampled_t, holm_adjust, pitman_morgan_p

VERIFICATION_SEEDS = (42, 100, 200, 300, 400)
UNSTABLE_STD = 0.05
ALPHA = 0.05
CONCLUSION_METRIC = "roc_auc"
PERFORMANCE_METRICS = ("roc_auc", "pr_auc", "f1")
STABILITY_TEST = "Pitman-Morgan variance test on paired splits with Holm adjustment"
DROP_LIMIT = 0.10
MAX_CRITIC_ROUNDS = 2
LEAKAGE_PROMPT = (
    "Bu makine öğrenmesi kodunda test setine data leakage (veri sızıntısı) var mı? "
    "(Örn: train ve test ayrılmadan önce imputation veya fit_transform yapılmış mı?) "
    "Analiz et ve varsa sebebini dön. "
    'Return only JSON: {"leakage": true, "reason": "..."}.'
)


def rewrite_seeds(source: str, seed: int) -> str:
    tree = ast.parse(source)
    rewriter = _SeedRewriter(seed)
    rewritten = rewriter.visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten)


STAT_METRICS = ("accuracy", "f1", "roc_auc", "pr_auc", "train_seconds")


def summarize_seed_runs(
    runs: list[list[dict[str, str | float]]],
) -> dict[str, dict[str, float] | str]:
    names: list[str] = []
    for run in runs:
        for item in run:
            name = str(item["model"])
            if name not in names:
                names.append(name)
    summary: dict[str, dict[str, float]] = {}
    for name in names:
        record: dict[str, float] = {}
        for metric in STAT_METRICS:
            values = [
                float(item[metric])
                for run in runs
                for item in run
                if str(item["model"]) == name and metric in item
            ]
            array = np.asarray(values, dtype=float)
            std = float(np.std(array, ddof=1)) if array.size > 1 else 0.0
            record[f"{metric}_mean"] = float(np.mean(array)) if array.size else 0.0
            record[f"{metric}_std"] = std
            record[f"{metric}_variance"] = std ** 2
        summary[name] = record
    finished: dict[str, dict[str, float] | str] = dict(summary)
    finished["statistical_conclusion"] = conclusion_sentence(stability_decision(runs))
    return finished


def model_series(
    runs: list[list[dict[str, str | float]]],
    metric: str,
) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    for run in runs:
        for item in run:
            if metric in item:
                series.setdefault(str(item["model"]), []).append(float(item[metric]))
    return series


def stability_decision(runs: list[list[dict[str, str | float]]]) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "outcome": "none",
        "winner": "",
        "metric": CONCLUSION_METRIC,
        "test": STABILITY_TEST,
        "alpha": ALPHA,
        "n_splits": 0,
        "min_adjusted_p": 1.0,
        "comparisons": [],
    }
    series = model_series(runs, CONCLUSION_METRIC)
    lengths = {len(values) for values in series.values()}
    if len(series) < 2 or len(lengths) != 1:
        return decision
    splits = lengths.pop()
    decision["n_splits"] = splits
    if splits < MIN_SPLITS:
        return decision
    variances = {name: float(np.var(values, ddof=1)) for name, values in series.items()}
    pairs = list(combinations(series, 2))
    raw = [pitman_morgan_p(series[first], series[second]) for first, second in pairs]
    adjusted = holm_adjust(raw)
    decision["comparisons"] = [
        {
            "a": first,
            "b": second,
            "variance_a": variances[first],
            "variance_b": variances[second],
            "p_value": p_value,
            "adjusted_p_value": adjusted_p,
        }
        for (first, second), p_value, adjusted_p in zip(pairs, raw, adjusted)
    ]
    decision["min_adjusted_p"] = min(adjusted)
    decision["outcome"] = "tie"
    for name in series:
        rivals = [
            (item, item["b"] if item["a"] == name else item["a"])
            for item in decision["comparisons"]
            if name in (item["a"], item["b"])
        ]
        if all(
            item["adjusted_p_value"] < ALPHA and variances[name] < variances[rival]
            for item, rival in rivals
        ):
            decision["outcome"] = "winner"
            decision["winner"] = name
            break
    return decision


def performance_comparisons(
    runs: list[list[dict[str, str | float]]],
    samples: float,
) -> list[dict[str, Any]]:
    rows = [item for run in runs for item in run]
    if not rows or not all(key in rows[0] for key in ("tn", "fp", "fn", "tp")):
        return []
    test_size = float(rows[0]["tn"] + rows[0]["fp"] + rows[0]["fn"] + rows[0]["tp"])
    train_size = float(samples) - test_size
    if test_size <= 0 or train_size <= 0:
        return []
    comparisons: list[dict[str, Any]] = []
    for metric in PERFORMANCE_METRICS:
        series = model_series(runs, metric)
        lengths = {len(values) for values in series.values()}
        if len(series) < 2 or len(lengths) != 1 or lengths.pop() < MIN_SPLITS:
            return []
        for first, second in combinations(series, 2):
            mean_difference, effect_size, p_value = corrected_resampled_t(
                series[first], series[second], train_size, test_size
            )
            comparisons.append(
                {
                    "metric": metric,
                    "a": first,
                    "b": second,
                    "mean_difference": mean_difference,
                    "effect_size_dz": effect_size,
                    "p_value": p_value,
                }
            )
    adjusted = holm_adjust([item["p_value"] for item in comparisons])
    for item, adjusted_p in zip(comparisons, adjusted):
        item["adjusted_p_value"] = adjusted_p
        item["significant"] = adjusted_p < ALPHA
    return comparisons


def conclusion_sentence(decision: dict[str, Any]) -> str:
    outcome = decision.get("outcome")
    if outcome not in {"tie", "winner"}:
        return ""
    method = (
        f"Pitman-Morgan test, alpha = {decision['alpha']:g}, n = {decision['n_splits']} splits"
    )
    if outcome == "tie":
        return (
            "No statistically significant difference in ROC-AUC stability was detected "
            f"(Tie; {method}, smallest Holm-adjusted p = {decision['min_adjusted_p']:.3f}). "
            "This does not establish equivalence."
        )
    return (
        f"{decision['winner']} is statistically significantly more stable: "
        "its ROC-AUC variance is lower than every other model's "
        f"(Holm-adjusted p < {decision['alpha']:g}; {method})."
    )


def is_unstable(summary: dict[str, dict[str, float] | str]) -> bool:
    for record in summary.values():
        if not isinstance(record, dict):
            continue
        for metric in ("roc_auc_std", "f1_std"):
            if float(record.get(metric, 0.0)) > UNSTABLE_STD:
                return True
    return False


def judge_data_leakage(code: str) -> tuple[bool, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": LEAKAGE_PROMPT},
            {"role": "user", "content": code},
        ],
    )
    content = response.choices[0].message.content or ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("leakage judge returned invalid JSON") from exc
    leakage = bool(payload.get("leakage")) if isinstance(payload, dict) else True
    reason = payload.get("reason", "") if isinstance(payload, dict) else ""
    if not isinstance(reason, str):
        reason = ""
    return leakage, reason.strip()


def models_dropped(
    original: list[dict[str, str | float]],
    renewed: list[dict[str, str | float]],
) -> bool:
    found = {str(item["model"]): item for item in renewed}
    if not original:
        return False
    for item in original:
        other = found.get(str(item["model"]))
        if other is None:
            return True
        score_names = ("accuracy", "f1", "roc_auc", "pr_auc")
        if performance_dropped(
            {name: float(item[name]) for name in score_names if name in item},
            {name: float(other[name]) for name in score_names if name in other},
        ):
            return True
    return False


def performance_dropped(original: dict[str, float], renewed: dict[str, float]) -> bool:
    for name in ("accuracy", "f1", "roc_auc", "pr_auc"):
        if name not in original or name not in renewed:
            continue
        baseline = original[name]
        if baseline <= 0:
            continue
        drop = (baseline - renewed[name]) / baseline
        if drop > DROP_LIMIT:
            return True
    return False


def has_split_loop(rows: list[dict[str, str | float]]) -> bool:
    counts: dict[str, int] = {}
    for item in rows:
        name = str(item["model"])
        counts[name] = counts.get(name, 0) + 1
    return bool(counts) and min(counts.values()) >= len(VERIFICATION_SEEDS)


class _SeedRewriter(ast.NodeTransformer):
    def __init__(self, seed: int) -> None:
        self.seed = seed

    def visit_Call(self, node: ast.Call) -> ast.Call:
        self.generic_visit(node)
        if _call_name(node.func) != "train_test_split":
            return node
        for keyword in node.keywords:
            if keyword.arg == "random_state" and _is_int(keyword.value):
                keyword.value = ast.Constant(value=self.seed)
        return node


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_int(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, int)

