import logging

from app.agents.literature import run_literature_agent
from app.agents.planner import run_planner_agent
from app.experiments import execute_experiment
from app.graph.state import AgentState
from app.graph.verifier import performance_dropped, rewrite_seeds
from app.memory.rag_memory import search_past_experiments
from app.sandbox.e2b_runner import SandboxCodeError, run_classification
from app.tracking.mlflow_logger import parse_metrics

logger = logging.getLogger("axiomforge")

EXPERIMENT_CSV_SCHEMA = "age:float, monthly_spend:float, tenure_months:int, churn:int"


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
    result = execute_experiment(hypothesis, EXPERIMENT_CSV_SCHEMA)
    logger.info("experiment result status=%s", result.get("status"))
    metrics = {
        name: float(result[name])
        for name in ("accuracy", "f1")
        if name in result
    }
    return {
        "current_experiment_code": result.get("code", ""),
        "experiment_metrics": metrics,
    }


def verifier_node(state: AgentState) -> dict:
    code = state.get("current_experiment_code", "")
    original = state.get("experiment_metrics") or {}
    logger.info("verifier_node original_metrics=%s", original)
    if not code or not original:
        logger.info("verification_status=Failed reason=no successful experiment")
        return {"verification_status": "Failed"}
    rewritten = rewrite_seeds(code)
    logger.info("verifier rewritten seeds in experiment code")
    try:
        output = run_classification(rewritten, EXPERIMENT_CSV_SCHEMA)
        renewed = parse_metrics(output)
    except (SandboxCodeError, RuntimeError) as exc:
        logger.error("verifier sandbox failed: %s", exc)
        return {"verification_status": "Failed"}
    if performance_dropped(original, renewed):
        logger.info("Overfitting/Unstable original=%s renewed=%s", original, renewed)
        return {"verification_status": "Failed"}
    logger.info("verification_status=Passed original=%s renewed=%s", original, renewed)
    return {"verification_status": "Passed"}
