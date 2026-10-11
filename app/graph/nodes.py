import logging

from app.agents.literature import run_literature_agent
from app.agents.planner import run_planner_agent
from app.experiments import execute_experiment
from app.graph.state import AgentState
from app.memory.rag_memory import search_past_experiments

logger = logging.getLogger("axiomforge")


def literature_node(state: AgentState) -> dict:
    logger.info("literature_node query=%s", state["query"])
    literature_context = run_literature_agent(state["query"])
    for index, item in enumerate(literature_context, start=1):
        logger.info("literature_context %s=%s", index, item)
    return {"literature_context": literature_context}


def planner_node(state: AgentState) -> dict:
    logger.info("planner_node query=%s", state["query"])
    past_experiments = search_past_experiments(state["query"], k=3)
    failed_experiments = [item for item in past_experiments if item.get("is_success") is False]
    logger.info(
        "planner retrieved past_experiments=%s failed=%s",
        len(past_experiments),
        len(failed_experiments),
    )
    for item in failed_experiments:
        logger.info(
            "past failure hypothesis=%s error=%s",
            item.get("hypothesis", ""),
            str(item.get("error_log", ""))[:500],
        )
    hypotheses, memory_note = run_planner_agent(
        state["query"],
        state["literature_context"],
        failed_experiments,
    )
    if memory_note:
        logger.info("planner memory_note=%s", memory_note)
    for index, item in enumerate(hypotheses, start=1):
        logger.info("hypothesis %s=%s", index, item)
    return {"hypotheses": hypotheses}


def experiment_node(state: AgentState) -> dict:
    logger.info("Onaylandı, deneylere başlanıyor")
    hypothesis = state["hypotheses"][0] if state["hypotheses"] else state["query"]
    result = execute_experiment(
        hypothesis,
        "age:float, monthly_spend:float, tenure_months:int, churn:int",
    )
    logger.info("experiment result status=%s", result.get("status"))
    return {}
