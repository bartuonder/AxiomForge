import ast
import json

import numpy as np
from openai import OpenAI

from app.config import OPENAI_API_KEY

VERIFICATION_SEEDS = (42, 100, 200, 300, 400)
UNSTABLE_STD = 0.05
VARIANCE_TIE_GAP = 0.005
CONCLUSION_VARIANCE = "roc_auc_variance"
TIE_CONCLUSION = (
    "Modellerin performansı ve varyansı istatistiksel olarak farksızdır (Tie). "
    "Biri diğerine üstünlük kuramamıştır."
)
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
    finished["statistical_conclusion"] = statistical_conclusion(summary)
    return finished


def stability_decision(summary: dict[str, dict[str, float] | str]) -> dict[str, str | float]:
    ranked = [
        (name, float(record[CONCLUSION_VARIANCE]))
        for name, record in summary.items()
        if isinstance(record, dict) and CONCLUSION_VARIANCE in record
    ]
    decision: dict[str, str | float] = {
        "outcome": "none",
        "winner": "",
        "metric": CONCLUSION_VARIANCE,
        "gap": 0.0,
        "tie_gap": VARIANCE_TIE_GAP,
    }
    if len(ranked) < 2:
        return decision
    ranked.sort(key=lambda item: (item[1], item[0]))
    lowest = ranked[0][1]
    decision["gap"] = abs(ranked[-1][1] - lowest)
    winners = [name for name, value in ranked if abs(value - lowest) <= VARIANCE_TIE_GAP]
    if decision["gap"] <= VARIANCE_TIE_GAP or len(winners) != 1:
        decision["outcome"] = "tie"
        return decision
    decision["outcome"] = "winner"
    decision["winner"] = winners[0]
    return decision


def conclusion_sentence(decision: dict[str, str | float]) -> str:
    if decision.get("outcome") == "tie":
        return TIE_CONCLUSION
    if decision.get("outcome") == "winner":
        return f"{decision['winner']} modeli istatistiksel olarak anlamlı bir şekilde daha kararlıdır"
    return ""


def statistical_conclusion(summary: dict[str, dict[str, float]]) -> str:
    return conclusion_sentence(stability_decision(summary))


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

