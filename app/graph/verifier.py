import ast

SEED_NAMES = {"random_state", "random_seed", "seed"}
REPLACEMENT_SEED = 9999
ALTERNATE_SEED = 12345
DROP_LIMIT = 0.10


def rewrite_seeds(source: str) -> str:
    tree = ast.parse(source)
    rewriter = _SeedRewriter()
    rewritten = rewriter.visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten)


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
