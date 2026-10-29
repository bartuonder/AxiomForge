import time
import pandas as pd
from datasets import load_dataset
frame = load_dataset("inria-soda/tabular-benchmark", "clf_num_MagicTelescope", split="train").to_pandas()
frame = frame.sample(n=6000, random_state=0).reset_index(drop=True)
y = (frame["class"] == 'h').astype(int).to_numpy()
X = frame.drop(columns=["class"])
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
print(f"dataset=tb_magic samples={len(y)} features={X.shape[1]} negative_ratio={(y == 0).mean():.2f} positive_ratio={(y == 1).mean():.2f}")
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, average_precision_score, confusion_matrix
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
models = {
    "RandomForest": with_preprocessing(RandomForestClassifier(random_state=0)),
    "HistGradientBoosting": with_preprocessing(HistGradientBoostingClassifier(random_state=0)),
    "MLP": with_preprocessing(MLPClassifier(max_iter=500, random_state=0)),
    "LogisticRegression": with_preprocessing(LogisticRegression(max_iter=1000, random_state=0)),
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
