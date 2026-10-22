import logging
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from app.agents.consistency import conclusion_issues, direction_conflict, judge_consistency
from app.agents.experiment import requested_models
from app.agents.literature import run_literature_agent
from app.agents.report import write_workshop_paper
from app.agents.planner import run_planner_agent
from app.experiments import execute_experiment
from app.graph.state import AgentState
from app.graph.verifier import (
    MAX_CRITIC_ROUNDS,
    VERIFICATION_SEEDS,
    has_split_loop,
    instability_finding,
    judge_data_leakage,
    performance_comparisons,
    rewrite_seeds,
    stability_decision,
    summarize_seed_runs,
)
from app.memory.rag_memory import save_experiment, search_past_experiments
from app.sandbox.e2b_runner import SandboxCodeError, run_classification
from app.tracking.mlflow_logger import parse_model_results

logger = logging.getLogger("axiomforge")

EXPERIMENT_CSV_SCHEMA = "age:float, monthly_spend:float, tenure_months:int, churn:int"
MAX_CONSISTENCY_ROUNDS = 2


def approval_gate(state: AgentState) -> dict:
    logger.info("approval_gate status=%s", state.get("approval_status", ""))
    return {}


def route_after_verifier(state: AgentState) -> str:
    if state.get("critic_continue"):
        return "experiment_node"
    return "report_node"


def route_after_consistency(state: AgentState) -> str:
    if state.get("consistency_continue"):
        return "report_node"
    return "end"


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
    specs, memory_note = run_planner_agent(
        state["query"],
        state["literature_context"],
        failed_experiments,
        requested_models(state["query"]),
    )
    if memory_note:
        logger.info("planner memory_note=%s", memory_note)
    for index, item in enumerate(specs, start=1):
        logger.info("hypothesis %s=%s", index, item)
    return {
        "hypotheses": [item["statement"] for item in specs],
        "experiment_specs": specs,
    }


def experiment_node(state: AgentState) -> dict:
    logger.info("Onaylandı, deneylere başlanıyor")
    query = state.get("query", "")
    allowed = requested_models(query)
    logger.info("experiment query_models=%s", [item["key"] for item in allowed])
    hypothesis = state["hypotheses"][0] if state["hypotheses"] else query
    prompt = f"User question:\n{query}\n\nHypothesis:\n{hypothesis}"
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
            models=allowed,
        )
    else:
        result = execute_experiment(prompt, EXPERIMENT_CSV_SCHEMA, models=allowed)
    logger.info("experiment result status=%s", result.get("status"))
    metrics = {
        name: float(result[name])
        for name in ("accuracy", "f1")
        if name in result
    }
    model_results = list(result.get("model_results") or [])
    tested_models: list[str] = []
    for item in model_results:
        name = str(item.get("model", ""))
        if name and name not in tested_models:
            tested_models.append(name)
    return {
        "current_experiment_code": result.get("code", ""),
        "experiment_metrics": metrics,
        "model_results": model_results,
        "tested_models": tested_models,
        "dataset_profile": dict(result.get("dataset_profile") or {}),
        "critic_continue": False,
    }


def report_node(state: AgentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    run_id = str(configurable.get("thread_id") or "run")
    past_experiments = search_past_experiments(state.get("query", ""), k=3)
    logger.info("report_node run_id=%s verification=%s", run_id, state.get("verification_status", ""))
    if state.get("consistency_feedback"):
        logger.info("report_node rewrite round=%s", state.get("consistency_rounds", 0))
        logger.info("report_node claim_review=%s", state.get("consistency_feedback", ""))
    path = write_workshop_paper(state, past_experiments, run_id)
    logger.info("report saved path=%s", path)
    return {
        "paper_markdown": Path(path).read_text(encoding="utf-8"),
        "consistency_continue": False,
    }


def consistency_checker_node(state: AgentState) -> dict:
    rounds = int(state.get("consistency_rounds", 0))
    paper = state.get("paper_markdown", "")
    statistical_results = state.get("statistical_results") or {}
    decision = state.get("statistical_decision") or {}
    logger.info("consistency_checker_node round=%s", rounds)
    conflict = direction_conflict(paper, decision)
    if conflict:
        logger.info("consistency direction_conflict=%s", conflict)
        consistent = False
        issues = [conflict]
    else:
        consistent, issues = judge_consistency(paper, statistical_results, decision)
        issues.extend(conclusion_issues(paper, decision))
        consistent = not issues
    for issue in issues:
        logger.info("consistency issue=%s", issue)
    if consistent:
        logger.info("consistency_checker_node passed")
        return {
            "consistency_feedback": "",
            "consistency_continue": False,
            "research_status": "Completed",
        }
    feedback = " ".join(issues)
    logger.info("consistency_checker_node failed issue_count=%s", len(issues))
    if rounds >= MAX_CONSISTENCY_ROUNDS:
        logger.info("consistency_checker_node stopped after %s rewrites", rounds)
        return {
            "consistency_feedback": feedback,
            "consistency_continue": False,
            "research_status": "NeedsReview",
        }
    logger.info("consistency_checker_node returning to report_node")
    return {
        "consistency_feedback": feedback,
        "consistency_rounds": rounds + 1,
        "consistency_continue": True,
    }


def verifier_node(state: AgentState) -> dict:
    code = state.get("current_experiment_code", "")
    original = state.get("experiment_metrics") or {}
    rounds = int(state.get("critic_rounds", 0))
    logger.info("verifier_node round=%s original_metrics=%s", rounds, original)
    reasons: list[str] = []
    statistical_results: dict[str, dict[str, float] | str] = {}
    collected: list[list[dict[str, str | float]]] = []
    if not code or not original:
        reasons.append("Deney metrik üretmedi.")
    else:
        try:
            first_output = run_classification(code, EXPERIMENT_CSV_SCHEMA)
            first_rows = parse_model_results(first_output)
        except (SandboxCodeError, RuntimeError) as exc:
            logger.error("verifier split loop failed: %s", exc)
            reasons.append(f"Çalışma hatası: split döngüsü çalışmadı. {exc}")
            first_rows = []
        if first_rows and has_split_loop(first_rows):
            logger.info("verifier uses the script split loop rows=%s", len(first_rows))
            collected.append(first_rows)
        elif not reasons:
            for seed in VERIFICATION_SEEDS:
                rewritten = rewrite_seeds(code, seed)
                logger.info("verifier split random_state=%s", seed)
                try:
                    output = run_classification(rewritten, EXPERIMENT_CSV_SCHEMA)
                    collected.append(parse_model_results(output))
                except (SandboxCodeError, RuntimeError) as exc:
                    logger.error("verifier seed=%s failed: %s", seed, exc)
                    reasons.append(f"Çalışma hatası: seed={seed} çalışması başarısız. {exc}")
                    break
        statistical_results = summarize_seed_runs(collected)
        logger.info("verifier statistical_results=%s", statistical_results)
    if code:
        leakage, leakage_reason = judge_data_leakage(code)
        logger.info("verifier leakage=%s reason=%s", leakage, leakage_reason)
        if leakage:
            reasons.append(f"Leakage çözülemedi: {leakage_reason}")
    decision = stability_decision(collected)
    decision["instability"] = instability_finding(statistical_results)
    logger.info("verifier instability=%s", decision["instability"])
    decision["performance"] = performance_comparisons(
        collected,
        float((state.get("dataset_profile") or {}).get("samples", 0.0)),
    )
    logger.info("verifier statistical_decision=%s", decision)
    if not reasons:
        logger.info("verification_status=Passed")
        return {
            "verification_status": "Passed",
            "verifier_feedback": "",
            "critic_continue": False,
            "statistical_results": statistical_results,
            "statistical_decision": decision,
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
            "statistical_results": statistical_results,
            "statistical_decision": decision,
        }
    return {
        "verification_status": "Failed",
        "verifier_feedback": feedback,
        "critic_rounds": rounds + 1,
        "critic_continue": True,
        "statistical_results": statistical_results,
        "statistical_decision": decision,
    }
