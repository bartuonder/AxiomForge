import copy
import json
import logging
from typing import Any

from openai import OpenAI

from app.campaign.memory import find_repeats
from app.campaign.planning import POOLS, PlanningError, assemble_spec, estimate_cost, map_models, tuning_note
from app.campaign.protocol import ESTIMATORS
from app.campaign.spec import CampaignSpecError, validate_campaign
from app.campaign.stats import METRICS
from app.campaign.tuning import DEFAULT_FOLDS, DEFAULT_ITERATIONS
from app.config import OPENAI_API_KEY

logger = logging.getLogger("axiomforge")

MODEL = "gpt-4o"
CANDIDATES = 3
MAX_PLAN_ATTEMPTS = 3
MIN_QUOTE_CHARS = 20
MAX_CLAIMS = 2
QUOTE_EDGES = " \t\n\"'“”‘’.,;:!?…"
SHAPE_ERROR = "the answer must be a JSON object with a candidates list; use unsupported only together with an empty candidates list"

SYSTEM_PROMPT = (
    "You are a replication planner. You read paper abstracts and a user query and turn their comparison claims "
    "into replication campaigns. A campaign trains the same models on 5 to 10 binary classification datasets of tabular data "
    "and tests the claim across datasets. "
    f"Propose exactly {CANDIDATES} different candidate campaigns. "
    "If the sources and the query allow fewer than three different claims, vary the model groups, the metrics or the comparison "
    "(for example all three metrics, ROC-AUC only, or a second comparison against another model family). "
    "Each candidate is a JSON object with: "
    "title (a short name), "
    "source_index (the number of the source paper the claims come from, or 0 when the claims come from the user query itself), "
    "pool (benchmark for the nine tabular benchmark datasets, or all for the benchmark plus the core datasets), "
    "tuned (true only when the user asks for tuned models or the source tuned its models; tuning every model by random search makes the run several times slower; otherwise false), "
    f"claims (at most {MAX_CLAIMS}), each with: statement (one sentence), "
    f"metrics (a list from: {', '.join(METRICS)}), "
    "subject (a list of model names that are claimed to score higher), "
    "other (a list of model names they are compared with), "
    "source_quote (an exact quote of at least 20 characters copied from the source abstract, the source conclusion or the user query that states or implies the claim). "
    "Use the model names as the source writes them; the system maps them to runnable estimators. "
    "Architectures that are not runnable, such as transformers, ResNet or other deep networks, are mapped to the MLP stand-in and noted as a deviation; "
    "propose the claim with the name as written and never answer unsupported because of an architecture that is not in the list. "
    "A negated statement such as 'X does not outperform Y' is not the claim that Y outperforms X: "
    "propose the affirmative claim 'X outperforms Y' so that the verdict can refute the statement, and never invert the direction. "
    f"Runnable estimators: {', '.join(sorted(ESTIMATORS))}. "
    "Never invent a claim that the sources and the query do not state. Candidates may differ in the claim, the model groups or the metrics. "
    "When the user query itself states a comparison claim, even one it attributes to a paper that is not among the sources, "
    "propose that claim with source_index 0 and quote the query; prefer a source paper only when its abstract states the claim. "
    "The system does not need the attributed paper: it tests the stated claim and will not credit it to any paper, "
    "so irrelevant sources are no reason to answer unsupported. "
    "Use unsupported only when neither the sources nor the query state any comparison between models on tabular classification. "
    "If the sources are not about comparing models on tabular classification, or contain no comparison claim, "
    "return an empty candidates list and explain why in unsupported. "
    "The key candidates is required in every answer; fill unsupported only when candidates is an empty list. "
    'Return only JSON: {"unsupported": "", "candidates": [{"title": "...", "source_index": 1, "pool": "benchmark", '
    '"claims": [{"statement": "...", "metrics": ["roc_auc"], "subject": ["..."], "other": ["..."], "source_quote": "..."}]}]}.'
)


JUDGE_PROMPT = (
    "You check whether a quote from a paper supports a comparison claim between model groups on tabular classification. "
    "You get a JSON object with claims; each has an id, a statement, subject models, other models and a quote. "
    "A quote supports the claim only when it states, or directly implies, that the subject models score higher or perform better than the other models. "
    "A quote that describes a related finding, such as tuning effort, speed, cost, robustness or a different pair of model families, does not support the claim. "
    "A quote that states the opposite direction does not support it. "
    "Answer for every id with a one-sentence reason. "
    'Return only JSON: {"verdicts": [{"id": 1, "supports": true, "reason": "..."}]}.'
)
MAX_REASON_CHARS = 200
FILL_VARIANTS = True
VARIANTS = (("ROC-AUC only", True, False), ("tuned", False, True))
NO_SEARCH_NOTE = "No hyperparameter search"


class CampaignUnsupported(RuntimeError):
    pass


def _normal(text: str) -> str:
    return " ".join(str(text).lower().split())


def _names(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise PlanningError(f"claim {label} must be a model name or a list of model names")
    return value


def _claim(raw: Any, origins: dict[str, str], mapped_notes: list[str], models: list[str]) -> tuple[dict[str, Any], str, str]:
    if not isinstance(raw, dict):
        raise PlanningError("each claim must be an object")
    quote = raw.get("source_quote")
    if isinstance(quote, str):
        quote = quote.strip(QUOTE_EDGES)
    if not isinstance(quote, str) or len(_normal(quote)) < MIN_QUOTE_CHARS:
        raise PlanningError(f"a claim needs a source_quote of at least {MIN_QUOTE_CHARS} characters")
    origin = next((name for name, text in origins.items() if _normal(quote) in text), None)
    if origin is None:
        raise PlanningError(f"the quote {quote[:60]!r} does not appear in the source text")
    groups: dict[str, list[str]] = {}
    for label in ("subject", "other"):
        mapped, notes, unmapped = map_models(_names(raw.get(label), label))
        if unmapped:
            raise PlanningError("these models cannot be run by the campaign engine: " + ", ".join(unmapped))
        groups[label] = mapped
        for name in mapped:
            if name not in models:
                models.append(name)
        for note in notes:
            if note not in mapped_notes:
                mapped_notes.append(note)
    metrics = raw.get("metrics")
    claim = {"statement": raw.get("statement"), "metrics": metrics, "subject": groups["subject"], "other": groups["other"]}
    return claim, quote.strip(), origin


def _candidate(raw: Any, query: str, sources: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PlanningError("each candidate must be an object")
    index = raw.get("source_index")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= len(sources):
        raise PlanningError(f"source_index must be a whole number from 0 to {len(sources)}")
    origins: dict[str, str] = {}
    source: dict[str, str] = {}
    if index > 0:
        paper = sources[index - 1]
        origins["source"] = _normal(f"{paper['title']} {paper['abstract']} {paper.get('passages', '')}")
        source = {"title": paper["title"], **{name: paper[name] for name in ("url", "citation") if paper.get(name)}}
    origins["query"] = _normal(query)
    raw_claims = raw.get("claims")
    if not isinstance(raw_claims, list) or not 1 <= len(raw_claims) <= MAX_CLAIMS:
        raise PlanningError(f"a candidate needs one to {MAX_CLAIMS} claims")
    pool = raw.get("pool") or "benchmark"
    if pool not in POOLS:
        raise PlanningError(f"pool must be one of: {', '.join(POOLS)}")
    tuned = raw.get("tuned", False)
    if not isinstance(tuned, bool):
        raise PlanningError("tuned must be true or false")
    tuning = {"iterations": DEFAULT_ITERATIONS, "folds": DEFAULT_FOLDS} if tuned else None
    models: list[str] = []
    notes: list[str] = []
    claims: list[dict[str, Any]] = []
    quotes: list[str] = []
    found: list[str] = []
    for item in raw_claims:
        claim, quote, origin = _claim(item, origins, notes, models)
        claims.append(claim)
        quotes.append(quote)
        found.append(origin)
    if len(set(found)) > 1:
        raise PlanningError("the claims of one candidate must all be quoted from the same origin, the source paper or the user query")
    if found[0] == "query":
        source = {}
    else:
        for item, quote in zip(claims, quotes):
            item["quote"] = quote
    spec = assemble_spec(str(raw.get("title") or "").strip(), models, claims, source, pool=pool, mapped_notes=notes, tuning=tuning)
    if found[0] == "source":
        issues = _support_issues(spec["claims"], raw_claims, quotes)
        if issues:
            raise PlanningError("; ".join(issues))
    evidence = [
        {"claim": claim["id"], "quote": quote, "source": source.get("title", "user query")}
        for claim, quote in zip(spec["claims"], quotes)
    ]
    return {"spec": spec, "estimate": estimate_cost(spec), "evidence": evidence}


def _judge_complete(user: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": user}],
    )
    return response.choices[0].message.content or ""


def _support_issues(spec_claims: list[dict[str, Any]], raw_claims: list[dict[str, Any]], quotes: list[str]) -> list[str]:
    items = [
        {
            "id": number,
            "statement": claim["statement"],
            "subject": _names(raw.get("subject"), "subject"),
            "other": _names(raw.get("other"), "other"),
            "quote": quote,
        }
        for number, (claim, raw, quote) in enumerate(zip(spec_claims, raw_claims, quotes), start=1)
    ]
    try:
        payload = json.loads(_judge_complete(json.dumps({"claims": items}, ensure_ascii=False)))
    except json.JSONDecodeError as exc:
        raise RuntimeError("campaign support judge returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("verdicts"), list) or not all(isinstance(item, dict) for item in payload["verdicts"]):
        raise RuntimeError("campaign support judge returned an unusable answer")
    by_id = {item.get("id"): item for item in payload["verdicts"]}
    issues = []
    for number, claim in enumerate(spec_claims, start=1):
        verdict = by_id.get(number)
        if verdict is None:
            issues.append(f"claim {claim['id']}: the judge returned no verdict")
        elif verdict.get("supports") is not True:
            reason = str(verdict.get("reason") or "no reason given")[:MAX_REASON_CHARS]
            issues.append(f"claim {claim['id']}: the source quote does not support the claim ({reason})")
    return issues


def _complete(user: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
    )
    return response.choices[0].message.content or ""


def _signature(candidate: dict[str, Any]) -> tuple:
    claims = tuple(
        (claim["statement"], tuple(claim["metrics"]), tuple(claim["subject"]), tuple(claim["other"]))
        for claim in candidate["spec"]["claims"]
    )
    return claims + (tuple(sorted((candidate["spec"].get("tuning") or {}).items())),)


def _variant(base: dict[str, Any], label: str, single_metric: bool, tuned: bool) -> dict[str, Any]:
    spec = copy.deepcopy(base["spec"])
    spec["title"] = f"{spec['title']} ({label})"
    if single_metric:
        for claim in spec["claims"]:
            claim["metrics"], claim["metric"] = ["roc_auc"], "roc_auc"
    if tuned:
        spec["tuning"] = {"iterations": DEFAULT_ITERATIONS, "folds": DEFAULT_FOLDS}
        note = tuning_note(spec["tuning"])
        source = spec.setdefault("source", {})
        source["deviations"] = [note if str(item).startswith(NO_SEARCH_NOTE) else item for item in source.get("deviations") or []]
    spec = validate_campaign(spec)
    return {"spec": spec, "estimate": estimate_cost(spec), "evidence": copy.deepcopy(base["evidence"])}


def _fill(valid: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {_signature(item) for item in valid}
    filled = list(valid)
    for base in valid:
        for label, single_metric, tuned in VARIANTS:
            if len(filled) >= CANDIDATES:
                return filled
            try:
                variant = _variant(base, label, single_metric, tuned)
            except (PlanningError, CampaignSpecError) as exc:
                logger.info("campaign planner could not vary %s: %s", base["spec"]["title"], exc)
                continue
            if _signature(variant) in seen:
                continue
            seen.add(_signature(variant))
            filled.append(variant)
    return filled


def _past_listing(past: list[dict[str, Any]]) -> str:
    lines = []
    for item in past:
        claims = "; ".join(str(claim.get("statement", "")) for claim in item["spec"].get("claims") or [])
        lines.append(f"- {item['title']}: {claims} ({item['verdicts']})")
    return "\n".join(lines)


def run_campaign_planner(query: str, sources: list[dict[str, str]], past: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    listing = "\n\n".join(
        f"[{number}] {paper['title']}: {paper['abstract']}" + (f"\nConclusion: {paper['passages']}" if paper.get("passages") else "")
        for number, paper in enumerate(sources, start=1)
    )
    prompt = f"User query:\n{query}\n\nSources:\n{listing or 'No source paper was found.'}"
    if past:
        prompt += (
            "\n\nCampaigns that were already run on similar questions. "
            "Do not propose the same claim again unless the user query asks to repeat it:\n" + _past_listing(past)
        )
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    refusal = ""
    for attempt in range(MAX_PLAN_ATTEMPTS):
        feedback = "" if not errors else "\n\nThese candidates of your previous answer were rejected, propose replacements:\n- " + "\n- ".join(errors)
        content = _complete(prompt + feedback)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("campaign planner returned invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
            errors = [SHAPE_ERROR]
            reason = payload.get("unsupported") if isinstance(payload, dict) else None
            refusal = reason.strip() if isinstance(reason, str) else ""
            continue
        if not payload["candidates"]:
            reason = payload.get("unsupported")
            raise CampaignUnsupported(str(reason).strip() if isinstance(reason, str) and reason.strip() else "the sources contain no claim a campaign can test")
        errors = []
        for number, raw in enumerate(payload["candidates"][:CANDIDATES], start=1):
            try:
                candidate = _candidate(raw, query, sources)
            except (PlanningError, CampaignSpecError) as exc:
                errors.append(f"candidate {number}: {exc}")
                logger.info("campaign planner rejected candidate %s: %s", number, exc)
                continue
            if _signature(candidate) not in {_signature(item) for item in valid}:
                valid.append(candidate)
        if len(valid) >= CANDIDATES or not errors:
            break
    if not valid:
        if errors == [SHAPE_ERROR]:
            if refusal:
                raise CampaignUnsupported(refusal)
            raise RuntimeError("campaign planner did not return candidates")
        raise RuntimeError("campaign planner returned no valid campaign: " + "; ".join(errors))
    chosen = (_fill(valid) if FILL_VARIANTS else valid)[:CANDIDATES]
    for item in chosen:
        item["repeats"] = find_repeats(item["spec"], past or [])
    return chosen
