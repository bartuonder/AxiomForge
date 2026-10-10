import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.agents.experiment import generate_classification_code
from app.celery_app import celery_app
from app.config import REDIS_URL

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
    return {"code": source}
