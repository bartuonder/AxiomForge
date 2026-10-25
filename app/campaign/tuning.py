import json
import math
import re
from typing import Any

MIN_ITERATIONS = 4
MAX_ITERATIONS = 40
DEFAULT_ITERATIONS = 12
MIN_FOLDS = 3
MAX_FOLDS = 5
DEFAULT_FOLDS = 3
TUNING_SHARE = 0.2
TUNING_SEED = 0

_FOREST = {"n_estimators": [100, 200, 400], "max_depth": [None, 5, 10, 20], "min_samples_leaf": [1, 2, 5]}
_BOOSTING = {"n_estimators": [100, 200, 400], "learning_rate": [0.03, 0.1, 0.3], "max_depth": [3, 6, 10]}

SEARCH_SPACES: dict[str, dict[str, list[Any]]] = {
    "LinearSVC": {"C": [0.01, 0.1, 1.0, 10.0, 100.0]},
    "SVM": {"C": [0.1, 1.0, 10.0, 100.0], "gamma": ["scale", "auto", 0.01, 0.1], "kernel": ["rbf", "linear"]},
    "RandomForest": _FOREST,
    "ExtraTrees": _FOREST,
    "LogisticRegression": {"C": [0.01, 0.1, 1.0, 10.0, 100.0], "class_weight": [None, "balanced"]},
    "DecisionTree": {"max_depth": [3, 5, 10, 20, None], "min_samples_leaf": [1, 5, 20, 50]},
    "GradientBoosting": {"n_estimators": [50, 100, 200], "learning_rate": [0.03, 0.1, 0.3], "max_depth": [2, 3, 5]},
    "HistGradientBoosting": {"learning_rate": [0.03, 0.1, 0.3], "max_depth": [None, 3, 6, 10], "max_iter": [100, 200, 400]},
    "XGBoost": _BOOSTING,
    "LightGBM": _BOOSTING,
    "CatBoost": {"iterations": [100, 300, 600], "learning_rate": [0.03, 0.1, 0.3], "depth": [4, 6, 8]},
    "KNN": {"n_neighbors": [3, 5, 10, 20, 50], "weights": ["uniform", "distance"]},
    "GaussianNB": {"var_smoothing": [1e-9, 1e-8, 1e-7, 1e-6, 1e-5]},
    "MLP": {"hidden_layer_sizes": [(50,), (100,), (100, 50), (200,)], "alpha": [1e-5, 1e-4, 1e-3, 1e-2], "learning_rate_init": [0.001, 0.003, 0.01]},
    "AdaBoost": {"n_estimators": [50, 100, 200], "learning_rate": [0.1, 0.5, 1.0]},
    "QDA": {"reg_param": [0.0, 0.1, 0.3, 0.5, 0.8]},
    "LDA": {"solver": ["lsqr"], "shrinkage": [None, "auto", 0.1, 0.5]},
}

_TUNED = re.compile(r"^tuned model=(?P<model>\S+) cv_roc_auc=(?P<score>\S+) params=(?P<params>\{.*\})$", re.MULTILINE)
_SPLIT = re.compile(r"^tuning rows_tune=(?P<tune>\d+) rows_eval=(?P<evaluation>\d+)$", re.MULTILINE)


class TuningError(ValueError):
    pass


def effective_params(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if spec.get("tuning"):
        return {model: {"tuned": True} for model in spec["models"]}
    return spec.get("params") or {}


def grid_size(model: str) -> int:
    return math.prod(len(values) for values in SEARCH_SPACES[model].values())


def validate_tuning(raw: Any, models: list[str]) -> dict[str, int]:
    if raw in (None, False, {}):
        return {}
    if not isinstance(raw, dict):
        raise TuningError("tuning must be an object with iterations and folds")
    unknown = sorted(set(raw) - {"iterations", "folds"})
    if unknown:
        raise TuningError("tuning has unknown fields: " + ", ".join(unknown))
    values = {}
    for name, default, low, high in (("iterations", DEFAULT_ITERATIONS, MIN_ITERATIONS, MAX_ITERATIONS), ("folds", DEFAULT_FOLDS, MIN_FOLDS, MAX_FOLDS)):
        value = raw.get(name, default)
        if not isinstance(value, int) or not low <= value <= high:
            raise TuningError(f"tuning {name} must be a whole number from {low} to {high}")
        values[name] = value
    missing = [model for model in models if model not in SEARCH_SPACES]
    if missing:
        raise TuningError("these models have no search space: " + ", ".join(missing))
    return values


def tuning_code(models: list[str], iterations: int, folds: int, estimators: dict[str, dict[str, Any]]) -> str:
    spaces = {model: SEARCH_SPACES[model] for model in models}
    classes = {model: estimators[model]["cls"] for model in models}
    fixed = {model: estimators[model]["fixed"] for model in models}
    sizes = {model: min(iterations, grid_size(model)) for model in models}
    class_map = "{" + ", ".join(f"{model!r}: {estimators[model]['cls']}" for model in models) + "}"
    return "\n".join(
        [
            "import json",
            "from sklearn.model_selection import ParameterSampler, cross_val_score",
            f"X_tune, X, y_tune, y = train_test_split(X, y, train_size={TUNING_SHARE!r}, random_state={TUNING_SEED!r}, stratify=y)",
            "print('tuning rows_tune=%d rows_eval=%d' % (len(y_tune), len(y)))",
            f"spaces = {spaces!r}",
            f"fixed = {fixed!r}",
            f"sizes = {sizes!r}",
            f"classes = {class_map}",
            "tuned = {}",
            "for name, space in spaces.items():",
            "    best_score, best_params = -1.0, {}",
            "    for candidate in ParameterSampler(space, n_iter=sizes[name], random_state=0):",
            "        estimator = with_preprocessing(classes[name](**{**fixed[name], **candidate}))",
            f"        score = cross_val_score(estimator, X_tune, y_tune, cv={folds!r}, scoring='roc_auc', n_jobs=-1, error_score=float('nan')).mean()",
            "        if score > best_score:",
            "            best_score, best_params = score, candidate",
            "    tuned[name] = best_params",
            "    print('tuned model=%s cv_roc_auc=%.4f params=%s' % (name, best_score, json.dumps(best_params)))",
        ]
    )


def parse_tuning(output: str) -> dict[str, Any]:
    split = _SPLIT.search(output)
    models: dict[str, dict[str, Any]] = {}
    for match in _TUNED.finditer(output):
        try:
            params = json.loads(match.group("params"))
            score = float(match.group("score"))
        except ValueError:
            continue
        models[match.group("model")] = {"cv_roc_auc": score, "params": params}
    if split is None and not models:
        return {}
    return {
        "rows_tune": int(split.group("tune")) if split else 0,
        "rows_eval": int(split.group("evaluation")) if split else 0,
        "models": models,
    }
