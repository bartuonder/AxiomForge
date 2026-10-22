import json

from openai import OpenAI

from app.agents.spec import DATASETS, SpecError, allowed_params_text, validate_spec
from app.config import OPENAI_API_KEY

MODEL = "gpt-4o"
MAX_PLAN_ATTEMPTS = 2

SYSTEM_PROMPT = (
    "You are a research planner. Read the user query, the literature context, "
    "and the failed past experiments. "
    "Write exactly 3 specific, testable hypotheses that do not repeat failed approaches. "
    "The experiment agent can only do this: train exactly the Allowed models together on one dataset "
    "and compare them, optionally with constructor parameters from the allowed parameter list. "
    "Every hypothesis must be an experiment of that kind. "
    "Its statement must not name a model, a method, a feature transformation or a dataset outside its own fields. "
    "Each hypothesis is a JSON object with these fields: "
    "statement (one testable sentence), "
    f"dataset (one of: {', '.join(DATASETS)}), "
    "params (an object keyed by model name, each value an object of allowed parameter names to numbers or strings; "
    "use an empty object when the hypothesis changes no parameter). "
    "If failed past experiments exist, memory_note must start with "
    "'Bu daha önce denenmiş ve şu hatayı almış, farklı bir yaklaşım öneriyorum' "
    "and mention the past error. "
    'Return only JSON: {"memory_note": "...", "hypotheses": [{"statement": "...", "dataset": "...", "params": {}}]}.'
)


def run_planner_agent(
    query: str,
    literature_context: list[str],
    past_experiments: list[dict],
    models: list[dict],
) -> tuple[list[dict], str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    model_keys = [str(item["key"]) for item in models]
    literature = "\n\n".join(literature_context) if literature_context else "No literature was found."
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = (
        "İşte literatür verisi. Ayrıca işte geçmişte denediğimiz ve başarısız olan "
        f"deneylerin kayıtları: {_format_past_experiments(past_experiments)}. "
        "Yeni hipotezler üretirken geçmişte başarısız olanları TEKRAR ETME.\n\n"
        f"Allowed models: {', '.join(model_keys)}\n"
        f"Allowed parameters per model:\n{allowed_params_text(model_keys)}\n\n"
        f"Query:\n{query}\n\nLiterature:\n{literature}"
    )
    error = ""
    for _ in range(MAX_PLAN_ATTEMPTS):
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt + (f"\n\nYour previous plan was rejected: {error}" if error else "")},
            ],
        )
        content = response.choices[0].message.content or ""
        try:
            return _plan(content, model_keys)
        except SpecError as exc:
            error = str(exc)
    raise RuntimeError(f"planner returned an invalid experiment spec: {error}")


def _format_past_experiments(past_experiments: list[dict]) -> str:
    if not past_experiments:
        return "Geçmişte başarısız deney kaydı yok."
    blocks = []
    for item in past_experiments:
        blocks.append(
            "Hypothesis: "
            f"{item.get('hypothesis', '')}\n"
            f"Metric: {item.get('metric', '')}\n"
            f"Error log: {str(item.get('error_log', ''))[:800]}\n"
            f"Code: {str(item.get('code', ''))[:400]}"
        )
    return "\n\n".join(blocks)


def _plan(content: str, model_keys: list[str]) -> tuple[list[dict], str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("planner returned invalid JSON") from exc
    items = payload.get("hypotheses") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("planner did not return hypotheses")
    if len(items) < 3:
        raise SpecError("exactly 3 hypotheses are required")
    specs = [validate_spec(item, model_keys) for item in items[:3]]
    note = payload.get("memory_note", "") if isinstance(payload, dict) else ""
    if not isinstance(note, str):
        note = ""
    return specs, note.strip()
