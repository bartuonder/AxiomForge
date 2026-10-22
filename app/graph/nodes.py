import logging
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from app.agents.consistency import (
    conclusion_issues,
    direction_conflict,
    instability_issues,
    judge_consistency,
    performance_issues,
    reliability_issue,
    verification_issue,
)
from app.agents.experiment import MODEL, PROMPT_VERSION, requested_models
from app.agents.literature import run_literature_agent
from app.agents.report import write_workshop_paper
from app.agents.planner import run_planner_agent
from app.experiments import execute_experiment
from app.graph.selection import primary_hypothesis
from app.graph.state import AgentState
from app.graph.verifier import (
    MAX_CRITIC_ROUNDS,
    VERIFICATION_SEEDS,
    has_split_loop,
    hypothesis_verdict,
    instability_finding,
    instability_text,
    judge_data_leakage,
    metric_summary,
    performance_comparisons,
    rewrite_seeds,
    seeded_rows,
    stability_decision,
    summarize_seed_runs,
)
from app.memory.rag_memory import save_experiment, search_past_experiments
from app.sandbox.e2b_runner import SandboxCodeError, run_classification
from app.tracking.mlflow_logger import (
    detect_algorithm,
    log_failed_run,
    log_verified_comparison,
    parse_model_results,
)

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


def _remember(
    state: AgentState,
    code: str,
    metric: str,
    is_success: bool,
    outcome: str,
    error_log: str = "",
    finding: str = "",
) -> None:
    hypothesis, spec = primary_hypothesis(state)
    memory_id = save_experiment(
        hypothesis=hypothesis,
        code=code,
        metric=metric,
        error_log=error_log,
        is_success=is_success,
        outcome=outcome,
        finding=finding,
        spec=spec,
    )
    logger.info("saved %s memory_id=%s", outcome, memory_id)


def _track_verified(
    state: AgentState,
    collected: list[list[dict[str, str | float]]],
    summary: dict[str, dict[str, float] | str],
    decision: dict,
) -> str:
    hypothesis, spec = primary_hypothesis(state)
    try:
        run_id = log_verified_comparison(
            seeded_rows(collected),
            summary,
            decision,
            prompt_version=PROMPT_VERSION,
            model=MODEL,
            critic_rounds=int(state.get("critic_rounds", 0)),
            hypothesis=hypothesis,
            dataset=state.get("dataset_profile") or None,
            spec=spec,
        )
    except Exception:
        logger.exception("mlflow logging failed")
        return ""
    logger.info("mlflow verified run_id=%s", run_id)
    return run_id


def _track_failure(state: AgentState, code: str, error: str) -> str:
    try:
        run_id = log_failed_run(
            prompt_version=PROMPT_VERSION,
            algorithm=detect_algorithm(code),
            model=MODEL,
            attempts=int(state.get("critic_rounds", 0)) + 1,
            error=error,
        )
    except Exception:
        logger.exception("mlflow logging failed")
        return ""
    logger.info("mlflow failed run_id=%s", run_id)
    return run_id


def experiment_node(state: AgentState) -> dict:
    logger.info("Onaylandı, deneylere başlanıyor")
    query = state.get("query", "")
    allowed = requested_models(query)
    logger.info("experiment query_models=%s", [item["key"] for item in allowed])
    hypothesis, spec = primary_hypothesis(state)
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
            track_run=False,
            models=allowed,
            spec=spec,
        )
    else:
        result = execute_experiment(
            prompt,
            EXPERIMENT_CSV_SCHEMA,
            record_memory=False,
            track_run=False,
            models=allowed,
            spec=spec,
        )
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
        "experiment_error": str(result.get("error") or ""),
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
        issues = [conflict]
    else:
        _, issues = judge_consistency(paper, statistical_results, decision)
        issues.extend(conclusion_issues(paper, decision))
    unverified = verification_issue(paper, state.get("verification_status", ""))
    if unverified:
        issues.append(unverified)
    issues.extend(instability_issues(paper, decision.get("instability")))
    reliability = reliability_issue(paper, state.get("verification_status", ""))
    if reliability:
        issues.append(reliability)
    issues.extend(performance_issues(paper, decision.get("performance")))
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
        reasons.append(f"Deney metrik üretmedi. {state.get('experiment_error', '')}".strip())
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
    claim = (primary_hypothesis(state)[1] or {}).get("claim")
    decision["hypothesis"] = hypothesis_verdict(claim, decision)
    logger.info("verifier hypothesis=%s", decision["hypothesis"])
    logger.info("verifier statistical_decision=%s", decision)
    if not reasons:
        logger.info("verification_status=Passed")
        finding = instability_text(decision["instability"])
        _remember(
            state,
            code,
            metric_summary(statistical_results),
            True,
            "finding" if finding else "success",
            finding=finding,
        )
        return {
            "mlflow_run_id": _track_verified(state, collected, statistical_results, decision),
            "verification_status": "Passed",
            "verifier_feedback": "",
            "critic_continue": False,
            "statistical_results": statistical_results,
            "statistical_decision": decision,
        }
    feedback = " ".join(reasons)
    logger.info("verification_status=Failed feedback=%s", feedback)
    if rounds >= MAX_CRITIC_ROUNDS:
        metric = metric_summary(statistical_results) or " ".join(
            f"{name}={value}" for name, value in original.items()
        )
        _remember(state, code, metric, False, "failure", error_log=feedback)
        return {
            "mlflow_run_id": _track_failure(state, code, feedback),
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
