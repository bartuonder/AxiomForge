import json

from openai import OpenAI

from app.config import OPENAI_API_KEY
from app.tools.arxiv import search_arxiv

MODEL = "gpt-4o"

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_arxiv",
        "description": "Search arXiv and return the title and abstract of the most relevant papers.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = (
    "You are a literature agent. Call search_arxiv once with the user query unchanged. "
    "Then combine each paper title with its abstract. "
    'Return only JSON: {"literature_context": ["...", "...", "..."]}. '
    "Use one string per paper. Do not add any other text."
)


def run_literature_agent(query: str) -> list[str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    first = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        tools=[SEARCH_TOOL],
        tool_choice={"type": "function", "function": {"name": "search_arxiv"}},
        messages=messages,
    )
    message = first.choices[0].message
    tool_calls = message.tool_calls or []
    if not tool_calls:
        raise RuntimeError("literature agent did not call search_arxiv")
    messages.append(message.model_dump(exclude_none=True))
    papers: list[dict[str, str]] = []
    for call in tool_calls:
        arguments = json.loads(call.function.arguments or "{}")
        papers = search_arxiv(str(arguments.get("query") or query))
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(papers),
            }
        )
    second = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=messages,
        response_format={"type": "json_object"},
    )
    content = second.choices[0].message.content or ""
    return _context_from_response(content, papers)


def _context_from_response(content: str, papers: list[dict[str, str]]) -> list[str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {}
    items = payload.get("literature_context") if isinstance(payload, dict) else None
    if isinstance(items, list):
        cleaned = [item.strip() for item in items if isinstance(item, str) and item.strip()]
        if cleaned:
            return cleaned
    return [f"{paper['title']}: {paper['abstract']}" for paper in papers]
