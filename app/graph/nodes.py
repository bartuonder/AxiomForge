import logging

from langchain_core.runnables import RunnableConfig

from app.agents.literature import run_literature_agent
from app.agents.report import write_workshop_paper
from app.agents.planner import run_planner_agent
from app.experiments import execute_experiment
from app.graph.state import AgentState
from app.graph.verifier import MAX_CRITIC_ROUNDS, judge_data_leakage, models_dropped, rewrite_seeds
from app.memory.rag_memory import save_experiment, search_past_experiments
from app.sandbox.e2b_runner import SandboxCodeError, run_classification
from app.tracking.mlflow_logger import parse_model_results

logger = logging.getLogger("axiomforge")

EXPERIMENT_CSV_SCHEMA = "age:float, monthly_spend:float, tenure_months:int, churn:int"


def approval_gate(state: AgentState) -> dict:
    logger.info("approval_gate status=%s", state.get("approval_status", ""))
    return {}


def route_after_verifier(state: AgentState) -> str:
    if state.get("critic_continue"):
        return "experiment_node"
    return "report_node"


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
    prompt = f"User question:\n{state.get('query', '')}\n\nHypothesis:\n{hypothesis}"
    criticism = state.get("verifier_feedback", "")
    if criticism:
        logger.info("experiment critic round=%s", state.get("critic_rounds", 0))
        logger.info("experiment critic=%s", criticism)
        result = execute_experiment(
            prompt,
            EXPERIMENT_CSV_SCHEMA,
            existing_code=state.get("current_experiment_code", ""),
            criticism=criticism,
            record_memory=False,
        )
    else:
        result = execute_experiment(prompt, EXPERIMENT_CSV_SCHEMA)
    logger.info("experiment result status=%s", result.get("status"))
    metrics = {
        name: float(result[name])
        for name in ("accuracy", "f1")
        if name in result
    }
    return {
        "current_experiment_code": result.get("code", ""),
        "experiment_metrics": metrics,
        "model_results": list(result.get("model_results") or []),
        "dataset_profile": dict(result.get("dataset_profile") or {}),
        "critic_continue": False,
    }


def report_node(state: AgentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    run_id = str(configurable.get("thread_id") or "run")
    past_experiments = search_past_experiments(state.get("query", ""), k=3)
    logger.info("report_node run_id=%s verification=%s", run_id, state.get("verification_status", ""))
    path = write_workshop_paper(state, past_experiments, run_id)
    logger.info("report saved path=%s", path)
    return {"research_status": "Completed"}


def verifier_node(state: AgentState) -> dict:
    code = state.get("current_experiment_code", "")
    original = state.get("experiment_metrics") or {}
    rounds = int(state.get("critic_rounds", 0))
    logger.info("verifier_node round=%s original_metrics=%s", rounds, original)
    reasons: list[str] = []
    if not code or not original:
        reasons.append("Deney metrik üretmedi.")
    else:
        rewritten = rewrite_seeds(code)
        logger.info("verifier rewritten seeds in experiment code")
        try:
            output = run_classification(rewritten, EXPERIMENT_CSV_SCHEMA)
            renewed = parse_model_results(output)
        except (SandboxCodeError, RuntimeError) as exc:
            logger.error("verifier sandbox failed: %s", exc)
            reasons.append(f"Overfitting/Unstable: seed yeniden çalışması başarısız. {exc}")
        else:
            logger.info("verifier seed metrics original=%s renewed=%s", original, renewed)
            original_models = list(state.get("model_results") or [])
            if not original_models:
                original_models = [
                    {
                        "model": "classifier",
                        "accuracy": float(original.get("accuracy", 0.0)),
                        "f1": float(original.get("f1", 0.0)),
                        "train_seconds": 0.0,
                    }
                ]
            if models_dropped(original_models, renewed):
                logger.info("Overfitting/Unstable original=%s renewed=%s", original_models, renewed)
                reasons.append(
                    "Overfitting/Unstable: seed değişince performans %10'dan fazla düştü. "
                    f"original={original_models} renewed={renewed}"
                )
    if code:
        leakage, leakage_reason = judge_data_leakage(code)
        logger.info("verifier leakage=%s reason=%s", leakage, leakage_reason)
        if leakage:
            reasons.append(f"Leakage çözülemedi: {leakage_reason}")
    if not reasons:
        logger.info("verification_status=Passed")
        return {
            "verification_status": "Passed",
            "verifier_feedback": "",
            "critic_continue": False,
        }
    feedback = " ".join(reasons)
    logger.info("verification_status=Failed feedback=%s", feedback)
    if rounds >= MAX_CRITIC_ROUNDS:
        hypothesis = state["hypotheses"][0] if state.get("hypotheses") else state.get("query", "")
        metric = " ".join(f"{name}={value}" for name, value in original.items())
        memory_id = save_experiment(
            hypothesis=hypothesis,
            code=code,
            metric=metric,
            error_log=feedback,
            is_success=False,
        )
        logger.info("saved rejected verification memory_id=%s", memory_id)
        return {
            "verification_status": "Failed",
            "verifier_feedback": feedback,
            "critic_continue": False,
        }
    return {
        "verification_status": "Failed",
        "verifier_feedback": feedback,
        "critic_rounds": rounds + 1,
        "critic_continue": True,
    }
