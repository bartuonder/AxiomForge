import re
from typing import Any

from app.agents.spec import MODEL_PARAMS, is_default
from app.campaign.protocol import ESTIMATORS, MIN_CAMPAIGN_MODELS
from app.campaign.stats import METRICS
from app.campaign.tuning import TuningError, validate_tuning
from app.datasets import DATASETS, benchmark_keys

MAX_STATEMENT = 500
MAX_TITLE = 160
MAX_NOTE = 300
MAX_NOTES = 12
MIN_CAMPAIGN_DATASETS = 2
_CLAIM_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,23}")


class CampaignSpecError(ValueError):
    pass


def _text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CampaignSpecError(f"{name} is missing")
    text = " ".join(value.split())
    if len(text) > limit:
        raise CampaignSpecError(f"{name} is longer than {limit} characters")
    return text


def _statement(value: Any, identifier: str) -> str:
    text = _text(value, f"claim {identifier} statement", MAX_STATEMENT).rstrip(". ")
    if not text:
        raise CampaignSpecError(f"claim {identifier} statement is missing")
    return text


def _models(raw: Any) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise CampaignSpecError("models must be a list of model names")
    if len(set(raw)) != len(raw):
        raise CampaignSpecError("models must not repeat")
    unknown = [item for item in raw if item not in ESTIMATORS]
    if unknown:
        raise CampaignSpecError("unknown models: " + ", ".join(unknown))
    if len(raw) < MIN_CAMPAIGN_MODELS:
        raise CampaignSpecError("a campaign needs at least two models")
    return list(raw)


def _params(raw: Any, models: list[str]) -> dict[str, dict[str, Any]]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise CampaignSpecError("params must be an object keyed by model name")
    cleaned: dict[str, dict[str, Any]] = {}
    for model, values in raw.items():
        if model not in models:
            raise CampaignSpecError(f"params names {model}, which the campaign does not run")
        if not isinstance(values, dict):
            raise CampaignSpecError(f"params for {model} must be an object")
        allowed = MODEL_PARAMS.get(model, ())
        kept: dict[str, Any] = {}
        for name, value in values.items():
            if name not in allowed:
                raise CampaignSpecError(f"{model} does not allow parameter {name}; allowed: {', '.join(allowed) or 'none'}")
            if isinstance(value, bool) or not (value is None or isinstance(value, (int, float, str))):
                raise CampaignSpecError(f"{model}.{name} must be a number, a string or null")
            if is_default(model, name, value):
                raise CampaignSpecError(f"{model}.{name}={value!r} is already the library default, so it is not a tuning")
            kept[name] = value
        if kept:
            cleaned[model] = kept
    return cleaned


def _datasets(raw: Any) -> list[str]:
    if raw is None:
        return benchmark_keys()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise CampaignSpecError("datasets must be a list of dataset keys")
    if len(set(raw)) != len(raw):
        raise CampaignSpecError("datasets must not repeat")
    unknown = [item for item in raw if item not in DATASETS]
    if unknown:
        raise CampaignSpecError("unknown datasets: " + ", ".join(unknown))
    if len(raw) < MIN_CAMPAIGN_DATASETS:
        raise CampaignSpecError("a campaign needs at least two datasets")
    return list(raw)


def _group(raw: Any, name: str, models: list[str]) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        raise CampaignSpecError(f"claim {name} must be a model name or a list of model names")
    outside = [item for item in raw if item not in models]
    if outside:
        raise CampaignSpecError(f"claim {name} names models the campaign does not run: " + ", ".join(outside))
    return list(dict.fromkeys(raw))


def _claims(raw: Any, models: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise CampaignSpecError("a campaign needs at least one claim")
    claims: list[dict[str, Any]] = []
    for position, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise CampaignSpecError("each claim must be an object")
        identifier = str(item.get("id") or f"C{position}")
        if not _CLAIM_ID.fullmatch(identifier):
            raise CampaignSpecError(f"claim id {identifier!r} is not valid")
        metrics = item.get("metrics") or [item.get("metric")]
        if not isinstance(metrics, list) or not metrics or any(metric not in METRICS for metric in metrics):
            raise CampaignSpecError(f"claim {identifier} metrics must come from " + ", ".join(METRICS))
        subject = _group(item.get("subject"), "subject", models)
        other = _group(item.get("other"), "other", models)
        if set(subject) & set(other):
            raise CampaignSpecError(f"claim {identifier} compares a model with itself")
        claim = {
            "id": identifier,
            "statement": _statement(item.get("statement"), identifier),
            "metric": metrics[0],
            "metrics": list(dict.fromkeys(metrics)),
            "subject": subject,
            "other": other,
        }
        if isinstance(item.get("quote"), str) and item["quote"].strip():
            claim["quote"] = _text(item["quote"], f"claim {identifier} quote", MAX_STATEMENT)
        claims.append(claim)
    if len({claim["id"] for claim in claims}) != len(claims):
        raise CampaignSpecError("claim ids must be unique")
    return claims


def _source(raw: Any) -> dict[str, Any]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise CampaignSpecError("source must be an object")
    source: dict[str, Any] = {}
    for name in ("title", "citation", "url"):
        if raw.get(name):
            source[name] = _text(raw[name], f"source {name}", MAX_STATEMENT)
    notes = raw.get("deviations") or []
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        raise CampaignSpecError(f"source deviations must be a list of at most {MAX_NOTES} notes")
    if notes:
        source["deviations"] = [_text(note, "a deviation note", MAX_NOTE) for note in notes]
    return source


_REVISION = re.compile(r"[0-9a-f]{40}")


def _revisions(raw: Any, datasets: list[str]) -> dict[str, str]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise CampaignSpecError("revisions must be an object that maps dataset keys to commit hashes")
    revisions: dict[str, str] = {}
    for key, value in raw.items():
        if key not in datasets:
            raise CampaignSpecError(f"revision given for {key}, which is not a dataset of the campaign")
        text = value.lower() if isinstance(value, str) else ""
        if not _REVISION.fullmatch(text):
            raise CampaignSpecError(f"the revision of {key} must be a 40 character commit hash")
        revisions[key] = text
    return revisions


def validate_campaign(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CampaignSpecError("a campaign must be a JSON object")
    models = _models(raw.get("models"))
    params = _params(raw.get("params"), models)
    try:
        tuning = validate_tuning(raw.get("tuning"), models)
    except TuningError as exc:
        raise CampaignSpecError(str(exc)) from exc
    if tuning and params:
        raise CampaignSpecError("tuning and listed parameters cannot be combined")
    datasets = _datasets(raw.get("datasets"))
    spec = {
        "title": _text(raw.get("title"), "title", MAX_TITLE),
        "models": models,
        "params": params,
        "tuning": tuning,
        "datasets": datasets,
        "claims": _claims(raw.get("claims"), models),
        "source": _source(raw.get("source")),
    }
    revisions = _revisions(raw.get("revisions"), datasets)
    if revisions:
        spec["revisions"] = revisions
    return spec
