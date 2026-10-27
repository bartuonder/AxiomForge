import hashlib
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from app.campaign import store
from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report, report_issues
from app.campaign.provenance import spec_digest
from app.campaign.runner import DEFAULT_WORKERS, MAX_ATTEMPTS, run_campaign
from app.campaign.spec import CampaignSpecError, validate_campaign
from app.seeds import SPLIT_SEEDS

logger = logging.getLogger("axiomforge")

PROGRESS_FIELDS = ("status", "attempts", "seconds", "error")
STALE_SECONDS = 1200
HEARTBEAT_SECONDS = 15
ALIVE_SECONDS = 90
ACTIVE = {"queued", "running"}
RETRYABLE = {"failed", "cancelled"}


class CampaignControlError(RuntimeError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _progress(result: dict[str, Any]) -> dict[str, Any]:
    return {name: result[name] for name in PROGRESS_FIELDS if name in result}


def _verdicts(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": claim["id"], "statement": claim["statement"], "verdict": claim["verdict"]} for claim in analysis.get("claims", [])]


def _initial_state(campaign_id: str, spec: dict[str, Any], status: str, origin: str | None = None) -> dict[str, Any]:
    state = {
        "id": campaign_id,
        "title": spec["title"],
        "status": status,
        "spec_sha256": spec_digest(spec),
        "datasets": {dataset: {"status": "queued"} for dataset in spec["datasets"]},
    }
    return {**state, "origin": origin} if origin else state


def campaign_summary(state: dict[str, Any]) -> dict[str, Any]:
    statuses = [item.get("status") for item in state.get("datasets", {}).values()]
    return {
        "id": state["id"],
        "title": state.get("title", ""),
        "status": state["status"],
        "updated": state.get("updated", ""),
        "origin": state.get("origin") or ("console" if str(state["id"]).startswith("g-") else "unknown"),
        "statement": (state.get("verdicts") or [{}])[0].get("statement", ""),
        "datasets": len(statuses),
        "finished": statuses.count("finished"),
        "failed": statuses.count("failed"),
        "verdicts": [{"id": item["id"], "verdict": item["verdict"]} for item in state.get("verdicts", [])],
    }


def is_alive(campaign_id: str, now: float | None = None) -> bool:
    age = store.heartbeat_age(campaign_id, now)
    return age is not None and age <= ALIVE_SECONDS


@contextmanager
def _beating(campaign_id: str):
    stop = threading.Event()

    def beat() -> None:
        while True:
            try:
                store.beat(campaign_id)
            except OSError:
                logger.exception("campaign %s: could not write the heartbeat", campaign_id)
            if stop.wait(HEARTBEAT_SECONDS):
                return

    thread = threading.Thread(target=beat, name="campaign-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def effective_state(state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if state.get("status") not in ACTIVE:
        return state
    try:
        updated = datetime.fromisoformat(str(state.get("updated")))
    except ValueError:
        return _with_cancel_request(state)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    clock = now or _now()
    idle = (clock - updated).total_seconds()
    if idle <= STALE_SECONDS or is_alive(str(state["id"]), clock.timestamp()):
        return _with_cancel_request(state)
    return {**state, "status": "failed", "stale": True, "error": f"the campaign has reported no progress for {int(idle // 60)} minutes; its worker may have stopped"}


def _with_cancel_request(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("status") == "running" and store.cancel_requested(str(state["id"])):
        return {**state, "cancel_requested": True}
    return state


def _existing(campaign_id: str) -> dict[str, Any]:
    state = store.load_state(campaign_id)
    if state is None:
        raise CampaignControlError("campaign not found", 404)
    return state


def cancel_campaign(campaign_id: str) -> dict[str, Any]:
    state = _existing(campaign_id)
    shown = effective_state(state)
    if shown["status"] not in ACTIVE:
        raise CampaignControlError(f"the campaign is already {shown['status']}", 409)
    store.request_cancel(campaign_id)
    if state["status"] == "queued":
        cancelled = {
            **state,
            "status": "cancelled",
            "finished": store.now(),
            "datasets": {key: {"status": "cancelled"} for key in state.get("datasets", {})},
        }
        store.save_state(campaign_id, cancelled)
        return cancelled
    return {**state, "cancel_requested": True}


def retry_campaign(campaign_id: str, before: Callable[[], None] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _existing(campaign_id)
    shown = effective_state(state)
    if shown["status"] not in RETRYABLE:
        raise CampaignControlError(f"the campaign is {shown['status']} and cannot be started again", 409)
    spec = store.load_spec(campaign_id)
    if spec is None:
        raise CampaignControlError("the specification of this campaign was not saved", 409)
    if before is not None:
        before()
    restarted = {
        key: value
        for key, value in {**state, "status": "queued", "queued": store.now(), "recoveries": int(state.get("recoveries") or 0) + 1}.items()
        if key not in {"error", "finished", "issues", "verdicts", "finished_datasets", "failed_datasets", "mlflow_run_id"}
    }
    restarted["datasets"] = {key: {"status": "queued"} for key in state.get("datasets", {})}
    store.clear_cancel(campaign_id)
    store.save_state(campaign_id, restarted)
    return spec, restarted


def queue_campaign(raw_spec: Any, origin: str = "api") -> tuple[str, dict[str, Any]]:
    spec = validate_campaign(raw_spec)
    campaign_id = store.new_campaign_id()
    store.save_state(campaign_id, _initial_state(campaign_id, spec, "queued", origin) | {"queued": store.now()})
    store.save_spec(campaign_id, spec)
    return campaign_id, spec


def campaign_id_for(thread_id: str, spec: dict[str, Any]) -> str:
    canonical = json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "g-" + hashlib.sha256(f"{thread_id}\n{canonical}".encode("utf-8")).hexdigest()[:32]


def queue_once(campaign_id: str, raw_spec: Any, origin: str = "console", thread_id: str | None = None) -> tuple[dict[str, Any], bool]:
    spec = validate_campaign(raw_spec)
    if store.load_state(campaign_id) is not None:
        return spec, False
    remembered = {"thread_id": thread_id} if thread_id else {}
    store.save_state(campaign_id, _initial_state(campaign_id, spec, "queued", origin) | {"queued": store.now()} | remembered)
    store.save_spec(campaign_id, spec)
    return spec, True


def reject_campaign(campaign_id: str, reason: str) -> None:
    state = store.load_state(campaign_id)
    if state is not None:
        store.save_state(campaign_id, state | {"status": "failed", "error": reason, "finished": store.now()})


def _track(tracker: Callable[..., str] | None, campaign_id: str, *arguments: Any) -> str:
    if tracker is None:
        return ""
    try:
        return tracker(campaign_id, *arguments)
    except Exception:
        logger.exception("campaign %s: MLflow logging failed", campaign_id)
        return ""


def execute_campaign(
    raw_spec: Any,
    campaign_id: str | None = None,
    execute: Callable[[str, str], str] | None = None,
    workers: int = DEFAULT_WORKERS,
    seeds: tuple[int, ...] = SPLIT_SEEDS,
    attempts: int = MAX_ATTEMPTS,
    tracker: Callable[..., str] | None = None,
) -> dict[str, Any]:
    spec = validate_campaign(raw_spec)
    campaign_id = campaign_id or store.new_campaign_id()
    queued = store.load_state(campaign_id)
    if queued is not None and queued.get("spec_sha256") not in (None, spec_digest(spec)):
        raise CampaignSpecError("the specification changed after it was queued")
    if queued is not None and queued.get("status") == "cancelled":
        return queued
    lock = threading.Lock()
    store.clear_cancel(campaign_id)
    state = _initial_state(campaign_id, spec, "running", (queued or {}).get("origin") or "cli") | {"started": store.now()}
    for kept in ("recoveries", "thread_id"):
        if (queued or {}).get(kept):
            state[kept] = queued[kept]
    store.save_state(campaign_id, state)
    store.save_spec(campaign_id, spec)

    def on_update(dataset: str, result: dict[str, Any]) -> None:
        with lock:
            state["datasets"][dataset] = _progress(result)
            store.save_state(campaign_id, state)

    try:
        with _beating(campaign_id):
            outcome = run_campaign(spec, execute, workers, on_update, seeds, attempts, lambda: store.cancel_requested(campaign_id))
        if outcome.get("cancelled"):
            with lock:
                state.update(status="cancelled", finished=store.now())
                store.save_state(campaign_id, state)
            return state
        analysis = analyze_campaign(spec, outcome)
        markdown, ledger = render_report(spec, outcome, analysis)
        issues = report_issues(markdown, ledger)
        scripts = {dataset: record["script"] for dataset, record in outcome["datasets"].items()}
        store.save_artifacts(campaign_id, markdown, ledger, analysis, scripts)
        status = "needs_review" if issues else "completed"
        run_id = _track(tracker, campaign_id, spec, outcome, analysis, markdown, ledger, status)
    except Exception as exc:
        logger.exception("campaign %s failed", campaign_id)
        with lock:
            state.update(status="failed", error=f"{type(exc).__name__}: {exc}", finished=store.now())
            store.save_state(campaign_id, state)
        return state
    with lock:
        state.update(
            status=status,
            finished=store.now(),
            issues=issues,
            verdicts=_verdicts(analysis),
            finished_datasets=len(outcome["datasets"]),
            failed_datasets=len(outcome["failed"]),
        )
        if tracker is not None:
            state["mlflow_run_id"] = run_id
        store.save_state(campaign_id, state)
    return state
