import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.celery_app import celery_app
from app.config import REDIS_URL

app = FastAPI(title="AxiomForge")


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
