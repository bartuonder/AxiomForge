import ast
import re
from typing import Any

SYNTHETIC_CALLS = frozenset(
    {
        "make_classification",
        "make_blobs",
        "make_moons",
        "make_circles",
        "make_gaussian_quantiles",
        "make_hastie_10_2",
        "make_friedman1",
        "make_friedman2",
        "make_friedman3",
        "load_breast_cancer",
        "load_iris",
        "load_wine",
        "load_digits",
        "fetch_openml",
        "fetch_covtype",
        "fetch_kddcup99",
        "fetch_california_housing",
        "fetch_20newsgroups",
    }
)

DATASETS: dict[str, dict[str, Any]] = {
    "breast_cancer": {
        "hf_id": "scikit-learn/breast-cancer-wisconsin",
        "summary": "Wisconsin breast cancer diagnosis, 569 rows, 30 numeric tumour measurements, malignant against benign (about 37% malignant)",
        "topics": "medical, diagnosis, cancer, tumour, health, clinical",
        "target": "diagnosis",
        "positive": "M",
        "drop": ["id", "Unnamed: 32"],
        "clean": [],
        "max_rows": None,
    },
    "credit_default": {
        "hf_id": "scikit-learn/credit-card-clients",
        "summary": "Taiwan credit card clients, 30000 rows (6000 sampled), 23 numeric features, default on the next payment (about 22% default)",
        "topics": "credit, loan, default, risk, banking, finance, payment",
        "target": "default.payment.next.month",
        "positive": 1,
        "drop": ["ID"],
        "clean": [],
        "max_rows": 6000,
    },
    "customer_churn": {
        "hf_id": "scikit-learn/churn-prediction",
        "summary": "Telecom customer churn, 7043 rows, 19 numeric and categorical customer features, churn against stay (about 27% churn)",
        "topics": "customer, churn, telecom, subscription, retention, marketing",
        "target": "Churn",
        "positive": "Yes",
        "drop": ["customerID"],
        "clean": ['frame["TotalCharges"] = pd.to_numeric(frame["TotalCharges"], errors="coerce")'],
        "max_rows": None,
    },
    "adult_income": {
        "hf_id": "scikit-learn/adult-census-income",
        "summary": "US adult census income, 32561 rows (6000 sampled), 14 numeric and categorical features, income above 50K (about 24% positive)",
        "topics": "income, census, demographic, salary, employment, social",
        "target": "income",
        "positive": ">50K",
        "drop": [],
        "clean": [],
        "max_rows": 6000,
    },
    "credit_fraud": {
        "hf_id": "David-Egea/Creditcard-fraud-detection",
        "summary": "European credit card transactions, 30 numeric features, fraud against legitimate; all 492 frauds plus 4000 legitimate rows (about 11% fraud, the full set has 0.17%)",
        "topics": "fraud, fraudulent, credit card, anomaly, transaction, payment, security, rare event",
        "target": "Class",
        "positive": 1,
        "drop": [],
        "clean": [],
        "max_rows": None,
        "keep_positives": 4000,
    },
}

PREPROCESSING_LINES = (
    "from sklearn.base import clone",
    "from sklearn.compose import ColumnTransformer",
    "from sklearn.impute import SimpleImputer",
    "from sklearn.pipeline import Pipeline",
    "from sklearn.preprocessing import OneHotEncoder, StandardScaler",
    'categorical = list(X.select_dtypes(exclude="number").columns)',
    "numeric = [column for column in X.columns if column not in categorical]",
    "preprocessor = ColumnTransformer([",
    '    ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),',
    '    ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),',
    "])",
    "def with_preprocessing(estimator):",
    '    return Pipeline([("prep", clone(preprocessor)), ("model", estimator)])',
)


def dataset_keys() -> list[str]:
    return list(DATASETS)


def hf_ids() -> list[str]:
    return [str(entry["hf_id"]) for entry in DATASETS.values()]


def dataset_menu() -> str:
    return "\n".join(
        f"- {key}: {entry['summary']}. Fits queries about {entry['topics']}."
        for key, entry in DATASETS.items()
    )


def describe(key: str) -> str:
    entry = DATASETS[key]
    return f"Hugging Face dataset {entry['hf_id']}: {entry['summary']}"


def loader_code(key: str) -> str:
    entry = DATASETS[key]
    lines = [
        "import pandas as pd",
        "from datasets import load_dataset",
        f'frame = load_dataset("{entry["hf_id"]}", split="train").to_pandas()',
    ]
    if entry["drop"]:
        columns = ", ".join(f'"{name}"' for name in entry["drop"])
        lines.append(f"frame = frame.drop(columns=[{columns}])")
    lines.extend(entry["clean"])
    target = entry["target"]
    if entry.get("keep_positives"):
        lines.append(f'positives = frame[frame["{target}"] == {entry["positive"]!r}]')
        lines.append(f'negatives = frame[frame["{target}"] != {entry["positive"]!r}].sample(n={entry["keep_positives"]}, random_state=0)')
        lines.append("frame = pd.concat([positives, negatives]).sample(frac=1, random_state=0).reset_index(drop=True)")
    elif entry["max_rows"]:
        lines.append(f"frame = frame.sample(n={entry['max_rows']}, random_state=0).reset_index(drop=True)")
    lines.append(f'y = (frame["{target}"] == {entry["positive"]!r}).astype(int).to_numpy()')
    lines.append(f'X = frame.drop(columns=["{target}"])')
    lines.extend(PREPROCESSING_LINES)
    lines.append(
        f'print(f"dataset={key} samples={{len(y)}} features={{X.shape[1]}} '
        'negative_ratio={(y == 0).mean():.2f} positive_ratio={(y == 1).mean():.2f}")'
    )
    return "\n".join(lines)


def _call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _statement_dump(node: ast.stmt) -> str:
    return ast.dump(node, annotate_fields=False, include_attributes=False)


def dataset_code_error(code: str, key: str | None) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""
    synthetic = sorted(_call_names(tree) & SYNTHETIC_CALLS)
    if synthetic:
        return (
            "The data must come from Hugging Face datasets, not from "
            + ", ".join(synthetic)
            + ". Paste the data block you were given."
        )
    present = {_statement_dump(node) for node in tree.body}
    keys = [key] if key else dataset_keys()
    last_missing = ""
    for candidate in keys:
        missing = [
            statement
            for statement in ast.parse(loader_code(candidate)).body
            if _statement_dump(statement) not in present
        ]
        if not missing:
            return ""
        first = ast.unparse(missing[0]).splitlines()[0]
        last_missing = f"The data block for {candidate} must be pasted unchanged at the top level of the script; this statement is missing or changed: {first}"
    return last_missing


DEFAULT_DATASET = "customer_churn"


def pick_dataset(text: str) -> str:
    lowered = text.lower()
    best, best_score = DEFAULT_DATASET, 0
    for key, entry in DATASETS.items():
        words = [word.strip() for word in str(entry["topics"]).split(",")]
        score = sum(1 for word in words if re.search(rf"\b{re.escape(word)}", lowered))
        if score > best_score:
            best, best_score = key, score
    return best


def data_brief(key: str) -> str:
    return (
        f"Data: {describe(key)}.\n"
        "Paste this data block unchanged at the top level of the script, before the models dict, "
        "and do not generate or simulate data with any sklearn.datasets generator or loader. "
        "The block already prints the dataset line, so print no other dataset line. "
        "Build every models value as with_preprocessing(<estimator>) so that imputation, scaling and encoding "
        "are fitted inside each training part only, and do not fit any transformer on the whole data.\n"
        f"{loader_code(key)}"
    )
