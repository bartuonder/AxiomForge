from typing import Any

from app.graph.state import AgentState


def selected_index(state: AgentState) -> int:
    count = len(state.get("experiment_specs") or []) or len(state.get("hypotheses") or [])
    index = state.get("selected_hypothesis", 0) or 0
    return index if isinstance(index, int) and 0 <= index < count else 0


def primary_hypothesis(state: AgentState) -> tuple[str, dict | None]:
    index = selected_index(state)
    specs = state.get("experiment_specs") or []
    if specs:
        return str(specs[index]["statement"]), specs[index]
    hypotheses = state.get("hypotheses") or []
    return (str(hypotheses[index]) if hypotheses else state.get("query", "")), None


def validate_selection(count: int, selected: Any) -> int:
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError("selected must be the number of one hypothesis")
    if not 0 <= selected < count:
        raise ValueError(f"selected must be between 0 and {count - 1}")
    return selected
