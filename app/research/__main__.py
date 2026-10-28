import argparse
import sys
import uuid
from typing import Any, Callable

from app.campaign.runner import DEFAULT_WORKERS, run_campaign
from app.research import generate, session
from app.research.protocol import ALPHA, ProtocolError

EXIT_OK = 0
EXIT_UNFINISHED = 1
EXIT_USAGE = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.research", description="Run a research session with sealed confirmation datasets.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a session")
    run.add_argument("--models", required=True, help="comma separated model keys")
    run.add_argument("--id", help="session id; a new one is generated when omitted")
    run.add_argument("--pool", help="comma separated dataset keys; default: the sixteen numeric benchmark datasets")
    run.add_argument("--explore", type=int, default=6, help="number of exploration datasets")
    run.add_argument("--seed", type=int, default=0, help="seed of the exploration and confirmation split")
    run.add_argument("--tuning", type=int, help="configurations per dataset of the tuned stage; the tuned stage is off without it")
    run.add_argument("--per-stage", type=int, default=8, help="most hypotheses registered in one stage")
    run.add_argument("--effect", type=float, default=generate.DEFAULT_EFFECT, help="smallest exploration effect worth a hypothesis")
    run.add_argument("--consistency", type=float, default=generate.DEFAULT_CONSISTENCY, help="share of exploration datasets that must agree")
    run.add_argument("--tuning-trigger", type=float, default=generate.TUNING_TRIGGER, help="exploration effect that asks for the tuned stage")
    run.add_argument("--alpha", type=float, default=ALPHA)
    run.add_argument("--generator", choices=session.GENERATORS, default="rules", help="who proposes the hypotheses from the exploration results")
    run.add_argument("--llm-model", default="gpt-4o", help="model used by the llm generator")
    run.add_argument("--no-history", action="store_true", help="do not skip claims that earlier sessions already confirmed")
    run.add_argument("--reuse", help="reuse the stage results of this earlier session instead of running the experiments again")
    run.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    commands.add_parser("list", help="list the sessions")
    show = commands.add_parser("show", help="print the report of a session")
    show.add_argument("id")
    verify = commands.add_parser("verify", help="check that the registered hypotheses of a session were not changed")
    verify.add_argument("id")
    return parser


def _summary(state: dict[str, Any]) -> list[str]:
    confirmations = state.get("confirmations", [])
    counts = {name: sum(1 for item in confirmations if item["status"] == name) for name in ("confirmed", "reversed", "not_confirmed", "not_testable")}
    lines = [f"session {state['id']}: {state['status']}" + (f" ({state['reason']})" if state.get("reason") else "")]
    lines.append(
        f"{len(state['hypotheses'])} registered, {counts['confirmed']} confirmed, {counts['reversed']} reversed, "
        f"{counts['not_confirmed']} not confirmed, {counts['not_testable']} not testable"
    )
    lines.append(f"report: {session.session_dir(state['id']) / session.REPORT}")
    return lines


def main(
    argv: list[str] | None = None,
    execute: Callable[[str, str], str] | None = None,
    runner: Callable[..., dict[str, Any]] = run_campaign,
    out=None,
) -> int:
    out = out or sys.stdout
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "list":
            for name in session.list_sessions():
                print(f"{name} {(session.load(name) or {}).get('status', '?')}", file=out)
            return EXIT_OK
        if arguments.command == "show":
            path = session.session_dir(arguments.id) / session.REPORT
            if not path.exists():
                print(f"session {arguments.id} has no report", file=out)
                return EXIT_USAGE
            print(path.read_text(encoding="utf-8"), file=out)
            return EXIT_OK
        if arguments.command == "verify":
            if session.load(arguments.id) is None:
                print(f"session {arguments.id} was not found", file=out)
                return EXIT_USAGE
            try:
                session.verify(arguments.id)
            except ProtocolError as exc:
                print(str(exc), file=out)
                return EXIT_UNFINISHED
            print(f"session {arguments.id}: the registered hypotheses are intact", file=out)
            return EXIT_OK
        pool = {"pool": arguments.pool.split(",")} if arguments.pool else {}
        config = session.SessionConfig(
            id=arguments.id or f"r-{uuid.uuid4().hex[:8]}",
            models=arguments.models.split(","),
            explore=arguments.explore,
            seed=arguments.seed,
            tuning=arguments.tuning,
            per_stage=arguments.per_stage,
            effect=arguments.effect,
            consistency=arguments.consistency,
            tuning_trigger=arguments.tuning_trigger,
            alpha=arguments.alpha,
            generator=arguments.generator,
            llm_model=arguments.llm_model,
            reuse=arguments.reuse,
            use_history=not arguments.no_history,
            **pool,
        )
        state = session.run_session(config, execute, arguments.workers, runner)
    except ProtocolError as exc:
        print(f"invalid session: {exc}", file=out)
        return EXIT_USAGE
    print("\n".join(_summary(state)), file=out)
    return EXIT_OK if state["status"] == "completed" else EXIT_UNFINISHED


if __name__ == "__main__":
    raise SystemExit(main())
