import json
from typing import Callable

from app.research import generate
from app.research.protocol import PRIMARY_METRIC, ExplorationView, Hypothesis, Registry

Known = frozenset[tuple[tuple[str, ...], tuple[str, ...]]] | set[tuple[tuple[str, ...], tuple[str, ...]]]


class GeneratorError(ValueError):
    pass


def prompt(view: ExplorationView, names: list[str], stage: str, count: int) -> str:
    rows = []
    for dataset in view.datasets:
        scores = ", ".join(f"{name}={float(view.per_dataset[dataset][name][f'{PRIMARY_METRIC}_mean']):.3f}" for name in names)
        rows.append(f"- {dataset}: {scores}")
    return (
        "You are a research agent that studies how machine learning models compare on tabular binary classification.\n"
        f"These are mean ROC-AUC scores on the exploration datasets, from the {stage} stage:\n" + "\n".join(rows) + "\n"
        f"Propose at most {count} hypotheses of the form \"the model you expect to score higher than the model you expect to score lower on ROC-AUC\". "
        "Use only the model names listed above. A name ending in __default is the same model with library default parameters (a control); "
        "compare it only with its own model, to ask whether tuning helped. "
        "Prefer hypotheses that the scores above make plausible, but you may also propose one that tests a common belief. "
        "A separate set of datasets that you cannot see will test each hypothesis once.\n"
        'Answer with JSON only: {"hypotheses": [{"higher": "model expected to score higher", "lower": "model expected to score lower", "rationale": "one short sentence"}]}'
    )


def parse(text: str) -> list[tuple[str, str, str]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(cleaned)
    except ValueError as exc:
        raise GeneratorError("not JSON") from exc
    items = value.get("hypotheses") if isinstance(value, dict) else None
    if not isinstance(items, list):
        raise GeneratorError("no hypotheses list")
    parsed = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("higher"), str) or not isinstance(item.get("lower"), str):
            raise GeneratorError("a hypothesis needs a higher and a lower model")
        rationale = item.get("rationale")
        parsed.append((item["higher"], item["lower"], rationale if isinstance(rationale, str) else ""))
    return parsed


def _refusal(subject: str, other: str, names: list[str]) -> str:
    if subject not in names or other not in names:
        return "unknown model"
    if subject == other:
        return "a model cannot be compared with itself"
    if not generate.pair_allowed(subject, other):
        return "a default control can only be compared with its own model"
    return ""


def make_generator(complete: Callable[[str], str]) -> Callable[..., tuple[list[Hypothesis], list[dict[str, str]]]]:
    def propose(
        view: ExplorationView,
        registry: Registry,
        stage: str,
        count: int,
        effect: float = generate.DEFAULT_EFFECT,
        consistency: float = generate.DEFAULT_CONSISTENCY,
        known: Known = frozenset(),
    ) -> tuple[list[Hypothesis], list[dict[str, str]]]:
        names = generate.model_names(view)
        try:
            requested = parse(complete(prompt(view, names, stage, count)))
        except Exception as exc:
            proposals, skipped = generate.propose(view, registry, stage, count, effect, consistency, known)
            reason = f"the language model answer was not usable ({type(exc).__name__}: {exc}); the rule generator was used"
            return proposals, [{"statement": "language model proposals", "reason": reason}, *skipped]
        proposals: list[Hypothesis] = []
        skipped: list[dict[str, str]] = []
        capacity = min(count, registry.remaining)
        seen: set[tuple[str, tuple[str, ...], tuple[str, ...], str]] = set()
        for subject, other, rationale in requested:
            if len(proposals) >= capacity:
                break
            reason = _refusal(subject, other, names)
            if reason:
                skipped.append({"statement": f"{subject} vs {other}", "reason": reason})
                continue
            item = Hypothesis(
                id=f"H{len(registry.records) + len(proposals) + 1}",
                subject=(subject,),
                other=(other,),
                stage=stage,
                metric=PRIMARY_METRIC,
                statement=generate.statement(subject, other, PRIMARY_METRIC, stage),
                evidence={**generate.exploration_evidence(view, subject, other), "rationale": rationale},
            )
            if registry.has(item) or item.key in seen:
                skipped.append({"statement": item.statement, "reason": generate.ALREADY_REGISTERED})
            elif ((subject,), (other,)) in known:
                skipped.append({"statement": item.statement, "reason": generate.ALREADY_KNOWN})
            else:
                seen.add(item.key)
                proposals.append(item)
        return proposals, skipped

    return propose


def make_complete(model: str) -> Callable[[str], str]:
    from openai import OpenAI

    from app.config import OPENAI_API_KEY

    client = OpenAI(api_key=OPENAI_API_KEY)

    def complete(text: str) -> str:
        response = client.chat.completions.create(model=model, temperature=0, response_format={"type": "json_object"}, messages=[{"role": "user", "content": text}])
        return response.choices[0].message.content or ""

    return complete
