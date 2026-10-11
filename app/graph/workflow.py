import logging
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
    route_after_verifier,
    verifier_node,
)
from app.graph.state import AgentState

logger = logging.getLogger("axiomforge")


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("literature_node", literature_node)
    graph.add_node("planner_node", planner_node)
    graph.add_node("experiment_node", experiment_node)
    graph.add_node("verifier_node", verifier_node)
    graph.add_edge(START, "literature_node")
    graph.add_node("approval_gate", approval_gate)
    graph.add_edge("literature_node", "planner_node")
    graph.add_edge("planner_node", "approval_gate")
    graph.add_edge("approval_gate", "experiment_node")
    graph.add_edge("experiment_node", "verifier_node")
    graph.add_conditional_edges(
        "verifier_node",
        route_after_verifier,
        {"experiment_node": "experiment_node", END: END},
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


def start_research(query: str) -> dict:
    initial: AgentState = {
        "query": query,
        "literature_context": [],
        "hypotheses": [],
        "approval_status": "",
        "current_experiment_code": "",
        "experiment_metrics": {},
        "verification_status": "",
        "verifier_feedback": "",
        "critic_rounds": 0,
        "critic_continue": False,
    }
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    with _open_graph() as checkpointer:
        checkpointer.setup()
        compiled = _compile(checkpointer)
        state = compiled.invoke(initial, config)
    hypotheses = list(state.get("hypotheses", []))
    logger.info("plan paused thread_id=%s decision=Y/N", thread_id)
    for index, item in enumerate(hypotheses, start=1):
        logger.info("paused hypothesis %s=%s", index, item)
    return {
        "thread_id": thread_id,
        "status": "paused",
        "hypotheses": hypotheses,
        "state": state,
    }


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
