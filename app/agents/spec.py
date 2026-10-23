import ast
import json
import re
from typing import Any

from app.datasets import DATASETS, data_brief, dataset_code_error
from app.variants import baseline_name, configured_models

MODEL_PARAMS: dict[str, tuple[str, ...]] = {
    "LinearSVC": ("C", "class_weight"),
    "SVM": ("C", "kernel", "gamma", "class_weight"),
    "RandomForest": ("n_estimators", "max_depth", "min_samples_leaf", "class_weight"),
    "LogisticRegression": ("C", "max_iter", "class_weight"),
    "DecisionTree": ("max_depth", "min_samples_leaf", "class_weight"),
    "GradientBoosting": ("n_estimators", "learning_rate", "max_depth"),
    "HistGradientBoosting": ("learning_rate", "max_depth", "max_iter"),
    "XGBoost": ("n_estimators", "learning_rate", "max_depth"),
    "LightGBM": ("n_estimators", "learning_rate", "max_depth"),
    "CatBoost": ("iterations", "learning_rate", "depth"),
    "KNN": ("n_neighbors", "weights"),
    "GaussianNB": ("var_smoothing",),
    "MLP": ("alpha", "max_iter"),
    "AdaBoost": ("n_estimators", "learning_rate"),
    "ExtraTrees": ("n_estimators", "max_depth", "min_samples_leaf", "class_weight"),
    "QDA": ("reg_param",),
    "LDA": (),
}


DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "LinearSVC": {"C": 1.0, "class_weight": None},
    "SVM": {"C": 1.0, "kernel": "rbf", "gamma": "scale", "class_weight": None},
    "RandomForest": {"n_estimators": 100, "max_depth": None, "min_samples_leaf": 1, "class_weight": None},
    "LogisticRegression": {"C": 1.0, "max_iter": 100, "class_weight": None},
    "DecisionTree": {"max_depth": None, "min_samples_leaf": 1, "class_weight": None},
    "GradientBoosting": {"n_estimators": 100, "learning_rate": 0.1, "max_depth": 3},
    "HistGradientBoosting": {"learning_rate": 0.1, "max_depth": None, "max_iter": 100},
    "XGBoost": {"n_estimators": 100, "learning_rate": 0.3, "max_depth": 6},
    "LightGBM": {"n_estimators": 100, "learning_rate": 0.1, "max_depth": -1},
    "CatBoost": {"iterations": 1000, "learning_rate": None, "depth": 6},
    "KNN": {"n_neighbors": 5, "weights": "uniform"},
    "GaussianNB": {"var_smoothing": 1e-09},
    "MLP": {"alpha": 0.0001, "max_iter": 200},
    "AdaBoost": {"n_estimators": 50, "learning_rate": 1.0},
    "ExtraTrees": {"n_estimators": 100, "max_depth": None, "min_samples_leaf": 1, "class_weight": None},
    "QDA": {"reg_param": 0.0},
}


def is_default(model: str, name: str, value: Any) -> bool:
    defaults = DEFAULT_PARAMS.get(model, {})
    if name not in defaults:
        return False
    default = defaults[name]
    if default is None or value is None:
        return default is None and value is None
    return default == value


CLAIM_KINDS = ("performance", "stability")
CLAIM_METRICS = ("roc_auc", "pr_auc", "f1")


_COMPARISON_WORDS = re.compile(
    r"\bthan\b|\bversus\b|\bvs\b|\bcompar\w*|\boutperform\w*|\bbetter\b|\bworse\b|\bhigher\b|\blower\b"
    r"|\bimprov\w*|\bincreas\w*|\breduc\w*|\bmore\s+(?:stable|accurate|robust)\b",
    re.IGNORECASE,
)


class SpecError(ValueError):
    pass


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _validate_claim(raw: Any, model_keys: list[str], statement: str) -> dict[str, str] | None:
    if len(model_keys) < 2:
        if _COMPARISON_WORDS.search(statement):
            raise SpecError(
                "the query names one model, so there is nothing to compare it with: "
                "write an absolute statement about its ROC-AUC, PR-AUC or F1 without any comparison word"
            )
        return None
    if not isinstance(raw, dict):
        raise SpecError("claim is missing: a hypothesis must compare two of the models the query named")
    kind = raw.get("kind")
    if kind not in CLAIM_KINDS:
        raise SpecError("claim.kind must be one of " + ", ".join(CLAIM_KINDS))
    metrics = ("roc_auc",) if kind == "stability" else CLAIM_METRICS
    metric = raw.get("metric")
    if metric not in metrics:
        raise SpecError(f"claim.metric must be one of {', '.join(metrics)} for a {kind} claim")
    subject = raw.get("subject")
    other = raw.get("other")
    if subject not in model_keys or other not in model_keys:
        raise SpecError("claim.subject and claim.other must be models the query named")
    if subject == other:
        raise SpecError("claim.subject and claim.other must be two different models")
    squashed = _squash(statement)
    if _squash(subject) not in squashed or _squash(other) not in squashed:
        raise SpecError("the statement must name both models of the claim")
    return {"kind": kind, "metric": metric, "subject": subject, "other": other}


def validate_spec(raw: Any, model_keys: list[str], drop_defaults: bool = False) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SpecError("each hypothesis must be a JSON object")
    statement = raw.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        raise SpecError("statement is missing")
    dataset = raw.get("dataset")
    if dataset not in DATASETS:
        raise SpecError("dataset must be one of " + ", ".join(DATASETS))
    raw_params = raw.get("params") or {}
    if not isinstance(raw_params, dict):
        raise SpecError("params must be a JSON object keyed by model name")
    params: dict[str, dict[str, Any]] = {}
    for model, values in raw_params.items():
        if model not in model_keys:
            raise SpecError(f"params names {model}, which the query did not name")
        if not isinstance(values, dict):
            raise SpecError(f"params for {model} must be a JSON object")
        allowed = MODEL_PARAMS.get(model, ())
        cleaned: dict[str, Any] = {}
        for name, value in values.items():
            if name not in allowed:
                listed = ", ".join(allowed) if allowed else "none"
                raise SpecError(f"{model} does not allow parameter {name}; allowed: {listed}")
            if isinstance(value, bool) or not (value is None or isinstance(value, (int, float, str))):
                raise SpecError(f"{model}.{name} must be a number, a string or null")
            if is_default(model, name, value):
                if drop_defaults:
                    continue
                raise SpecError(
                    f"{model}.{name}={value!r} is already the library default, so it is not a tuning: "
                    "give a value that differs from the default or leave the parameter out"
                )
            cleaned[name] = value
        if cleaned:
            params[model] = cleaned
    return {
        "statement": statement.strip(),
        "models": list(model_keys),
        "claim": _validate_claim(raw.get("claim"), model_keys, statement),
        "dataset": dataset,
        "params": params,
    }


def allowed_params_text(model_keys: list[str]) -> str:
    return "\n".join(
        f"- {key}: "
        + (
            ", ".join(
                f"{name} (default {DEFAULT_PARAMS.get(key, {}).get(name)!r})" if name in DEFAULT_PARAMS.get(key, {}) else name
                for name in MODEL_PARAMS.get(key, ())
            )
            or "no parameters"
        )
        for key in model_keys
    )


def spec_brief(spec: dict[str, Any]) -> str:
    lines = [
        "Experiment specification (follow it exactly):",
        json.dumps(spec, ensure_ascii=False),
        data_brief(str(spec["dataset"])),
    ]
    for model, values in spec.get("params", {}).items():
        pairs = ", ".join(f"{name}={value!r}" for name, value in values.items())
        lines.append(f"Construct {model} with these keyword arguments written literally: {pairs}.")
    controls = configured_models(spec)
    if controls:
        lines.append(
            "Control group: for every model that has parameters add one more models entry named "
            + ", ".join(baseline_name(model) for model in controls)
            + " (the model name followed by __default), built from the same estimator class without any of the listed parameters, "
            "so it runs with the library defaults apart from random_state. It is trained on the same splits and printed like every other entry."
        )
    lines.append(
        "Arguments the specification does not list are yours to choose, such as random_state or max_iter for convergence, "
        "but they must not change a listed value."
    )
    return "\n".join(lines)


def spec_code_error(code: str, spec: dict[str, Any], models: list[dict]) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    names = {call_name(call.func) for call in calls}
    data_error = dataset_code_error(code, str(spec["dataset"]))
    if data_error:
        return data_error
    classes = {str(item["key"]): tuple(item["classes"]) for item in models}
    missing: list[str] = []
    leaked: list[str] = []
    unbuilt: list[str] = []
    entries = _models_entries(tree)
    for model, values in spec.get("params", {}).items():
        entry = entries.get(model)
        scope = list(ast.walk(entry)) if entry is not None else list(ast.walk(tree))
        constructors = [
            node
            for node in scope
            if isinstance(node, ast.Call) and call_name(node.func) in classes.get(model, ())
        ]
        for name, value in values.items():
            if not any(
                keyword.arg == name and _literal(keyword.value) == value
                for call in constructors
                for keyword in call.keywords
            ):
                missing.append(f"{model}.{name}={value!r}")
        control = entries.get(baseline_name(model))
        if control is not None:
            built = False
            for node in ast.walk(control):
                if isinstance(node, ast.Call):
                    built = built or call_name(node.func) in classes.get(model, ())
                    leaked.extend(
                        f"{baseline_name(model)}.{keyword.arg}"
                        for keyword in node.keywords
                        if keyword.arg in values
                    )
            if not built:
                unbuilt.append(baseline_name(model))
    if missing:
        return "The constructors must set these parameters literally: " + ", ".join(missing) + "."
    if unbuilt:
        return "The default entries must construct the same estimator class: " + ", ".join(unbuilt) + "."
    if leaked:
        return "The default entries must not set the listed parameters: " + ", ".join(dict.fromkeys(leaked)) + "."
    return ""


def _models_entries(tree: ast.AST) -> dict[str, ast.expr]:
    found: list[dict[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(target, ast.Name) and target.id == "models" for target in targets):
            continue
        if isinstance(value, ast.Dict):
            found.append(
                {
                    key.value: item
                    for key, item in zip(value.keys, value.values)
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
            )
    return found[0] if len(found) == 1 else {}


def call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _literal(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return object()
