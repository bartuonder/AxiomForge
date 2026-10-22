import ast
import json
from typing import Any

DATASETS = {
    "breast_cancer": "sklearn.datasets.load_breast_cancer",
    "imbalanced": "sklearn.datasets.make_classification with class_sep of at most 0.5 and a weights list",
}

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


class SpecError(ValueError):
    pass


def validate_spec(raw: Any, model_keys: list[str]) -> dict[str, Any]:
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
            cleaned[name] = value
        if cleaned:
            params[model] = cleaned
    return {
        "statement": statement.strip(),
        "models": list(model_keys),
        "dataset": dataset,
        "params": params,
    }


def allowed_params_text(model_keys: list[str]) -> str:
    return "\n".join(
        f"- {key}: " + (", ".join(MODEL_PARAMS.get(key, ())) or "no parameters")
        for key in model_keys
    )


def spec_brief(spec: dict[str, Any]) -> str:
    dataset = DATASETS[str(spec["dataset"])]
    lines = [
        "Experiment specification (follow it exactly):",
        json.dumps(spec, ensure_ascii=False),
        f"Use this dataset and no other: {dataset}.",
    ]
    for model, values in spec.get("params", {}).items():
        pairs = ", ".join(f"{name}={value!r}" for name, value in values.items())
        lines.append(f"Construct {model} with these keyword arguments written literally: {pairs}.")
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
    if spec["dataset"] == "breast_cancer":
        if "load_breast_cancer" not in names or "make_classification" in names:
            return "The dataset must be load_breast_cancer and make_classification must not appear."
    else:
        generators = [call for call in calls if call_name(call.func) == "make_classification"]
        weighted = any(keyword.arg == "weights" for call in generators for keyword in call.keywords)
        if not weighted or "load_breast_cancer" in names:
            return (
                "The dataset must be make_classification with a weights argument "
                "and load_breast_cancer must not appear."
            )
    classes = {str(item["key"]): tuple(item["classes"]) for item in models}
    missing: list[str] = []
    for model, values in spec.get("params", {}).items():
        constructors = [call for call in calls if call_name(call.func) in classes.get(model, ())]
        for name, value in values.items():
            if not any(
                keyword.arg == name and _literal(keyword.value) == value
                for call in constructors
                for keyword in call.keywords
            ):
                missing.append(f"{model}.{name}={value!r}")
    if missing:
        return "The constructors must set these parameters literally: " + ", ".join(missing) + "."
    return ""


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
