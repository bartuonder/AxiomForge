from app.campaign.service import execute_campaign
from app.campaign.tracking import log_campaign
from app.celery_app import celery_app
from app.graph.errors import record_error
from app.graph.workflow import resume_campaign, resume_research, run_until_pause


@celery_app.task(name="axiomforge.run_research", ignore_result=True)
def run_research_task(thread_id: str, query: str, mode: str = "experiment") -> None:
    run_until_pause(thread_id, query, mode)


@celery_app.task(name="axiomforge.resume_research", ignore_result=True)
def resume_research_task(thread_id: str) -> None:
    resume_research(thread_id)


RESUME_ATTEMPTS = 40
RESUME_DELAY_SECONDS = 5


@celery_app.task(name="axiomforge.run_campaign", ignore_result=True)
def run_campaign_task(campaign_id: str, spec: dict, thread_id: str | None = None) -> None:
    execute_campaign(spec, campaign_id, tracker=log_campaign)
    if thread_id:
        resume_campaign_task.delay(thread_id)


@celery_app.task(name="axiomforge.resume_campaign", ignore_result=True)
def resume_campaign_task(thread_id: str, attempt: int = 1) -> None:
    if resume_campaign(thread_id) != "waiting":
        return
    if attempt >= RESUME_ATTEMPTS:
        record_error(thread_id, "the research graph never reached the campaign collection step")
        return
    resume_campaign_task.apply_async((thread_id, attempt + 1), countdown=RESUME_DELAY_SECONDS)
