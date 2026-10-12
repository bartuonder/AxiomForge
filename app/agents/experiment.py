import re

from openai import OpenAI

from app.config import OPENAI_API_KEY

MODEL = "gpt-4o"
PROMPT_VERSION = "experiment-v4"

SYSTEM_PROMPT = (
    "You write one complete Python script for the comparison asked in the user question. "
    "Do not train only one model when the question compares several models. "
    "Example: if the question compares XGBoost and Random Forest, train both on the same rows and the same train/test split in each loop pass. "
    "Do not use a tiny synthetic CSV as the only data. "
    "Load a realistic classification dataset from sklearn.datasets, such as load_breast_cancer, "
    "or build a clearly imbalanced set with sklearn.datasets.make_classification. "
    "Veri Üretimi Sabiti: Veriyi herhangi bir döngünün dışında tek bir kere yükle veya üret. "
    "make_classification kullanıyorsan class_sep 0.5 veya daha düşük olsun ve weights ile net bir imbalanced dağılım kur. "
    "Veri üretiminin random_state değeri sabit bir tam sayı olsun ve split döngüsünde değişmesin. "
    "Seed Döngüsü Protokolü: Beşli test döngüsü yalnız train_test_split random_state değerini değiştirir. "
    "Döngü tam olarak bu tohumlar olsun: 42, 100, 200, 300, 400. "
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
    "If XGBoost is required, install xgboost with subprocess before importing it. "
    "Inside the split loop, print one line per model for that split and no other output. "
    "Each model name appears exactly five times. Use a single token model name: "
    "model=<name> accuracy=<float> f1=<float> roc_auc=<float> pr_auc=<float> "
    "train_seconds=<float> tn=<int> fp=<int> fn=<int> tp=<int> "
    "Do not wrap the source in markdown. Do not explain it. Do not use comments."
)


def generate_classification_code(prompt: str, csv_schema: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Prompt:\n{prompt}\n\nCSV structure:\n{csv_schema}",
            },
        ],
    )
    content = response.choices[0].message.content or ""
    return _plain_python(content)


def correct_classification_code(
    code: str,
    error: str,
    prompt: str,
    csv_schema: str,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
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
                    f"Original prompt:\n{prompt}\n\n"
                    f"CSV structure:\n{csv_schema}"
                ),
            },
        ],
    )
    content = response.choices[0].message.content or ""
    return _plain_python(content)


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
