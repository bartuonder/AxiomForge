import hmac
import json
import os
import tempfile
import threading
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException

USAGE_FILE = Path(__file__).resolve().parents[1] / "reports" / "usage.json"
DEFAULT_DAILY_LIMIT = 100
_LOCK = threading.Lock()


def today() -> date:
    return date.today()


def api_key() -> str:
    return os.getenv("API_KEY", "")


def daily_limit() -> int:
    try:
        value = int(os.getenv("DAILY_START_LIMIT", ""))
    except ValueError:
        return DEFAULT_DAILY_LIMIT
    return value if value >= 0 else DEFAULT_DAILY_LIMIT


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = api_key()
    if expected and not hmac.compare_digest((x_api_key or "").encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="[unauthorized] a valid X-API-Key header is needed")


def _read() -> dict[str, int]:
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): int(value) for key, value in data.items() if isinstance(value, int)} if isinstance(data, dict) else {}


def _write(data: dict[str, int]) -> None:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=USAGE_FILE.parent, suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(data, stream)
    os.replace(name, USAGE_FILE)


def spend_start() -> None:
    limit = daily_limit()
    key = today().isoformat()
    with _LOCK:
        used = _read().get(key, 0)
        if limit and used >= limit:
            raise HTTPException(status_code=429, detail=f"[daily_limit] the limit of {limit} starts per day has been reached")
        _write({key: used + 1})


def usage() -> dict[str, Any]:
    limit = daily_limit()
    key = today().isoformat()
    used = _read().get(key, 0)
    return {"date": key, "used": used, "limit": limit, "remaining": max(0, limit - used) if limit else None}
