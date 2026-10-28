import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable

from app.campaign.runner import DEFAULT_WORKERS, run_campaign
from app.research import session
from app.research.protocol import ProtocolError

logger = logging.getLogger("axiomforge")

HEARTBEAT_FILE = "heartbeat"
CANCEL_FLAG = "cancel.flag"
HEARTBEAT_SECONDS = 15
ALIVE_SECONDS = 90
ACTIVE = {"queued", "running"}
RETRYABLE = {"failed", "cancelled", "aborted"}


class SessionControlError(RuntimeError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def new_session_id() -> str:
    return f"r-{uuid.uuid4().hex[:8]}"


def _path(session_id: str, name: str):
    return session.session_dir(session_id) / name


def beat(session_id: str) -> None:
    path = _path(session_id, HEARTBEAT_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    os.utime(path, None)


def heartbeat_age(session_id: str, now: float | None = None) -> float | None:
    try:
        stamp = _path(session_id, HEARTBEAT_FILE).stat().st_mtime
    except OSError:
        return None
    return max(0.0, (time.time() if now is None else now) - stamp)


def is_alive(session_id: str, now: float | None = None) -> bool:
    age = heartbeat_age(session_id, now)
    return age is not None and age <= ALIVE_SECONDS


def clear_heartbeat(session_id: str) -> None:
    _path(session_id, HEARTBEAT_FILE).unlink(missing_ok=True)


def request_cancel(session_id: str) -> None:
    path = _path(session_id, CANCEL_FLAG)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def cancel_requested(session_id: str) -> bool:
    return _path(session_id, CANCEL_FLAG).exists()


def clear_cancel(session_id: str) -> None:
    _path(session_id, CANCEL_FLAG).unlink(missing_ok=True)


@contextmanager
def beating(session_id: str):
    stop = threading.Event()

    def pulse() -> None:
        while True:
            try:
                beat(session_id)
            except OSError:
                logger.exception("research session %s: could not write the heartbeat", session_id)
            if stop.wait(HEARTBEAT_SECONDS):
                return

    beat(session_id)
    thread = threading.Thread(target=pulse, name="research-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def effective_state(state: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    status = state.get("status")
    if status not in ACTIVE:
        return state
    session_id = str(state["id"])
    if status == "running" and not is_alive(session_id, now):
        return {**state, "status": "failed", "stale": True, "reason": "the worker of this session stopped reporting; start it again to continue from the saved stages"}
    if cancel_requested(session_id):
        return {**state, "cancel_requested": True}
    return state


def _existing(session_id: str) -> dict[str, Any]:
    try:
        state = session.load(session_id)
    except ProtocolError as exc:
        raise SessionControlError("invalid session id", 400) from exc
    if state is None:
        raise SessionControlError("session not found", 404)
    return state


def execute_session(
    session_id: str,
    execute: Callable[[str, str], str] | None = None,
    workers: int = DEFAULT_WORKERS,
    runner: Callable[..., dict[str, Any]] = run_campaign,
) -> dict[str, Any] | None:
    state = session.load(session_id)
    if state is None or state.get("status") != "queued":
        return state
    config = session.SessionConfig(**state["config"])
    try:
        with beating(session_id):
            return session.run_session(config, execute, workers, runner, should_stop=lambda: cancel_requested(session_id))
    except Exception as exc:
        logger.exception("research session %s failed", session_id)
        return session.close(session_id, "failed", f"{type(exc).__name__}: {exc}")


def cancel_session(session_id: str) -> dict[str, Any]:
    state = _existing(session_id)
    shown = effective_state(state)
    if shown["status"] not in ACTIVE:
        raise SessionControlError(f"the session is already {shown['status']}", 409)
    if state["status"] == "queued":
        return session.close(session_id, "cancelled", "cancelled before it started")
    request_cancel(session_id)
    return {**state, "cancel_requested": True}


def retry_session(session_id: str, before: Callable[[], None] | None = None) -> dict[str, Any]:
    state = _existing(session_id)
    shown = effective_state(state)
    if shown["status"] not in RETRYABLE:
        raise SessionControlError(f"the session is {shown['status']} and cannot be started again", 409)
    if before is not None:
        before()
    fields = dict(state["config"])
    own_stages = shown["status"] != "aborted" and session.has_stage(session_id, "default")
    fields["reuse"] = session_id if own_stages else (None if shown["status"] == "aborted" else fields.get("reuse"))
    session.reset_for_retry(session_id)
    clear_cancel(session_id)
    clear_heartbeat(session_id)
    return session.queue_session(session.SessionConfig(**fields))
