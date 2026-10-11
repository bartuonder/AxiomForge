import json

from openai import OpenAI

from app.config import OPENAI_API_KEY

MODEL = "gpt-4o"

SYSTEM_PROMPT = (
    "You are a research planner. Read the user query, the literature context, "
    "and the failed past experiments. "
    "Write exactly 3 specific, testable hypotheses that do not repeat failed approaches. "
    "If failed past experiments exist, memory_note must start with "
    "'Bu daha önce denenmiş ve şu hatayı almış, farklı bir yaklaşım öneriyorum' "
    "and mention the past error. "
    'Return only JSON: {"memory_note": "...", "hypotheses": ["...", "...", "..."]}.'
)


def run_planner_agent(
    query: str,
    literature_context: list[str],
    past_experiments: list[dict],
) -> tuple[list[str], str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    literature = "\n\n".join(literature_context) if literature_context else "No literature was found."
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "İşte literatür verisi. Ayrıca işte geçmişte denediğimiz ve başarısız olan "
                    f"deneylerin kayıtları: {_format_past_experiments(past_experiments)}. "
                    "Yeni hipotezler üretirken geçmişte başarısız olanları TEKRAR ETME.\n\n"
                    f"Query:\n{query}\n\nLiterature:\n{literature}"
                ),
            },
        ],
    )
    content = response.choices[0].message.content or ""
    return _plan(content)


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


def _plan(content: str) -> tuple[list[str], str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("planner returned invalid JSON") from exc
    items = payload.get("hypotheses") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("planner did not return hypotheses")
    cleaned = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    if len(cleaned) < 3:
        raise RuntimeError("planner returned fewer than 3 hypotheses")
    note = payload.get("memory_note", "") if isinstance(payload, dict) else ""
    if not isinstance(note, str):
        note = ""
    return cleaned[:3], note.strip()
