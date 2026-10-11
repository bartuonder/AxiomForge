import ast
import json

from openai import OpenAI

from app.config import OPENAI_API_KEY

SEED_NAMES = {"random_state", "random_seed", "seed"}
REPLACEMENT_SEED = 9999
ALTERNATE_SEED = 12345
DROP_LIMIT = 0.10
MAX_CRITIC_ROUNDS = 2
LEAKAGE_PROMPT = (
    "Bu makine öğrenmesi kodunda test setine data leakage (veri sızıntısı) var mı? "
    "(Örn: train ve test ayrılmadan önce imputation veya fit_transform yapılmış mı?) "
    "Analiz et ve varsa sebebini dön. "
    'Return only JSON: {"leakage": true, "reason": "..."}.'
)


def rewrite_seeds(source: str) -> str:
    tree = ast.parse(source)
    rewriter = _SeedRewriter()
    rewritten = rewriter.visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten)


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
        if performance_dropped(
            {"accuracy": float(item["accuracy"]), "f1": float(item["f1"])},
            {"accuracy": float(other["accuracy"]), "f1": float(other["f1"])},
        ):
            return True
    return False


def performance_dropped(original: dict[str, float], renewed: dict[str, float]) -> bool:
    for name in ("accuracy", "f1"):
        if name not in original or name not in renewed:
            continue
        baseline = original[name]
        if baseline <= 0:
            continue
        drop = (baseline - renewed[name]) / baseline
        if drop > DROP_LIMIT:
            return True
    return False


class _SeedRewriter(ast.NodeTransformer):
    def visit_keyword(self, node: ast.keyword) -> ast.keyword:
        self.generic_visit(node)
        if node.arg in SEED_NAMES and _is_int(node.value):
            node.value = ast.Constant(value=_different_seed(node.value.value))
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.Assign:
        self.generic_visit(node)
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in SEED_NAMES
            and _is_int(node.value)
        ):
            node.value = ast.Constant(value=_different_seed(node.value.value))
        return node

    def visit_Call(self, node: ast.Call) -> ast.Call:
        self.generic_visit(node)
        name = _call_name(node.func)
        if name == "seed" and node.args and _is_int(node.args[0]):
            node.args[0] = ast.Constant(value=_different_seed(node.args[0].value))
        return node


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_int(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, int)


def _different_seed(current: int) -> int:
    if current == REPLACEMENT_SEED:
        return ALTERNATE_SEED
    return REPLACEMENT_SEED
