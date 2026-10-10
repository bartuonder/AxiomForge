import logging

import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.agents.experiment import MODEL, PROMPT_VERSION, generate_classification_code
from app.celery_app import celery_app
from app.config import REDIS_URL
from app.sandbox.e2b_runner import run_classification
from app.tracking.mlflow_logger import (
    detect_algorithm,
    log_classification_run,
    parse_metrics,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("axiomforge")

app = FastAPI(title="AxiomForge")


class ExperimentRequest(BaseModel):
    prompt: str = Field(min_length=1)
    csv_schema: str = Field(min_length=1)


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
        source = generate_classification_code(body.prompt, body.csv_schema)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        output = run_classification(source, body.csv_schema)
        metrics = parse_metrics(output)
        run_id = log_classification_run(
            metrics,
            prompt_version=PROMPT_VERSION,
            algorithm=detect_algorithm(source),
            model=MODEL,
        )
    except Exception:
        logger.exception("sandbox execution failed")
        return {"code": source}
    payload = {"code": source, "mlflow_run_id": run_id}
    payload.update(metrics)
    return payload
