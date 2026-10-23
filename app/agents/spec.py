import ast
import json
import re
from typing import Any

from app.variants import baseline_name, configured_models

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
        "claim": _validate_claim(raw.get("claim"), model_keys, statement),
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
