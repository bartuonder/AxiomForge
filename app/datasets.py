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

BENCHMARK_ID = "inria-soda/tabular-benchmark"
BENCHMARK_ROWS = 6000

BENCHMARK_POOL = (
    ("tb_credit", "clf_num_credit", "SeriousDlqin2yrs", 1, "credit scoring, serious delinquency in two years, 10 numeric features"),
    ("tb_california", "clf_num_california", "price_above_median", 1, "California housing, house price above the median, 8 numeric features"),
    ("tb_electricity", "clf_num_electricity", "class", "UP", "electricity market, price movement up against down, 7 numeric features"),
    ("tb_magic", "clf_num_MagicTelescope", "class", "h", "MAGIC gamma telescope, hadron against gamma shower, 10 numeric features"),
    ("tb_bank", "clf_num_bank-marketing", "Class", 2, "bank marketing campaign, subscription outcome, 7 numeric features"),
    ("tb_heloc", "clf_num_heloc", "RiskPerformance", 1, "HELOC home equity credit risk performance, 22 numeric features"),
    ("tb_house16h", "clf_num_house_16H", "binaryClass", "P", "house 16H census prices, binary class, 16 numeric features"),
    ("tb_pol", "clf_num_pol", "binaryClass", "P", "pol telecommunication data, binary class, 26 numeric features"),
    ("tb_eye", "clf_num_eye_movements", "label", 1, "eye movements in reading, relevance label, 20 numeric features"),
)

for _key, _config, _target, _positive, _summary in BENCHMARK_POOL:
    DATASETS[_key] = {
        "hf_id": BENCHMARK_ID,
        "config": _config,
        "group": "benchmark",
        "summary": f"Tabular benchmark of Grinsztajn et al. 2022, {_summary}; classes balanced 50/50 by the benchmark; {BENCHMARK_ROWS} rows sampled",
        "topics": "benchmark",
        "target": _target,
        "positive": _positive,
        "drop": [],
        "clean": [],
        "max_rows": BENCHMARK_ROWS,
    }

EXTENDED_POOL = (
    ("tb_bioresponse", "clf_num_Bioresponse", "target", 1, "Bioresponse, biological response of molecules, 419 numeric features", None),
    ("tb_diabetes", "clf_num_Diabetes130US", "readmitted", 1, "Diabetes 130 US hospitals, readmission outcome, 7 numeric features", BENCHMARK_ROWS),
    ("tb_higgs", "clf_num_Higgs", "target", 1, "Higgs boson signal against background, 24 numeric features", BENCHMARK_ROWS),
    ("tb_miniboone", "clf_num_MiniBooNE", "signal", True, "MiniBooNE neutrino signal against background, 50 numeric features", BENCHMARK_ROWS),
    ("tb_covertype", "clf_num_covertype", "Y", 1, "forest cover type, binary class, 10 numeric features", BENCHMARK_ROWS),
    ("tb_creditcard", "clf_num_default-of-credit-card-clients", "y", 1, "default of credit card clients, 20 numeric features", BENCHMARK_ROWS),
    ("tb_jannis", "clf_num_jannis", "class", 1, "Jannis, binary class, 54 numeric features", BENCHMARK_ROWS),
)

for _key, _config, _target, _positive, _summary, _rows in EXTENDED_POOL:
    DATASETS[_key] = {
        "hf_id": BENCHMARK_ID,
        "config": _config,
        "group": "extended",
        "summary": f"Tabular benchmark of Grinsztajn et al. 2022, {_summary}; classes balanced 50/50 by the benchmark; "
        + (f"{_rows} rows sampled" if _rows else "all rows used"),
        "topics": "benchmark",
        "target": _target,
        "positive": _positive,
        "drop": [],
        "clean": [],
        "max_rows": _rows,
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


def core_keys() -> list[str]:
    return [key for key, entry in DATASETS.items() if entry.get("group", "core") == "core"]


def benchmark_keys() -> list[str]:
    return [key for key, entry in DATASETS.items() if entry.get("group") == "benchmark"]


def extended_keys() -> list[str]:
    return [key for key, entry in DATASETS.items() if entry.get("group") == "extended"]


def research_pool() -> list[str]:
    return benchmark_keys() + extended_keys()


def hf_ids() -> list[str]:
    return [str(entry["hf_id"]) for entry in DATASETS.values()]


def dataset_menu() -> str:
    return "\n".join(
        f"- {key}: {DATASETS[key]['summary']}. Fits queries about {DATASETS[key]['topics']}."
        for key in core_keys()
    )


def describe(key: str) -> str:
    entry = DATASETS[key]
    where = f"{entry['hf_id']} ({entry['config']})" if entry.get("config") else entry["hf_id"]
    return f"Hugging Face dataset {where}: {entry['summary']}"


REVISION = re.compile(r"[0-9a-f]{40}")


def pinned_loader_code(key: str, revision: str) -> str:
    if not REVISION.fullmatch(str(revision)):
        raise ValueError("revision must be a 40 character commit hash in lower case hexadecimal")
    return loader_code(key).replace('split="train")', f'split="train", revision="{revision}")', 1)


def loader_code(key: str) -> str:
    entry = DATASETS[key]
    lines = [
        "import pandas as pd",
        "from datasets import load_dataset",
        (
            f'frame = load_dataset("{entry["hf_id"]}", "{entry["config"]}", split="train").to_pandas()'
            if entry.get("config")
            else f'frame = load_dataset("{entry["hf_id"]}", split="train").to_pandas()'
        ),
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
    for key in core_keys():
        entry = DATASETS[key]
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
