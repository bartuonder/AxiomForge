import logging
import threading
from typing import Any, Callable

from app.campaign import store
from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report, report_issues
from app.campaign.runner import DEFAULT_WORKERS, MAX_ATTEMPTS, run_campaign
from app.campaign.spec import validate_campaign
from app.sandbox.e2b_runner import run_classification
from app.seeds import SPLIT_SEEDS

logger = logging.getLogger("axiomforge")

PROGRESS_FIELDS = ("status", "attempts", "seconds", "error")


def _progress(result: dict[str, Any]) -> dict[str, Any]:
    return {name: result[name] for name in PROGRESS_FIELDS if name in result}


def _verdicts(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": claim["id"], "statement": claim["statement"], "verdict": claim["verdict"]} for claim in analysis.get("claims", [])]


def _initial_state(campaign_id: str, spec: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "id": campaign_id,
        "title": spec["title"],
        "status": status,
        "datasets": {dataset: {"status": "queued"} for dataset in spec["datasets"]},
    }


def campaign_summary(state: dict[str, Any]) -> dict[str, Any]:
    statuses = [item.get("status") for item in state.get("datasets", {}).values()]
    return {
        "id": state["id"],
        "title": state.get("title", ""),
        "status": state["status"],
        "updated": state.get("updated", ""),
        "datasets": len(statuses),
        "finished": statuses.count("finished"),
        "failed": statuses.count("failed"),
        "verdicts": [{"id": item["id"], "verdict": item["verdict"]} for item in state.get("verdicts", [])],
    }


def queue_campaign(raw_spec: Any) -> tuple[str, dict[str, Any]]:
    spec = validate_campaign(raw_spec)
    campaign_id = store.new_campaign_id()
    store.save_state(campaign_id, _initial_state(campaign_id, spec, "queued") | {"queued": store.now()})
    return campaign_id, spec


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
    execute: Callable[[str, str], str] = run_classification,
    workers: int = DEFAULT_WORKERS,
    seeds: tuple[int, ...] = SPLIT_SEEDS,
    attempts: int = MAX_ATTEMPTS,
    tracker: Callable[..., str] | None = None,
) -> dict[str, Any]:
    spec = validate_campaign(raw_spec)
    campaign_id = campaign_id or store.new_campaign_id()
    lock = threading.Lock()
    state = _initial_state(campaign_id, spec, "running") | {"started": store.now()}
    store.save_state(campaign_id, state)

    def on_update(dataset: str, result: dict[str, Any]) -> None:
        with lock:
            state["datasets"][dataset] = _progress(result)
            store.save_state(campaign_id, state)

    try:
        outcome = run_campaign(spec, execute, workers, on_update, seeds, attempts)
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
