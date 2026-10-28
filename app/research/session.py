import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.campaign.protocol import ESTIMATORS
from app.campaign.runner import DEFAULT_WORKERS, run_campaign
from app.campaign.spec import validate_campaign
from app.campaign.tuning import TuningError, validate_tuning
from app.datasets import DATASETS, research_pool
from app.research import generate, protocol
from app.research.protocol import ALPHA, MIN_CONFIRM, MIN_EXPLORE, ExplorationView, ProtocolError, Registry

ROOT = Path(__file__).resolve().parents[2] / "reports" / "research"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
FILENAME = "session.json"
REPORT = "report.md"


@dataclass(frozen=True)
class SessionConfig:
    id: str
    models: list[str]
    pool: list[str] = field(default_factory=research_pool)
    explore: int = 6
    seed: int = 0
    tuning: int | None = None
    per_stage: int = 8
    effect: float = generate.DEFAULT_EFFECT
    consistency: float = generate.DEFAULT_CONSISTENCY
    tuning_trigger: float = generate.TUNING_TRIGGER
    alpha: float = ALPHA

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.id):
            raise ProtocolError(f"the session id {self.id!r} is not valid")
        if len(self.models) < 2 or len(set(self.models)) != len(self.models):
            raise ProtocolError("a session needs at least two different models")
        unknown = [model for model in self.models if model not in ESTIMATORS]
        if unknown:
            raise ProtocolError("unknown models: " + ", ".join(unknown))
        unknown = [key for key in self.pool if key not in DATASETS]
        if unknown:
            raise ProtocolError("unknown datasets: " + ", ".join(unknown))
        if self.tuning is not None:
            try:
                validate_tuning({"iterations": self.tuning}, list(self.models))
            except TuningError as exc:
                raise ProtocolError(f"tuning: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def session_dir(session_id: str) -> Path:
    if not _ID.fullmatch(session_id):
        raise ProtocolError(f"the session id {session_id!r} is not valid")
    return ROOT / session_id


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def save(state: dict[str, Any]) -> None:
    _write(session_dir(state["id"]) / FILENAME, json.dumps(state, ensure_ascii=False, indent=1))


def load(session_id: str) -> dict[str, Any] | None:
    path = session_dir(session_id) / FILENAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_sessions() -> list[str]:
    if not ROOT.exists():
        return []
    return sorted(path.parent.name for path in ROOT.glob(f"*/{FILENAME}"))


def verify(session_id: str) -> bool:
    state = load(session_id)
    if state is None:
        raise ProtocolError(f"session {session_id} was not found")
    Registry.restore(state["budget"], state["hypotheses"])
    return True


def known_claims(exclude: str | None = None) -> frozenset[tuple[tuple[str, ...], tuple[str, ...]]]:
    found: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for name in list_sessions():
        if name == exclude:
            continue
        state = load(name)
        if not state or state.get("status") != "completed":
            continue
        confirmed = {item["id"] for item in state.get("confirmations", []) if item["status"] == "confirmed"}
        for item in state["hypotheses"]:
            if item["id"] in confirmed:
                found.add((tuple(item["subject"]), tuple(item["other"])))
    return frozenset(found)


def stage_spec(models: list[str], datasets: list[str], tuning: int | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Research session stage",
        "models": list(models),
        "params": {},
        "claims": [{"statement": f"{models[0]} beats {models[1]}", "metric": "roc_auc", "subject": [models[0]], "other": [models[1]]}],
        "datasets": list(datasets),
        "source": {},
    }
    if tuning:
        base["tuning"] = {"iterations": tuning}
    return validate_campaign(base)


def _finish(state: dict[str, Any], status: str, reason: str = "") -> dict[str, Any]:
    state["status"] = status
    state["reason"] = reason
    state["finished"] = _now()
    save(state)
    _write(session_dir(state["id"]) / REPORT, render_report(state))
    return state


def run_session(
    config: SessionConfig,
    execute: Callable[[str, str], str] | None = None,
    workers: int = DEFAULT_WORKERS,
    runner: Callable[..., dict[str, Any]] = run_campaign,
) -> dict[str, Any]:
    if (session_dir(config.id) / FILENAME).exists():
        raise ProtocolError(f"the session {config.id} exists already")
    explore, confirm = protocol.split_pool(list(config.pool), config.explore, config.seed)
    registry = Registry(protocol.max_hypotheses(len(confirm), config.alpha))
    state: dict[str, Any] = {
        "id": config.id,
        "config": config.to_dict(),
        "status": "running",
        "reason": "",
        "created": _now(),
        "explore": explore,
        "confirm": confirm,
        "budget": registry.budget,
        "alpha": config.alpha,
        "stages": [],
        "hypotheses": [],
        "skipped": [],
    }
    save(state)
    known = known_claims()
    sealed: dict[str, dict[str, Any]] = {}
    stage = "default"
    try:
        while True:
            outcome = runner(stage_spec(config.models, config.pool, config.tuning if stage == "tuned" else None), execute, workers)
            results = {key: record["summary"] for key, record in outcome["datasets"].items()}
            explored = [key for key in explore if key in results]
            confirmed = [key for key in confirm if key in results]
            state["stages"].append({"name": stage, "finished": [key for key in config.pool if key in results], "failed": dict(outcome.get("failed") or {})})
            if len(explored) < MIN_EXPLORE:
                return _finish(state, "aborted", f"only {len(explored)} of {len(explore)} exploration datasets finished in the {stage} stage")
            if len(confirmed) < MIN_CONFIRM:
                return _finish(state, "aborted", f"only {len(confirmed)} of {len(confirm)} confirmation datasets finished in the {stage} stage")
            allowed = protocol.max_hypotheses(len(confirmed), config.alpha)
            if registry.budget > allowed:
                registry.budget = max(allowed, len(registry.records))
                state["budget"] = registry.budget
            sealed[stage] = {key: results[key] for key in confirmed}
            view = ExplorationView(results, explored)
            proposals, skipped = generate.propose(view, registry, stage, config.per_stage, config.effect, config.consistency, known)
            for item in proposals:
                registry.register(item)
            state["hypotheses"] = registry.records
            state["skipped"].extend({"stage": stage, **entry} for entry in skipped)
            save(state)
            if stage == "default" and config.tuning and generate.needs_tuning(proposals, config.tuning_trigger):
                stage = "tuned"
                continue
            break
        state["confirmations"] = protocol.confirm(registry, sealed)
    except Exception as exc:
        return _finish(state, "failed", f"{type(exc).__name__}: {exc}")
    return _finish(state, "completed")


def _format(value: float | None, digits: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_report(state: dict[str, Any]) -> str:
    confirmations = {item["id"]: item for item in state.get("confirmations", [])}
    counts = {name: sum(1 for item in confirmations.values() if item["status"] == name) for name in protocol.STATUSES}
    lines = [
        f"# Research session {state['id']}",
        "",
        f"Status: {state['status']}" + (f" ({state['reason']})" if state.get("reason") else ""),
        "",
        "## Protocol",
        "",
        f"The pool of {len(state['explore']) + len(state['confirm'])} datasets was split once and for good into {len(state['explore'])} exploration datasets and {len(state['confirm'])} confirmation datasets "
        "(seeded, deterministic). The hypothesis generator saw only the exploration datasets; the confirmation results stayed sealed until every hypothesis was registered and saved. "
        "Each registered hypothesis was tested exactly once on the confirmation datasets (two-sided Wilcoxon over datasets, one primary metric, ROC-AUC). "
        f"All registered hypotheses of the session share one Holm correction (family-wise error) and a Benjamini-Hochberg q value; a hypothesis counts as confirmed only when its Holm adjusted p is below {state['alpha']} and the confirmation effect has the registered direction. "
        f"The confirmation set allows at most {state['budget']} hypotheses to be significant at all.",
        "",
        f"Exploration datasets: {', '.join(state['explore'])}.",
        f"Confirmation datasets: {', '.join(state['confirm'])}.",
        "",
        "## Result",
        "",
        f"{len(state['hypotheses'])} registered, {counts['confirmed']} confirmed, {counts['reversed']} reversed, {counts['not_confirmed']} not confirmed, {counts['not_testable']} not testable.",
        "",
    ]
    if state["hypotheses"]:
        lines += [
            "| id | stage | claim | exploration estimate (median diff, wins) | confirmation effect (median diff, wins) | p | adjusted p (Holm) | q (BH) | status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in state["hypotheses"]:
            outcome = confirmations.get(item["id"])
            evidence = item["evidence"]
            exploration = f"{_format(evidence['median_difference'])}, {evidence['wins']}/{evidence['datasets']}"
            if outcome:
                confirmation = f"{_format(outcome['median_difference'])}, {outcome['wins']}/{outcome['datasets']}"
                cells = [_format(outcome["p_value"], 5), _format(outcome["adjusted_p_value"], 5), _format(outcome["q_value"], 5), outcome["status"]]
            else:
                confirmation, cells = "not run", ["n/a", "n/a", "n/a", "not run"]
            lines.append(f"| {item['id']} | {item['stage']} | {item['statement']} | {exploration} | {confirmation} | {' | '.join(cells)} |")
        lines += [
            "",
            "The exploration estimate is inflated by selection (the hypothesis was chosen because it looked strong there); only the confirmation effect is an unbiased estimate.",
            "",
        ]
    if state.get("skipped"):
        lines += ["## Skipped proposals", ""]
        lines += [f"- {entry['statement']}: {entry['reason']}" for entry in state["skipped"]]
        lines.append("")
    lines += [
        "## Limits",
        "",
        "- Hypotheses are limited to model comparisons and tuning effects on binary classification of tabular data.",
        "- The datasets come from one benchmark; the exploration set is small, so the generator sees a noisy picture.",
        "- The hypothesis generator is rule based. The protocol would stay valid with any generator that only reads the exploration datasets.",
        "- This is exploratory analysis with statistical safeguards, not a new scientific discovery.",
        "",
    ]
    return "\n".join(lines)
