import ast
import re

from openai import OpenAI

from app.agents.spec import call_name, spec_brief
from app.config import OPENAI_API_KEY
from app.seeds import SPLIT_SEEDS

MODEL = "gpt-4o"
PROMPT_VERSION = "experiment-v7"
QUERY_NAMES_NO_MODEL = "query names no model"


class QueryNamesNoModel(RuntimeError):
    def __init__(self) -> None:
        super().__init__(QUERY_NAMES_NO_MODEL)


SYSTEM_PROMPT = (
    "You write one complete Python script for the comparison asked in the user question. "
    "Train only the estimators named under Allowed models. "
    "Do not add an estimator that Allowed models does not list. "
    "A hypothesis or an earlier experiment must not add one. "
    "Assign one dict named models. "
    "Its keys are exactly the allowed names, in the listed order, and its values are unfitted estimators. "
    "Do not construct an estimator outside that dict. "
    "Train every models entry on the same rows and the same train/test split in each loop pass. "
    "When an Experiment specification is given, its dataset and parameters decide the data and the constructor arguments. "
    "Do not use a tiny synthetic CSV as the only data. "
    "Load a realistic classification dataset from sklearn.datasets, such as load_breast_cancer, "
    "or build a clearly imbalanced set with sklearn.datasets.make_classification. "
    "Veri Üretimi Sabiti: Veriyi herhangi bir döngünün dışında tek bir kere yükle veya üret. "
    "make_classification kullanıyorsan class_sep 0.5 veya daha düşük olsun ve weights ile net bir imbalanced dağılım kur. "
    "Veri üretiminin random_state değeri sabit bir tam sayı olsun ve split döngüsünde değişmesin. "
    "Seed Döngüsü Protokolü: Test döngüsü yalnız train_test_split random_state değerini değiştirir. "
    f"Döngü tam olarak şu {len(SPLIT_SEEDS)} tohum olsun, bu sırayla: {', '.join(str(seed) for seed in SPLIT_SEEDS)}. "
    "Every train_test_split call must pass stratify=y, the label array, so that every split keeps the class ratio. "
    "Model random_state ve veri üretim tohumu döngünün dışında sabit kalsın. "
    "Başka bir random_state bu döngüde değişmesin. "
    "Dengesiz (imbalanced) veri setlerinde asla sadece Accuracy'ye güvenme; "
    "kodun mutlaka ROC-AUC ve PR-AUC'yi de ölçmelidir. "
    "Terminoloji Kesinliği: Standart sapma ile varyansı karıştırma. Varyans, standart sapmanın karesidir. "
    "Before any model line, print exactly one dataset line: "
    "dataset=<name> samples=<int> features=<int> negative_ratio=<float> positive_ratio=<float> "
    "negative_ratio is the share of the negative class and positive_ratio is the share of the positive class. "
    "Use accuracy_score, f1_score, roc_auc_score, average_precision_score, and confusion_matrix. "
    "Time only model.fit with time.time(). "
    "If an allowed model is not already installed, install its package with subprocess before importing it. "
    "Inside the split loop, print one line per model for that split and no other output. "
    f"Each model name appears exactly {len(SPLIT_SEEDS)} times. The printed name is the models key. "
    "model=<name> accuracy=<float> f1=<float> roc_auc=<float> pr_auc=<float> "
    "train_seconds=<float> tn=<int> fp=<int> fn=<int> tp=<int> "
    "Do not wrap the source in markdown. Do not explain it. Do not use comments."
)

_MODEL_SPECS: tuple[dict, ...] = (
    {
        "key": "LinearSVC",
        "aliases": ("linear svc", "linearsvc", "linear support vector"),
        "hint": "sklearn.svm.LinearSVC. Use decision_function for ROC-AUC and PR-AUC.",
        "classes": ("LinearSVC",),
        "modules": (),
    },
    {
        "key": "SVM",
        "aliases": (
            "support vector machine",
            "support vector",
            "svm",
            "svc",
            "destek vektör",
            "destek vektor",
        ),
        "hint": "sklearn.svm.SVC(probability=True).",
        "classes": ("SVC",),
        "modules": (),
    },
    {
        "key": "RandomForest",
        "aliases": ("random forest", "randomforest", "rf", "rastgele orman"),
        "hint": "sklearn.ensemble.RandomForestClassifier.",
        "classes": ("RandomForestClassifier",),
        "modules": (),
    },
    {
        "key": "LogisticRegression",
        "aliases": ("logistic regression", "logisticregression", "lojistik regresyon"),
        "hint": "sklearn.linear_model.LogisticRegression.",
        "classes": ("LogisticRegression",),
        "modules": (),
    },
    {
        "key": "DecisionTree",
        "aliases": ("decision tree", "decisiontree", "karar ağacı", "karar agaci"),
        "hint": "sklearn.tree.DecisionTreeClassifier.",
        "classes": ("DecisionTreeClassifier",),
        "modules": (),
    },
    {
        "key": "GradientBoosting",
        "aliases": ("gradient boosting", "gradientboosting", "gradyan artırma", "gradyan artirma"),
        "hint": "sklearn.ensemble.GradientBoostingClassifier.",
        "classes": ("GradientBoostingClassifier",),
        "modules": (),
    },
    {
        "key": "HistGradientBoosting",
        "aliases": ("hist gradient boosting", "histgradientboosting"),
        "hint": "sklearn.ensemble.HistGradientBoostingClassifier.",
        "classes": ("HistGradientBoostingClassifier",),
        "modules": (),
    },
    {
        "key": "XGBoost",
        "aliases": ("xgboost", "xgb"),
        "hint": "xgboost.XGBClassifier. Install xgboost with subprocess before importing it.",
        "classes": ("XGBClassifier",),
        "modules": ("xgboost",),
    },
    {
        "key": "LightGBM",
        "aliases": ("lightgbm", "lgbm"),
        "hint": "lightgbm.LGBMClassifier. Install lightgbm with subprocess before importing it.",
        "classes": ("LGBMClassifier",),
        "modules": ("lightgbm",),
    },
    {
        "key": "CatBoost",
        "aliases": ("catboost",),
        "hint": "catboost.CatBoostClassifier. Install catboost with subprocess before importing it.",
        "classes": ("CatBoostClassifier",),
        "modules": ("catboost",),
    },
    {
        "key": "KNN",
        "aliases": ("k-nearest neighbors", "k nearest neighbors", "k-nearest", "k nearest", "knn"),
        "hint": "sklearn.neighbors.KNeighborsClassifier.",
        "classes": ("KNeighborsClassifier",),
        "modules": (),
    },
    {
        "key": "GaussianNB",
        "aliases": ("naive bayes", "gaussiannb", "gaussian nb"),
        "hint": "sklearn.naive_bayes.GaussianNB.",
        "classes": ("GaussianNB",),
        "modules": (),
    },
    {
        "key": "MLP",
        "aliases": ("multilayer perceptron", "multi-layer perceptron", "mlp"),
        "hint": "sklearn.neural_network.MLPClassifier.",
        "classes": ("MLPClassifier",),
        "modules": (),
    },
    {
        "key": "AdaBoost",
        "aliases": ("adaboost", "ada boost"),
        "hint": "sklearn.ensemble.AdaBoostClassifier.",
        "classes": ("AdaBoostClassifier",),
        "modules": (),
    },
    {
        "key": "ExtraTrees",
        "aliases": ("extra trees", "extratrees"),
        "hint": "sklearn.ensemble.ExtraTreesClassifier.",
        "classes": ("ExtraTreesClassifier",),
        "modules": (),
    },
    {
        "key": "QDA",
        "aliases": ("quadratic discriminant", "qda"),
        "hint": "sklearn.discriminant_analysis.QuadraticDiscriminantAnalysis.",
        "classes": ("QuadraticDiscriminantAnalysis",),
        "modules": (),
    },
    {
        "key": "LDA",
        "aliases": ("linear discriminant", "lda"),
        "hint": "sklearn.discriminant_analysis.LinearDiscriminantAnalysis.",
        "classes": ("LinearDiscriminantAnalysis",),
        "modules": (),
    },
)

_BY_CLASS = {
    class_name: spec
    for spec in _MODEL_SPECS
    for class_name in spec["classes"]
}
_EXPLICIT_CLASS = re.compile(r"(?<!\w)([A-Za-z_][A-Za-z0-9_]*Classifier)(?!\w)")


def requested_models(query: str) -> list[dict]:
    found: list[tuple[int, int, dict]] = []
    for spec in _MODEL_SPECS:
        for alias in spec["aliases"]:
            pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
            for match in pattern.finditer(query):
                found.append((match.start(), match.end(), spec))
    for match in _EXPLICIT_CLASS.finditer(query):
        name = match.group(1)
        spec = _BY_CLASS.get(name)
        if spec is None:
            spec = {
                "key": name,
                "hint": f"Use {name} exactly as written. Do not substitute another estimator.",
                "classes": (name,),
                "modules": (),
            }
        found.append((match.start(), match.end(), spec))
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    chosen: list[dict] = []
    seen: set[str] = set()
    taken_until = -1
    for start, end, spec in found:
        if start < taken_until:
            continue
        taken_until = end
        key = str(spec["key"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append(spec)
    return chosen


def models_dict_error(code: str, models: list[dict]) -> str:
    allowed = [str(item["key"]) for item in models]
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""
    if _models_keys(tree) != allowed:
        return (
            "models must be one dict literal with exactly these keys in this order: "
            + ", ".join(allowed)
            + "."
        )
    missing = _missing_constructors(code, models)
    if missing:
        return "Each models entry must construct its own estimator: " + ", ".join(missing) + "."
    foreign = _foreign_models(code, models)
    if foreign:
        return "Remove estimators that the query did not name: " + ", ".join(foreign) + "."
    return ""


def split_contract_error(code: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and call_name(node.func) == "train_test_split"
    ]
    if not calls:
        return "The script must split with train_test_split so that its random_state can be changed."
    for call in calls:
        stratified = any(
            keyword.arg == "stratify"
            and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
            for keyword in call.keywords
        )
        if not stratified:
            return "Every train_test_split call must pass stratify=y, the label array."
    return ""


def generate_classification_code(
    prompt: str,
    csv_schema: str,
    models: list[dict],
    spec: dict | None = None,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    if not models:
        raise QueryNamesNoModel()
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _task(prompt, csv_schema, models, spec)},
        ],
    )
    content = response.choices[0].message.content or ""
    return _plain_python(content)


def correct_classification_code(
    code: str,
    error: str,
    prompt: str,
    csv_schema: str,
    models: list[dict],
    spec: dict | None = None,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    if not models:
        raise QueryNamesNoModel()
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Şu kodu yazdın ama şu hatayı aldım, lütfen hatayı analiz edip "
                    "düzeltilmiş Python kodunu ver.\n\n"
                    f"Code:\n{code}\n\n"
                    f"Error:\n{error}\n\n"
                    f"{_task(prompt, csv_schema, models, spec)}"
                ),
            },
        ],
    )
    content = response.choices[0].message.content or ""
    return _plain_python(content)


def _task(prompt: str, csv_schema: str, models: list[dict], spec: dict | None = None) -> str:
    lines = "\n".join(f"- {item['key']}: {item['hint']}" for item in models)
    names = ", ".join(str(item["key"]) for item in models)
    task = (
        f"Prompt:\n{prompt}\n\n"
        f"CSV structure:\n{csv_schema}\n\n"
        f"Allowed models:\n{lines}\n\n"
        f"Assign models = {{...}} with exactly these keys, in this order: {names}. "
        "Do not add any other key."
    )
    if spec:
        task += "\n\n" + spec_brief(spec)
    return task


def _models_keys(tree: ast.AST) -> list[str] | None:
    found: list[list[str]] = []
    for node in ast.walk(tree):
        value = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        else:
            continue
        if value is None:
            continue
        if not any(isinstance(target, ast.Name) and target.id == "models" for target in targets):
            continue
        if not isinstance(value, ast.Dict):
            return None
        keys: list[str] = []
        for key in value.keys:
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                return None
            keys.append(key.value)
        found.append(keys)
    if len(found) != 1:
        return None
    return found[0]


def _missing_constructors(code: str, models: list[dict]) -> list[str]:
    missing: list[str] = []
    for item in models:
        classes = tuple(item["classes"])
        if not classes:
            continue
        present = any(
            re.search(rf"(?<!\w){re.escape(str(class_name))}(?!\w)", code)
            for class_name in classes
        )
        if not present:
            missing.append(str(item["key"]))
    return missing


def _foreign_models(code: str, models: list[dict]) -> list[str]:
    allowed_keys = {str(item["key"]) for item in models}
    allowed_classes = {str(class_name) for item in models for class_name in item["classes"]}
    allowed_modules = {str(module) for item in models for module in item["modules"]}
    foreign: list[str] = []
    for spec in _MODEL_SPECS:
        if str(spec["key"]) in allowed_keys:
            continue
        tokens = (spec["key"], *spec["classes"], *spec["modules"])
        for token in tokens:
            text = str(token)
            if text in allowed_classes or text in allowed_modules:
                continue
            if re.search(rf"(?<!\w){re.escape(text)}(?!\w)", code):
                foreign.append(text)
                break
    for match in _EXPLICIT_CLASS.finditer(code):
        name = match.group(1)
        if name not in allowed_classes and name not in foreign:
            foreign.append(name)
    return foreign


def _plain_python(content: str) -> str:
    text = content.strip()
    fenced = re.fullmatch(r"```(?:python)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
    text = "\n".join(lines).strip()
    if not text:
        raise RuntimeError("model returned empty code")
    return text
