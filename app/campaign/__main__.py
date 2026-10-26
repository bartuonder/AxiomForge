import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from app.campaign import store
from app.campaign.demos import demo_names, demo_spec
from app.campaign.planning import tuning_note
from app.campaign.runner import DEFAULT_WORKERS
from app.campaign.service import execute_campaign
from app.campaign.spec import CampaignSpecError
from app.campaign.tracking import log_campaign
from app.campaign.tuning import DEFAULT_FOLDS

EXIT_OK = 0
EXIT_UNFINISHED = 1
EXIT_USAGE = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.campaign", description="Replicate a published claim across datasets.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a campaign")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", help="a ready campaign: " + ", ".join(demo_names()))
    source.add_argument("--spec", help="path of a campaign specification in JSON")
    run.add_argument("--datasets", help="comma separated dataset keys that replace the specification's datasets")
    run.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="datasets run in parallel")
    run.add_argument("--id", help="campaign id; a new one is generated when omitted")
    run.add_argument("--mlflow", action="store_true", help="also record the campaign in MLflow")
    run.add_argument("--tuning", type=int, help="tune every model by random search with this many configurations per dataset")
    run.add_argument("--pin-from", help="pin the dataset revisions recorded by this stored campaign")
    commands.add_parser("list", help="list stored campaigns")
    commands.add_parser("demos", help="list the ready campaigns")
    show = commands.add_parser("show", help="print the report of a stored campaign")
    show.add_argument("id")
    return parser


def _load_spec(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.demo:
        spec = demo_spec(arguments.demo)
    else:
        try:
            spec = json.loads(Path(arguments.spec).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CampaignSpecError(f"cannot read {arguments.spec}: {exc}") from exc
    if arguments.datasets:
        spec["datasets"] = [key.strip() for key in arguments.datasets.split(",") if key.strip()]
    if arguments.tuning is not None:
        spec["tuning"] = {"iterations": arguments.tuning}
        source = spec.get("source")
        if isinstance(source, dict) and isinstance(source.get("deviations"), list):
            note = tuning_note({"iterations": arguments.tuning, "folds": DEFAULT_FOLDS})
            source["deviations"] = [note if str(item).startswith("No hyperparameter search") else item for item in source["deviations"]]
    if arguments.pin_from:
        spec["revisions"] = _pinned_revisions(arguments.pin_from, spec.get("datasets") or [])
    return spec


def _pinned_revisions(campaign_id: str, datasets: list[str]) -> dict[str, str]:
    ledger = store.load_ledger(campaign_id)
    if ledger is None:
        raise CampaignSpecError(f"campaign {campaign_id} has no ledger to pin the revisions from")
    revisions = {
        entry["key"]: entry["provenance"]["revision"]
        for entry in ledger
        if entry.get("kind") == "dataset" and entry["key"] in datasets and re.fullmatch(r"[0-9a-f]{40}", str((entry.get("provenance") or {}).get("revision", "")))
    }
    if not revisions:
        raise CampaignSpecError(f"campaign {campaign_id} has no revision for the datasets of this run")
    return revisions


def _describe(state: dict[str, Any]) -> list[str]:
    lines = [f"campaign {state['id']}: {state['status']}"]
    for key, item in state["datasets"].items():
        detail = f" ({item['error']})" if item.get("error") else ""
        lines.append(f"  {key}: {item['status']}{detail}")
    for verdict in state.get("verdicts", []):
        lines.append(f"  {verdict['id']} {verdict['verdict']}: {verdict['statement']}")
    for issue in state.get("issues", []):
        lines.append(f"  issue: {issue}")
    if state.get("error"):
        lines.append(f"  error: {state['error']}")
    if state.get("mlflow_run_id"):
        lines.append(f"mlflow run: {state['mlflow_run_id']}")
    if state["status"] in {"completed", "needs_review"}:
        lines.append(f"report: {store.campaign_dir(state['id']) / 'report.md'}")
    return lines


def main(argv: list[str] | None = None, execute: Callable[[str, str], str] | None = None, out=None) -> int:
    out = out or sys.stdout
    arguments = _parser().parse_args(argv)
    if arguments.command == "demos":
        print("\n".join(demo_names()), file=out)
        return EXIT_OK
    if arguments.command == "list":
        for campaign_id in store.list_campaigns():
            state = store.load_state(campaign_id) or {}
            print(f"{campaign_id} {state.get('status', '?')} {state.get('title', '')}", file=out)
        return EXIT_OK
    if arguments.command == "show":
        try:
            report = store.load_report(arguments.id)
        except store.CampaignStoreError as exc:
            print(str(exc), file=out)
            return EXIT_USAGE
        if report is None:
            print(f"campaign {arguments.id} has no report", file=out)
            return EXIT_USAGE
        print(report, file=out)
        return EXIT_OK
    try:
        tracker = log_campaign if arguments.mlflow else None
        state = execute_campaign(_load_spec(arguments), arguments.id, execute, arguments.workers, tracker=tracker)
    except (CampaignSpecError, store.CampaignStoreError) as exc:
        print(f"invalid campaign: {exc}", file=out)
        return EXIT_USAGE
    print("\n".join(_describe(state)), file=out)
    return EXIT_OK if state["status"] == "completed" else EXIT_UNFINISHED


if __name__ == "__main__":
    sys.exit(main())
