import logging

from app.agents.literature import run_literature_agent
from app.graph.state import AgentState

logger = logging.getLogger("axiomforge")


def literature_node(state: AgentState) -> dict:
    logger.info("literature_node query=%s", state["query"])
    literature_context = run_literature_agent(state["query"])
    for index, item in enumerate(literature_context, start=1):
        logger.info("literature_context %s=%s", index, item)
    return {"literature_context": literature_context}


def planner_node(state: AgentState) -> dict:
    logger.info("planner_node query=%s", state["query"])
    return {}


def experiment_node(state: AgentState) -> dict:
    logger.info("experiment_node query=%s", state["query"])
    return {}
