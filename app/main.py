import logging
from pathlib import Path

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.config import REDIS_URL
from app.experiments import execute_experiment
from app.graph.workflow import approve_plan, get_research, start_research

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


class ApprovePlanRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)


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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/start_research")
def start_research_endpoint(body: StartResearchRequest):
    try:
        return start_research(body.query)
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
        return approve_plan(body.thread_id, body.decision)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
