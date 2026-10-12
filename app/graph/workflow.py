import logging
import threading
import uuid
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.config import DATABASE_URL
from app.graph.nodes import (
    approval_gate,
    experiment_node,
    literature_node,
    planner_node,
    report_node,
    route_after_verifier,
    verifier_node,
)
from app.graph.state import AgentState

logger = logging.getLogger("axiomforge")

_research_errors: dict[str, str] = {}
_STEP_ORDER = [
    "literature_node",
    "planner_node",
    "experiment_node",
    "verifier_node",
    "report_node",
]


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("literature_node", literature_node)
    graph.add_node("planner_node", planner_node)
    graph.add_node("experiment_node", experiment_node)
    graph.add_node("verifier_node", verifier_node)
    graph.add_node("report_node", report_node)
    graph.add_edge(START, "literature_node")
    graph.add_node("approval_gate", approval_gate)
    graph.add_edge("literature_node", "planner_node")
    graph.add_edge("planner_node", "approval_gate")
    graph.add_edge("approval_gate", "experiment_node")
    graph.add_edge("experiment_node", "verifier_node")
    graph.add_conditional_edges(
        "verifier_node",
        route_after_verifier,
        {"experiment_node": "experiment_node", "report_node": "report_node"},
    )
    graph.add_edge("report_node", END)
    return graph


def _compile(checkpointer: PostgresSaver) -> CompiledStateGraph:
    return build_graph().compile(
        checkpointer=checkpointer,
        interrupt_before=["approval_gate"],
    )


def _open_graph():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing")
    return PostgresSaver.from_conn_string(DATABASE_URL)


def _initial_state(query: str) -> AgentState:
    return {
        "query": query,
        "literature_context": [],
        "hypotheses": [],
        "approval_status": "",
        "current_experiment_code": "",
        "experiment_metrics": {},
        "model_results": [],
        "dataset_profile": {},
        "statistical_results": {},
        "verification_status": "",
        "verifier_feedback": "",
        "critic_rounds": 0,
        "critic_continue": False,
        "research_status": "",
    }


def _run_until_pause(thread_id: str, query: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        with _open_graph() as checkpointer:
            checkpointer.setup()
            compiled = _compile(checkpointer)
            state = compiled.invoke(_initial_state(query), config)
        hypotheses = list(state.get("hypotheses", []))
        logger.info("plan paused thread_id=%s decision=Y/N", thread_id)
        for index, item in enumerate(hypotheses, start=1):
            logger.info("paused hypothesis %s=%s", index, item)
    except Exception as exc:
        logger.exception("research failed thread_id=%s", thread_id)
        _research_errors[thread_id] = str(exc)


def start_research(query: str) -> dict:
    thread_id = str(uuid.uuid4())
    worker = threading.Thread(
        target=_run_until_pause,
        args=(thread_id, query),
        daemon=True,
    )
    worker.start()
    return {"thread_id": thread_id, "status": "running"}


def get_research(thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    error = _research_errors.get(thread_id, "")
    with _open_graph() as checkpointer:
        compiled = _compile(checkpointer)
        snapshot = compiled.get_state(config)
    values = dict(snapshot.values or {})
    next_nodes = [str(node) for node in (snapshot.next or ())]
    status = _research_status(values, next_nodes, error)
    return {
        "thread_id": thread_id,
        "status": status,
        "next": next_nodes,
        "active_step": _active_step(values, next_nodes, status),
        "hypotheses": list(values.get("hypotheses") or []),
        "approval_status": values.get("approval_status") or "",
        "verification_status": values.get("verification_status") or "",
        "research_status": values.get("research_status") or "",
        "error": error,
        "steps": _steps(values, next_nodes, status),
    }


def _research_status(values: dict, next_nodes: list[str], error: str) -> str:
    if error and not values:
        return "failed"
    if values.get("research_status") == "Completed":
        return "completed"
    if values.get("approval_status") == "rejected":
        return "rejected"
    if "approval_gate" in next_nodes and values.get("hypotheses"):
        return "paused"
    if not values and not next_nodes:
        return "starting"
    return "running"


def _active_step(values: dict, next_nodes: list[str], status: str) -> str:
    if status == "completed":
        return "report_node"
    if status in {"paused", "rejected"}:
        return "planner_node"
    for name in ("report_node", "verifier_node", "experiment_node", "planner_node", "literature_node"):
        if name in next_nodes:
            return name
    if values.get("verification_status"):
        return "report_node"
    if values.get("current_experiment_code"):
        return "verifier_node"
    if values.get("approval_status") == "approved":
        return "experiment_node"
    if values.get("hypotheses"):
        return "planner_node"
    return "literature_node"


def _steps(values: dict, next_nodes: list[str], status: str) -> list[dict[str, str]]:
    done = {
        "literature_node": bool(values.get("literature_context")),
        "planner_node": bool(values.get("hypotheses")),
        "experiment_node": bool(values.get("current_experiment_code")),
        "verifier_node": values.get("verification_status") in {"Passed", "Failed"}
        and not values.get("critic_continue"),
        "report_node": values.get("research_status") == "Completed",
    }
    active = _active_step(values, next_nodes, status)
    steps = []
    for name in _STEP_ORDER:
        if status == "completed" or done[name]:
            phase = "done"
        elif status not in {"rejected", "failed"} and name == active:
            phase = "active"
        else:
            phase = "pending"
        steps.append({"id": name, "phase": phase})
    return steps


def approve_plan(thread_id: str, decision: str) -> dict:
    normalized = decision.strip().upper()
    if normalized not in {"Y", "N"}:
        raise RuntimeError("decision must be Y or N")
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    with _open_graph() as checkpointer:
        checkpointer.setup()
        compiled = _compile(checkpointer)
        snapshot = compiled.get_state(config)
        if not snapshot.values:
            raise RuntimeError("research thread was not found")
        if snapshot.next != ("approval_gate",):
            raise RuntimeError("research thread is not waiting for approval")
        hypotheses = list(snapshot.values.get("hypotheses", []))
        logger.info("approve_plan thread_id=%s decision=%s", thread_id, normalized)
        for index, item in enumerate(hypotheses, start=1):
            logger.info("approve hypothesis %s=%s", index, item)
        if normalized == "N":
            logger.info("plan rejected thread_id=%s", thread_id)
            compiled.update_state(config, {"approval_status": "rejected"})
            state = compiled.get_state(config).values
            return {
                "thread_id": thread_id,
                "status": "ended",
                "approval_status": "rejected",
                "hypotheses": hypotheses,
                "state": state,
            }
        compiled.update_state(config, {"approval_status": "approved"})
        state = compiled.invoke(None, config)
    return {
        "thread_id": thread_id,
        "status": "finished",
        "approval_status": "approved",
        "hypotheses": hypotheses,
        "state": state,
    }
