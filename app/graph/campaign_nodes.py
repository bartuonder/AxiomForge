import logging
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from app.agents.consistency_meta import meta_issues
from app.agents.meta_report import write_meta_paper
from app.campaign import store
from app.campaign.service import campaign_id_for, queue_once, reject_campaign
from app.graph.state import AgentState

logger = logging.getLogger("axiomforge")

FINAL_STATUSES = {"completed", "needs_review", "failed"}
MAX_META_ROUNDS = 2


def _enqueue_campaign(campaign_id: str, spec: dict, thread_id: str) -> None:
    from app.tasks import run_campaign_task

    run_campaign_task.delay(campaign_id, spec, thread_id)


def campaign_dispatch_node(state: AgentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = str(configurable.get("thread_id") or "")
    if not thread_id:
        raise RuntimeError("the campaign needs a research thread id")
    raw_spec = state.get("campaign_spec") or {}
    if not raw_spec:
        raise RuntimeError("no campaign was approved")
    campaign_id = campaign_id_for(thread_id, raw_spec)
    spec, created = queue_once(campaign_id, raw_spec)
    logger.info("campaign_dispatch_node thread_id=%s campaign_id=%s created=%s", thread_id, campaign_id, created)
    if created:
        try:
            _enqueue_campaign(campaign_id, spec, thread_id)
        except Exception as exc:
            reject_campaign(campaign_id, f"the campaign could not be queued: {exc}")
            raise
    return {"campaign_id": campaign_id, "campaign_status": "queued"}


def campaign_collect_node(state: AgentState) -> dict:
    campaign_id = state.get("campaign_id") or ""
    if not campaign_id:
        raise RuntimeError("no campaign was dispatched")
    campaign = store.load_state(campaign_id)
    if campaign is None:
        raise RuntimeError(f"campaign {campaign_id} was not found")
    status = campaign["status"]
    logger.info("campaign_collect_node campaign_id=%s status=%s", campaign_id, status)
    if status not in FINAL_STATUSES:
        raise RuntimeError(f"campaign {campaign_id} has not finished: {status}")
    if status == "failed":
        raise RuntimeError(f"campaign failed: {campaign.get('error') or 'no error was recorded'}")
    analysis = store.load_analysis(campaign_id)
    ledger = store.load_ledger(campaign_id)
    if analysis is None or ledger is None:
        raise RuntimeError(f"campaign {campaign_id} finished without its analysis and ledger")
    return {
        "campaign_status": status,
        "campaign_analysis": analysis,
        "campaign_ledger": ledger,
        "campaign_issues": list(campaign.get("issues") or []),
        "campaign_mlflow_run_id": str(campaign.get("mlflow_run_id") or ""),
    }


def meta_report_node(state: AgentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    run_id = str(configurable.get("thread_id") or "run")
    if state.get("consistency_feedback"):
        logger.info("meta_report_node rewrite round=%s review=%s", state.get("consistency_rounds", 0), state.get("consistency_feedback", ""))
    path = write_meta_paper(state, run_id)
    logger.info("meta report saved path=%s", path)
    return {"paper_markdown": Path(path).read_text(encoding="utf-8"), "consistency_continue": False}


def meta_consistency_node(state: AgentState) -> dict:
    rounds = int(state.get("consistency_rounds", 0))
    issues = meta_issues(
        state.get("paper_markdown", ""),
        state.get("campaign_spec") or {},
        state.get("campaign_analysis") or {},
        list(state.get("campaign_ledger") or []),
        list(state.get("literature_sources") or []),
    )
    for issue in issues:
        logger.info("meta consistency issue=%s", issue)
    if issues and rounds < MAX_META_ROUNDS:
        logger.info("meta_consistency_node failed issue_count=%s, returning to meta_report_node", len(issues))
        return {"consistency_feedback": " ".join(issues), "consistency_rounds": rounds + 1, "consistency_continue": True}
    campaign_issues = [f"Campaign check: {item}" for item in state.get("campaign_issues") or []]
    if issues or campaign_issues or state.get("campaign_status") == "needs_review":
        logger.info("meta_consistency_node stopped after %s rewrites", rounds)
        return {
            "consistency_feedback": " ".join(issues + campaign_issues),
            "consistency_continue": False,
            "research_status": "NeedsReview",
            "referee_notes": [],
        }
    logger.info("meta_consistency_node passed")
    return {"consistency_feedback": "", "consistency_continue": False, "research_status": "Completed", "referee_notes": []}


def route_after_meta_consistency(state: AgentState) -> str:
    if state.get("consistency_continue"):
        return "meta_report_node"
    return "end"
