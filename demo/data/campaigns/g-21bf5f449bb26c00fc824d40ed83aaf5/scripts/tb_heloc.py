import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'xgboost'], check=True)
import time
import pandas as pd
from datasets import load_dataset
frame = load_dataset("inria-soda/tabular-benchmark", "clf_num_heloc", split="train").to_pandas()
frame = frame.sample(n=6000, random_state=0).reset_index(drop=True)
y = (frame["RiskPerformance"] == 1).astype(int).to_numpy()
X = frame.drop(columns=["RiskPerformance"])
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
categorical = list(X.select_dtypes(exclude="number").columns)
numeric = [column for column in X.columns if column not in categorical]
preprocessor = ColumnTransformer([
    ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
    ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
])
def with_preprocessing(estimator):
    return Pipeline([("prep", clone(preprocessor)), ("model", estimator)])
print(f"dataset=tb_heloc samples={len(y)} features={X.shape[1]} negative_ratio={(y == 0).mean():.2f} positive_ratio={(y == 1).mean():.2f}")
import sys
import importlib.metadata as _metadata
def _version(name):
    try:
        return _metadata.version(name)
    except Exception:
        return 'unknown'
try:
    from huggingface_hub import HfApi
    _revision = HfApi().dataset_info('inria-soda/tabular-benchmark').sha or 'unknown'
except Exception:
    _revision = 'unknown'
_packages = ['numpy', 'pandas', 'scikit-learn', 'scipy', 'datasets', 'xgboost']
print("provenance revision=" + _revision + " python=" + sys.version.split()[0] + " " + " ".join(name + "=" + _version(name) for name in _packages))
import numpy as _np
_numeric = X.select_dtypes(include='number')
_filled = _numeric.fillna(_numeric.median())
_categorical_share = (X.shape[1] - _numeric.shape[1]) / max(1, X.shape[1])
_correlation = 0.0
if _filled.shape[1] > 1:
    with _np.errstate(all='ignore'):
        _matrix = _np.nan_to_num(_np.abs(_np.corrcoef(_filled.to_numpy(dtype=float), rowvar=False)))
    _correlation = float(_matrix[_np.triu_indices_from(_matrix, k=1)].mean())
_skew = float(_np.nan_to_num(_filled.skew().abs().to_numpy(dtype=float)).mean()) if _filled.shape[1] else 0.0
_missing = float(X.isna().to_numpy().mean())
print('descriptors categorical_share=%.4f mean_abs_correlation=%.4f mean_abs_skew=%.4f missing_share=%.4f' % (_categorical_share, _correlation, _skew, _missing))
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, average_precision_score, confusion_matrix
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
import json
from sklearn.model_selection import ParameterSampler, cross_val_score
X_tune, X, y_tune, y = train_test_split(X, y, train_size=0.2, random_state=0, stratify=y)
print('tuning rows_tune=%d rows_eval=%d' % (len(y_tune), len(y)))
spaces = {'XGBoost': {'n_estimators': [100, 200, 400], 'learning_rate': [0.03, 0.1, 0.3], 'max_depth': [3, 6, 10]}, 'RandomForest': {'n_estimators': [100, 200, 400], 'max_depth': [None, 5, 10, 20], 'min_samples_leaf': [1, 2, 5]}, 'MLP': {'hidden_layer_sizes': [(50,), (100,), (100, 50), (200,)], 'alpha': [1e-05, 0.0001, 0.001, 0.01], 'learning_rate_init': [0.001, 0.003, 0.01]}}
fixed = {'XGBoost': {'random_state': 0, 'eval_metric': 'logloss'}, 'RandomForest': {'random_state': 0}, 'MLP': {'max_iter': 500, 'random_state': 0}}
sizes = {'XGBoost': 12, 'RandomForest': 12, 'MLP': 12}
classes = {'XGBoost': XGBClassifier, 'RandomForest': RandomForestClassifier, 'MLP': MLPClassifier}
tuned = {}
for name, space in spaces.items():
    best_score, best_params = -1.0, {}
    for candidate in ParameterSampler(space, n_iter=sizes[name], random_state=0):
        estimator = with_preprocessing(classes[name](**{**fixed[name], **candidate}))
        score = cross_val_score(estimator, X_tune, y_tune, cv=3, scoring='roc_auc', n_jobs=-1, error_score=float('nan')).mean()
        if score > best_score:
            best_score, best_params = score, candidate
    tuned[name] = best_params
    print('tuned model=%s cv_roc_auc=%.4f params=%s' % (name, best_score, json.dumps(best_params)))
models = {
    "XGBoost": with_preprocessing(XGBClassifier(**{**{'random_state': 0, 'eval_metric': 'logloss'}, **tuned['XGBoost']})),
    "XGBoost__default": with_preprocessing(XGBClassifier(random_state=0, eval_metric='logloss')),
    "RandomForest": with_preprocessing(RandomForestClassifier(**{**{'random_state': 0}, **tuned['RandomForest']})),
    "RandomForest__default": with_preprocessing(RandomForestClassifier(random_state=0)),
    "MLP": with_preprocessing(MLPClassifier(**{**{'max_iter': 500, 'random_state': 0}, **tuned['MLP']})),
    "MLP__default": with_preprocessing(MLPClassifier(max_iter=500, random_state=0)),
}
seeds = [42, 100, 200, 300, 400, 500, 600, 700, 800, 900]
for seed in seeds:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)
    for name, model in models.items():
        start = time.time()
        model.fit(X_train, y_train)
        train_seconds = time.time() - start
        scores = model.predict_proba(X_test)[:, 1] if hasattr(model, 'predict_proba') else model.decision_function(X_test)
        predicted = model.predict(X_test)
        tn, fp, fn, tp = confusion_matrix(y_test, predicted).ravel()
        print(
            f'model={name} accuracy={accuracy_score(y_test, predicted):.4f} f1={f1_score(y_test, predicted):.4f} '
            f'roc_auc={roc_auc_score(y_test, scores):.4f} pr_auc={average_precision_score(y_test, scores):.4f} '
            f'train_seconds={train_seconds:.4f} tn={tn} fp={fp} fn={fn} tp={tp}'
        )
