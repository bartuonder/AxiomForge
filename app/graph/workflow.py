import logging
import uuid
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.experiment import QueryNamesNoModel, requested_models
from app.config import DATABASE_URL
from app.graph.errors import describe_error, read_error, record_error
from app.graph.nodes import (
    approval_gate,
    consistency_checker_node,
    experiment_node,
    literature_node,
    planner_node,
    report_node,
    route_after_consistency,
    route_after_verifier,
    verifier_node,
)
from app.graph.selection import selected_index, validate_selection
from app.graph.state import AgentState

logger = logging.getLogger("axiomforge")

FINISHED_STATUSES = {"completed", "needs_review"}
_STEP_ORDER = [
    "literature_node",
    "planner_node",
    "experiment_node",
    "verifier_node",
    "report_node",
    "consistency_checker_node",
]


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("literature_node", literature_node)
    graph.add_node("planner_node", planner_node)
    graph.add_node("experiment_node", experiment_node)
    graph.add_node("verifier_node", verifier_node)
    graph.add_node("report_node", report_node)
    graph.add_node("consistency_checker_node", consistency_checker_node)
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
    graph.add_edge("report_node", "consistency_checker_node")
    graph.add_conditional_edges(
        "consistency_checker_node",
        route_after_consistency,
        {"report_node": "report_node", "end": END},
    )
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


def empty_research_state(query: str) -> AgentState:
    return {
        "query": query,
        "literature_context": [],
        "hypotheses": [],
        "experiment_specs": [],
        "selected_hypothesis": 0,
        "approval_status": "",
        "current_experiment_code": "",
        "experiment_error": "",
        "experiment_metrics": {},
        "model_results": [],
        "tested_models": [],
        "dataset_profile": {},
        "statistical_results": {},
        "statistical_decision": {},
        "mlflow_run_id": "",
        "verification_status": "",
        "verifier_feedback": "",
        "critic_rounds": 0,
        "critic_continue": False,
        "paper_markdown": "",
        "consistency_feedback": "",
        "consistency_rounds": 0,
        "consistency_continue": False,
        "research_status": "",
    }


def run_until_pause(thread_id: str, query: str) -> None:
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    fresh = empty_research_state(query)
    logger.info("start_research thread_id=%s", thread_id)
    logger.info(
        "start_research reset literature=%s hypotheses=%s code=%s stats=%s models=%s tested=%s",
        fresh["literature_context"],
        fresh["hypotheses"],
        fresh["current_experiment_code"],
        fresh["statistical_results"],
        fresh["model_results"],
        fresh["tested_models"],
    )
    try:
        with _open_graph() as checkpointer:
            checkpointer.setup()
            compiled = _compile(checkpointer)
            existing = compiled.get_state(config)
            if existing.values:
                raise RuntimeError("research thread was not empty")
            state = compiled.invoke(fresh, config)
        hypotheses = list(state.get("hypotheses", []))
        logger.info("plan paused thread_id=%s decision=Y/N", thread_id)
        for index, item in enumerate(hypotheses, start=1):
            logger.info("paused hypothesis %s=%s", index, item)
    except Exception as exc:
        logger.exception("research failed thread_id=%s", thread_id)
        record_error(thread_id, describe_error(exc))


def new_thread_id(query: str) -> str:
    if not requested_models(query):
        raise QueryNamesNoModel()
    return str(uuid.uuid4())


def get_research(thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    error = read_error(thread_id)
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
        "experiment_specs": list(values.get("experiment_specs") or []),
        "selected_hypothesis": selected_index(values),
        "approval_status": values.get("approval_status") or "",
        "verification_status": values.get("verification_status") or "",
        "verifier_feedback": values.get("verifier_feedback") or "",
        "instability": _instability(values),
        "research_status": values.get("research_status") or "",
        "consistency_feedback": values.get("consistency_feedback") or "",
        "error": error,
        "steps": _steps(values, next_nodes, status),
    }


def _instability(values: dict) -> dict:
    finding = (values.get("statistical_decision") or {}).get("instability") or {}
    return {
        "unstable": bool(finding.get("unstable")),
        "std_threshold": float(finding.get("std_threshold", 0.0)),
        "flagged": list(finding.get("flagged") or []),
    }


def _research_status(values: dict, next_nodes: list[str], error: str) -> str:
    if values.get("research_status") == "Completed":
        return "completed"
    if values.get("research_status") == "NeedsReview":
        return "needs_review"
    if error:
        return "failed"
    if values.get("approval_status") == "rejected":
        return "rejected"
    if (
        "approval_gate" in next_nodes
        and values.get("hypotheses")
        and values.get("approval_status") != "approved"
    ):
        return "paused"
    if not values and not next_nodes:
        return "starting"
    return "running"


def _active_step(values: dict, next_nodes: list[str], status: str) -> str:
    if status in FINISHED_STATUSES:
        return "consistency_checker_node"
    if status in {"paused", "rejected"}:
        return "planner_node"
    for name in (
        "consistency_checker_node",
        "report_node",
        "verifier_node",
        "experiment_node",
        "planner_node",
        "literature_node",
    ):
        if name in next_nodes:
            return name
    if values.get("paper_markdown") and values.get("consistency_continue"):
        return "report_node"
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
        "report_node": bool(values.get("paper_markdown")) and not values.get("consistency_continue"),
        "consistency_checker_node": values.get("research_status") in {"Completed", "NeedsReview"},
    }
    active = _active_step(values, next_nodes, status)
    steps = []
    for name in _STEP_ORDER:
        if status in FINISHED_STATUSES or done[name]:
            phase = "done"
        elif status not in {"rejected", "failed"} and name == active:
            phase = "active"
        else:
            phase = "pending"
        steps.append({"id": name, "phase": phase})
    return steps


def decide_plan(thread_id: str, decision: str, selected: int | None = None) -> dict:
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
        if snapshot.values.get("approval_status"):
            raise RuntimeError("research thread was already decided")
        hypotheses = list(snapshot.values.get("hypotheses", []))
        logger.info("decide_plan thread_id=%s decision=%s", thread_id, normalized)
        for index, item in enumerate(hypotheses, start=1):
            logger.info("approve hypothesis %s=%s", index, item)
        if normalized == "N":
            logger.info("plan rejected thread_id=%s", thread_id)
            compiled.update_state(config, {"approval_status": "rejected"})
            return {
                "thread_id": thread_id,
                "status": "ended",
                "approval_status": "rejected",
                "hypotheses": hypotheses,
            }
        choice = validate_selection(len(hypotheses), selected)
        compiled.update_state(config, {"approval_status": "approved", "selected_hypothesis": choice})
    return {
        "thread_id": thread_id,
        "status": "running",
        "approval_status": "approved",
        "selected_hypothesis": choice,
        "hypotheses": hypotheses,
    }


def revoke_approval(thread_id: str) -> None:
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    with _open_graph() as checkpointer:
        compiled = _compile(checkpointer)
        compiled.update_state(config, {"approval_status": ""})


def resume_research(thread_id: str) -> None:
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    logger.info("resume_research thread_id=%s", thread_id)
    try:
        with _open_graph() as checkpointer:
            compiled = _compile(checkpointer)
            compiled.invoke(None, config)
    except Exception as exc:
        logger.exception("research failed thread_id=%s", thread_id)
        record_error(thread_id, describe_error(exc))
