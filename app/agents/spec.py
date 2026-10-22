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
