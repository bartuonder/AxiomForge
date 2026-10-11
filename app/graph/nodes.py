import logging

from app.graph.state import AgentState

logger = logging.getLogger("axiomforge")


def literature_node(state: AgentState) -> dict:
    logger.info("literature_node query=%s", state["query"])
    return {}


def planner_node(state: AgentState) -> dict:
    logger.info("planner_node query=%s", state["query"])
    return {}


def experiment_node(state: AgentState) -> dict:
    logger.info("experiment_node query=%s", state["query"])
    return {}
