from typing import TypedDict


class AgentState(TypedDict):
    query: str
    literature_context: list[str]
    hypotheses: list[str]
    approval_status: str
