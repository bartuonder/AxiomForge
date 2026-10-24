import logging

from langchain_core.runnables import RunnableConfig

from app.campaign import store
from app.campaign.service import campaign_id_for, queue_once, reject_campaign
from app.graph.state import AgentState

logger = logging.getLogger("axiomforge")

FINAL_STATUSES = {"completed", "needs_review", "failed"}


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
