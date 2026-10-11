import json

from openai import OpenAI

from app.config import OPENAI_API_KEY

MODEL = "gpt-4o"

SYSTEM_PROMPT = (
    "You are a research planner. Read the user query and the literature context. "
    "Write exactly 3 specific, testable hypotheses. "
    'Return only JSON: {"hypotheses": ["...", "...", "..."]}.'
)


def run_planner_agent(query: str, literature_context: list[str]) -> list[str]:
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
                "content": f"Query:\n{query}\n\nLiterature:\n{literature}",
            },
        ],
    )
    content = response.choices[0].message.content or ""
    return _three_hypotheses(content)


def _three_hypotheses(content: str) -> list[str]:
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
    return cleaned[:3]
