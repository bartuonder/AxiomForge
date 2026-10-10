import re

from openai import OpenAI

from app.config import OPENAI_API_KEY

MODEL = "gpt-4o"
PROMPT_VERSION = "experiment-v1"

SYSTEM_PROMPT = (
    "You write Python source for a scikit-learn classification experiment. "
    "The user supplies a task prompt and a CSV column structure. "
    "Return only one complete Python script. "
    "The script must read /home/user/data.csv. "
    "The file columns match the given structure. "
    "Train a scikit-learn classifier. "
    "The target is the column named in the prompt, otherwise the last column. "
    "Print exactly two lines and nothing else: "
    "accuracy=<float> "
    "f1=<float> "
    "Use sklearn.metrics.accuracy_score and sklearn.metrics.f1_score. "
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
