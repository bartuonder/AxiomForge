import logging
from pathlib import Path
from typing import Literal

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from kombu.exceptions import OperationalError
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.agents.experiment import QueryNamesTooFewModels
from app.campaign import store as campaign_store
from app.campaign.demos import demo_spec
from app.campaign.service import campaign_summary, queue_campaign, reject_campaign
from app.campaign.spec import CampaignSpecError
from app.celery_app import celery_app
from app.config import REDIS_URL
from app.experiments import execute_experiment
from app.graph.workflow import PlanDecisionError, decide_plan, get_research, new_thread_id, revoke_approval
from app.openai_check import check_openai_access
from app.tasks import resume_research_task, run_campaign_task, run_research_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("axiomforge")

app = FastAPI(title="AxiomForge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExperimentRequest(BaseModel):
    prompt: str = Field(min_length=1)
    csv_schema: str = Field(min_length=1)


class StartResearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: Literal["experiment", "campaign"] = "experiment"


class StartCampaignRequest(BaseModel):
    demo: str | None = None
    spec: dict | None = None
    datasets: list[str] | None = None


class ApprovePlanRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    selected: int | None = None


def _too_few_models_detail(exc: QueryNamesTooFewModels) -> str:
    return f"{exc}: name at least two models in the query so that they can be compared, for example SVM and Random Forest."


def redis_status() -> str:
    client = redis.Redis.from_url(
        REDIS_URL,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        client.ping()
        return "ok"
    except Exception:
        return "down"
    finally:
        client.close()


def celery_status() -> str:
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        reply = inspector.ping()
        if reply:
            return "ok"
        return "down"
    except Exception:
        return "down"


@app.get("/health")
def health():
    redis_state = redis_status()
    celery_state = celery_status()
    payload = {"redis": redis_state, "celery": celery_state}
    code = 200 if redis_state == "ok" and celery_state == "ok" else 503
    return JSONResponse(status_code=code, content=payload)


@app.post("/experiments")
def create_experiment(body: ExperimentRequest):
    try:
        return execute_experiment(body.prompt, body.csv_schema)
    except QueryNamesTooFewModels as exc:
        raise HTTPException(status_code=422, detail=_too_few_models_detail(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _enqueue(task, *args) -> None:
    try:
        task.delay(*args)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"task queue is unavailable: {exc}") from exc


@app.post("/start_research")
def start_research_endpoint(body: StartResearchRequest):
    try:
        thread_id = new_thread_id(body.query, body.mode)
        check_openai_access()
        _enqueue(run_research_task, thread_id, body.query, body.mode)
        return {"thread_id": thread_id, "status": "running", "mode": body.mode}
    except QueryNamesTooFewModels as exc:
        raise HTTPException(status_code=422, detail=_too_few_models_detail(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/research/{thread_id}")
def research_status(thread_id: str):
    try:
        return get_research(thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/reports/{thread_id}")
def research_report(thread_id: str):
    if any(char in thread_id for char in "/\\."):
        raise HTTPException(status_code=400, detail="invalid thread id")
    path = Path(__file__).resolve().parents[1] / "reports" / f"{thread_id}_paper.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="report not ready")
    return {"markdown": path.read_text(encoding="utf-8")}


@app.post("/approve_plan")
def approve_plan_endpoint(body: ApprovePlanRequest):
    try:
        result = decide_plan(body.thread_id, body.decision, body.selected)
        if result["approval_status"] == "approved":
            try:
                _enqueue(resume_research_task, body.thread_id)
            except HTTPException:
                revoke_approval(body.thread_id)
                raise
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PlanDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/start_campaign")
def start_campaign_endpoint(body: StartCampaignRequest):
    if (body.demo is None) == (body.spec is None):
        raise HTTPException(status_code=422, detail="give exactly one of demo and spec")
    try:
        spec = demo_spec(body.demo) if body.demo is not None else dict(body.spec)
        if body.datasets is not None:
            spec["datasets"] = body.datasets
        campaign_id, spec = queue_campaign(spec)
    except CampaignSpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        _enqueue(run_campaign_task, campaign_id, spec)
    except HTTPException as exc:
        reject_campaign(campaign_id, str(exc.detail))
        raise
    return {"campaign_id": campaign_id, "status": "queued"}


@app.get("/campaigns")
def campaigns_list():
    ids = campaign_store.list_campaigns()
    states = [state for state in (campaign_store.load_state(campaign_id) for campaign_id in ids) if state]
    items = sorted((campaign_summary(state) for state in states), key=lambda item: item["updated"], reverse=True)
    return {"campaigns": ids, "items": items}


def _campaign_state(campaign_id: str) -> dict:
    try:
        state = campaign_store.load_state(campaign_id)
    except campaign_store.CampaignStoreError as exc:
        raise HTTPException(status_code=400, detail="invalid campaign id") from exc
    if state is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return state


@app.get("/campaign/{campaign_id}")
def campaign_status(campaign_id: str):
    return _campaign_state(campaign_id)


@app.get("/campaign/{campaign_id}/report")
def campaign_report(campaign_id: str):
    _campaign_state(campaign_id)
    markdown = campaign_store.load_report(campaign_id)
    if markdown is None:
        raise HTTPException(status_code=404, detail="report not ready")
    return {"markdown": markdown, "ledger": campaign_store.load_ledger(campaign_id)}
