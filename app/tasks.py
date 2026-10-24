from app.campaign.service import execute_campaign
from app.celery_app import celery_app
from app.graph.workflow import resume_research, run_until_pause


@celery_app.task(name="axiomforge.run_research", ignore_result=True)
def run_research_task(thread_id: str, query: str) -> None:
    run_until_pause(thread_id, query)


@celery_app.task(name="axiomforge.resume_research", ignore_result=True)
def resume_research_task(thread_id: str) -> None:
    resume_research(thread_id)


@celery_app.task(name="axiomforge.run_campaign", ignore_result=True)
def run_campaign_task(campaign_id: str, spec: dict) -> None:
    execute_campaign(spec, campaign_id)
