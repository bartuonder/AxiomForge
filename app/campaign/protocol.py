from typing import Any

from app.campaign.descriptors import descriptors_code
from app.campaign.provenance import provenance_code
from app.campaign.tuning import TuningError, tuning_code, validate_tuning
from app.datasets import DATASETS, loader_code, pinned_loader_code
from app.seeds import SPLIT_SEEDS
from app.variants import baseline_name

ESTIMATORS: dict[str, dict[str, Any]] = {
    "LinearSVC": {"module": "sklearn.svm", "cls": "LinearSVC", "fixed": {"max_iter": 5000, "random_state": 0}},
    "SVM": {"module": "sklearn.svm", "cls": "SVC", "fixed": {"probability": True, "random_state": 0}},
    "RandomForest": {"module": "sklearn.ensemble", "cls": "RandomForestClassifier", "fixed": {"random_state": 0}},
    "LogisticRegression": {"module": "sklearn.linear_model", "cls": "LogisticRegression", "fixed": {"max_iter": 1000, "random_state": 0}},
    "DecisionTree": {"module": "sklearn.tree", "cls": "DecisionTreeClassifier", "fixed": {"random_state": 0}},
    "GradientBoosting": {"module": "sklearn.ensemble", "cls": "GradientBoostingClassifier", "fixed": {"random_state": 0}},
    "HistGradientBoosting": {"module": "sklearn.ensemble", "cls": "HistGradientBoostingClassifier", "fixed": {"random_state": 0}},
    "XGBoost": {"module": "xgboost", "cls": "XGBClassifier", "fixed": {"random_state": 0, "eval_metric": "logloss"}, "package": "xgboost"},
    "LightGBM": {"module": "lightgbm", "cls": "LGBMClassifier", "fixed": {"random_state": 0, "verbose": -1}, "package": "lightgbm"},
    "CatBoost": {"module": "catboost", "cls": "CatBoostClassifier", "fixed": {"random_seed": 0, "verbose": 0}, "package": "catboost"},
    "KNN": {"module": "sklearn.neighbors", "cls": "KNeighborsClassifier", "fixed": {}},
    "GaussianNB": {"module": "sklearn.naive_bayes", "cls": "GaussianNB", "fixed": {}},
    "MLP": {"module": "sklearn.neural_network", "cls": "MLPClassifier", "fixed": {"max_iter": 500, "random_state": 0}},
    "AdaBoost": {"module": "sklearn.ensemble", "cls": "AdaBoostClassifier", "fixed": {"random_state": 0}},
    "ExtraTrees": {"module": "sklearn.ensemble", "cls": "ExtraTreesClassifier", "fixed": {"random_state": 0}},
    "QDA": {"module": "sklearn.discriminant_analysis", "cls": "QuadraticDiscriminantAnalysis", "fixed": {}},
    "LDA": {"module": "sklearn.discriminant_analysis", "cls": "LinearDiscriminantAnalysis", "fixed": {}},
}

MIN_CAMPAIGN_MODELS = 2


class ProtocolError(ValueError):
    pass


def _arguments(values: dict[str, Any]) -> str:
    return ", ".join(f"{name}={value!r}" for name, value in values.items())


def _constructor(model: str, params: dict[str, Any] | None) -> str:
    entry = ESTIMATORS[model]
    return f"{entry['cls']}({_arguments({**entry['fixed'], **(params or {})})})"


def build_script(
    dataset: str,
    models: list[str],
    params: dict[str, dict[str, Any]] | None = None,
    seeds: tuple[int, ...] = SPLIT_SEEDS,
    tuning: dict[str, int] | None = None,
    revisions: dict[str, str] | None = None,
) -> str:
    if dataset not in DATASETS:
        raise ProtocolError(f"unknown dataset {dataset}")
    if len(models) < MIN_CAMPAIGN_MODELS or len(set(models)) != len(models):
        raise ProtocolError("a campaign needs at least two different models")
    unknown = [model for model in models if model not in ESTIMATORS]
    if unknown:
        raise ProtocolError("unknown models: " + ", ".join(unknown))
    params = {model: values for model, values in (params or {}).items() if values}
    stray = [model for model in params if model not in models]
    if stray:
        raise ProtocolError("parameters for models that are not in the campaign: " + ", ".join(stray))
    if not seeds:
        raise ProtocolError("at least one split seed is needed")
    try:
        tuning = validate_tuning(tuning, models)
    except TuningError as exc:
        raise ProtocolError(str(exc)) from exc
    if tuning and params:
        raise ProtocolError("tuning and listed parameters cannot be combined")

    packages = list(dict.fromkeys(ESTIMATORS[model]["package"] for model in models if "package" in ESTIMATORS[model]))
    lines: list[str] = []
    if packages:
        lines.append("import subprocess, sys")
        lines.extend(
            f"subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '{package}'], check=True)" for package in packages
        )
    lines.append("import time")
    revision = (revisions or {}).get(dataset)
    if revision:
        try:
            lines.append(pinned_loader_code(dataset, revision))
        except ValueError as exc:
            raise ProtocolError(str(exc)) from exc
    else:
        lines.append(loader_code(dataset))
    lines.append(provenance_code(dataset, packages, revision))
    lines.append(descriptors_code())
    lines.append("from sklearn.model_selection import train_test_split")
    lines.append("from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, average_precision_score, confusion_matrix")
    imports: dict[str, list[str]] = {}
    for model in models:
        entry = ESTIMATORS[model]
        imports.setdefault(entry["module"], [])
        if entry["cls"] not in imports[entry["module"]]:
            imports[entry["module"]].append(entry["cls"])
    lines.extend(f"from {module} import {', '.join(names)}" for module, names in imports.items())
    entries: list[str] = []
    if tuning:
        lines.append(tuning_code(models, tuning["iterations"], tuning["folds"], ESTIMATORS, tuning.get("share")))
    for model in models:
        if tuning:
            entry = ESTIMATORS[model]
            entries.append(f'    "{model}": with_preprocessing({entry["cls"]}(**{{**{entry["fixed"]!r}, **tuned[{model!r}]}})),')
            entries.append(f'    "{baseline_name(model)}": with_preprocessing({_constructor(model, None)}),')
            continue
        entries.append(f'    "{model}": with_preprocessing({_constructor(model, params.get(model))}),')
        if model in params:
            entries.append(f'    "{baseline_name(model)}": with_preprocessing({_constructor(model, None)}),')
    lines.append("models = {\n" + "\n".join(entries) + "\n}")
    lines.append(f"seeds = {list(seeds)!r}")
    lines.append(
        "\n".join(
            [
                "for seed in seeds:",
                "    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)",
                "    for name, model in models.items():",
                "        start = time.time()",
                "        model.fit(X_train, y_train)",
                "        train_seconds = time.time() - start",
                "        scores = model.predict_proba(X_test)[:, 1] if hasattr(model, 'predict_proba') else model.decision_function(X_test)",
                "        predicted = model.predict(X_test)",
                "        tn, fp, fn, tp = confusion_matrix(y_test, predicted).ravel()",
                "        print(",
                "            f'model={name} accuracy={accuracy_score(y_test, predicted):.4f} f1={f1_score(y_test, predicted):.4f} '",
                "            f'roc_auc={roc_auc_score(y_test, scores):.4f} pr_auc={average_precision_score(y_test, scores):.4f} '",
                "            f'train_seconds={train_seconds:.4f} tn={tn} fp={fp} fn={fn} tp={tp}'",
                "        )",
            ]
        )
    )
    return "\n".join(lines) + "\n"
