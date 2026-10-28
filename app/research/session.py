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
from app.research import generate, llm_generator, protocol
from app.research.protocol import ALPHA, MIN_CONFIRM, MIN_EXPLORE, ExplorationView, ProtocolError, Registry

ROOT = Path(__file__).resolve().parents[2] / "reports" / "research"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
FILENAME = "session.json"
GENERATORS = ("rules", "llm")
STAGES = ("default", "tuned")
STAGE_DIR = "stages"
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
    generator: str = "rules"
    llm_model: str = "gpt-4o"
    reuse: str | None = None
    use_history: bool = True

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.id):
            raise ProtocolError(f"the session id {self.id!r} is not valid")
        if self.reuse is not None and not _ID.fullmatch(self.reuse):
            raise ProtocolError(f"the session id {self.reuse!r} is not valid")
        if self.generator not in GENERATORS:
            raise ProtocolError(f"the generator must be one of: {', '.join(GENERATORS)}")
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


def _blank_state(config: SessionConfig, status: str) -> dict[str, Any]:
    explore, confirm = protocol.split_pool(list(config.pool), config.explore, config.seed)
    return {
        "id": config.id,
        "config": config.to_dict(),
        "status": status,
        "reason": "",
        "phase": "",
        "created": _now(),
        "explore": explore,
        "confirm": confirm,
        "budget": protocol.max_hypotheses(len(confirm), config.alpha),
        "alpha": config.alpha,
        "generator": config.generator,
        "stages": [],
        "hypotheses": [],
        "skipped": [],
    }


def queue_session(config: SessionConfig) -> dict[str, Any]:
    if (session_dir(config.id) / FILENAME).exists():
        raise ProtocolError(f"the session {config.id} exists already")
    state = _blank_state(config, "queued")
    save(state)
    return state


def reset_for_retry(session_id: str) -> None:
    folder = session_dir(session_id)
    if not (folder / FILENAME).exists():
        raise ProtocolError(f"session {session_id} was not found")
    for name in (FILENAME, REPORT):
        path = folder / name
        if path.exists():
            path.unlink()


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
    state["phase"] = ""
    state["finished"] = _now()
    save(state)
    _write(session_dir(state["id"]) / REPORT, render_report(state))
    return state


def _stage_file(session_id: str, stage: str) -> Path:
    return session_dir(session_id) / STAGE_DIR / f"{stage}.json"


def _save_stage(config: SessionConfig, stage: str, results: dict[str, Any], failed: dict[str, Any]) -> None:
    payload = {
        "stage": stage,
        "models": list(config.models),
        "pool": list(config.pool),
        "tuning": config.tuning if stage == "tuned" else None,
        "results": results,
        "failed": failed,
    }
    _write(_stage_file(config.id, stage), json.dumps(payload, ensure_ascii=False))


def _load_reused(config: SessionConfig) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    if not config.reuse:
        return {}
    source = session_dir(config.reuse)
    reused: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for stage in STAGES:
        path = _stage_file(config.reuse, stage)
        if not path.exists():
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["models"] != list(config.models):
            raise ProtocolError(f"the models differ from session {config.reuse}")
        if saved["pool"] != list(config.pool):
            raise ProtocolError(f"the pool differs from session {config.reuse}")
        if stage == "tuned":
            if config.tuning is None:
                continue
            if saved["tuning"] != config.tuning:
                raise ProtocolError(f"the tuning differs from session {config.reuse}")
        reused[stage] = (saved["results"], saved["failed"])
    if "default" not in reused:
        raise ProtocolError(f"session {config.reuse} has nothing to reuse in {source}")
    return reused


def run_session(
    config: SessionConfig,
    execute: Callable[[str, str], str] | None = None,
    workers: int = DEFAULT_WORKERS,
    runner: Callable[..., dict[str, Any]] = run_campaign,
    generator: Callable[..., Any] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    existing = load(config.id)
    if existing is not None and existing.get("status") != "queued":
        raise ProtocolError(f"the session {config.id} exists already")
    reused = _load_reused(config)
    state = _blank_state(config, "running")
    if existing is not None:
        state["created"] = existing.get("created", state["created"])
    state["generator"] = config.generator if generator is None else "custom"
    explore, confirm = state["explore"], state["confirm"]
    registry = Registry(state["budget"])
    if should_stop and should_stop():
        return _finish(state, "cancelled", "stopped on request")
    save(state)
    known = known_claims() if config.use_history else frozenset()
    propose = generator or (generate.propose if config.generator == "rules" else llm_generator.make_generator(llm_generator.make_complete(config.llm_model)))
    sealed: dict[str, dict[str, Any]] = {}
    stage = "default"
    try:
        while True:
            try:
                if stage in reused:
                    results, failed = reused[stage]
                else:
                    state["phase"] = stage
                    save(state)
                    stage_arguments = (stage_spec(config.models, config.pool, config.tuning if stage == "tuned" else None), execute, workers)
                    outcome = runner(*stage_arguments, should_stop=should_stop) if should_stop else runner(*stage_arguments)
                    results = {key: record["summary"] for key, record in outcome["datasets"].items()}
                    failed = dict(outcome.get("failed") or {})
                _save_stage(config, stage, results, failed)
            except Exception as exc:
                if stage == "default":
                    raise
                state["stages"].append({"name": stage, "finished": [], "failed": {}, "error": f"{type(exc).__name__}: {exc}"})
                state["reason"] = f"the {stage} stage failed ({type(exc).__name__}: {exc}); only the earlier stages were tested"
                break
            if should_stop and should_stop():
                return _finish(state, "cancelled", "stopped on request")
            explored = [key for key in explore if key in results]
            confirmed = [key for key in confirm if key in results]
            state["stages"].append({"name": stage, "finished": [key for key in config.pool if key in results], "failed": failed})
            shortage = ""
            if len(explored) < MIN_EXPLORE:
                shortage = f"only {len(explored)} of {len(explore)} exploration datasets finished in the {stage} stage"
            elif len(confirmed) < MIN_CONFIRM:
                shortage = f"only {len(confirmed)} of {len(confirm)} confirmation datasets finished in the {stage} stage"
            if shortage and stage == "default":
                return _finish(state, "aborted", shortage)
            if shortage:
                state["reason"] = f"the {stage} stage was dropped: {shortage}; only the earlier stages were tested"
                break
            allowed = protocol.max_hypotheses(len(confirmed), config.alpha)
            if registry.budget > allowed:
                registry.budget = max(allowed, len(registry.records))
                state["budget"] = registry.budget
            sealed[stage] = {key: results[key] for key in confirmed}
            view = ExplorationView(results, explored)
            proposals, skipped = propose(view, registry, stage, config.per_stage, config.effect, config.consistency, known)
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
    return _finish(state, "completed", state["reason"])


def summary_of(state: dict[str, Any]) -> dict[str, Any]:
    confirmations = state.get("confirmations", [])
    return {
        "id": state["id"],
        "status": state["status"],
        "reason": state.get("reason", ""),
        "created": state.get("created", ""),
        "finished": state.get("finished", ""),
        "models": list(state["config"]["models"]),
        "explore": list(state["explore"]),
        "confirm": list(state["confirm"]),
        "budget": state["budget"],
        "registered": len(state["hypotheses"]),
        "counts": {name: sum(1 for item in confirmations if item["status"] == name) for name in protocol.STATUSES},
        "phase": state.get("phase", ""),
        "stages": [{"name": item["name"], "finished": len(item["finished"]), "failed": len(item["failed"])} for item in state.get("stages", [])],
    }


def _format(value: float | None, digits: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _reuse_note(state: dict[str, Any]) -> list[str]:
    source = state["config"].get("reuse")
    if not source:
        return []
    if source == state["id"]:
        return ["The stage results saved by an earlier attempt of this session were reused; no experiment was run again for them.", ""]
    return [f"The stage results were reused from session {source}; no experiment was run for them.", ""]


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
        f"Hypothesis generator: {state.get('generator', 'rules')}" + (f" ({state['config'].get('llm_model', '')})" if state.get("generator") == "llm" else "") + ".",
        "",
        *_reuse_note(state),
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
        "- The protocol would stay valid with any hypothesis generator that only reads the exploration datasets; this session used the generator named above.",
        "- This is exploratory analysis with statistical safeguards, not a new scientific discovery.",
        "",
    ]
    return "\n".join(lines)
