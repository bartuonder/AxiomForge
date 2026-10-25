import re
from typing import Any

from app.agents.meta_report import DATASET_SCOPE, split_sections
from app.campaign.meta_evidence import VERDICT_TITLES
from app.campaign.protocol import ESTIMATORS
from app.campaign.report import report_issues
from app.datasets import DATASETS

LLM_SECTIONS = ("Introduction", "Discussion")
CHECKED_SECTIONS = ("Abstract", "Results", "Conclusion")
MAX_EXAMPLES = 3
NEGATION_WINDOW = 25

_DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
_SIGNIFICANCE = re.compile(r"\bsignifican\w*\b", re.IGNORECASE)
_FORBIDDEN_CERTAINTY = re.compile(r"\b(confirm\w*|refut\w*|prov(?:e|es|ed|en)|disprov\w*|demonstrat\w*|supports|supported)\b", re.IGNORECASE)
_VERDICT_WORDS = re.compile(r"\b(replicat\w*|contradict\w*|inconclusive)\b", re.IGNORECASE)
_CAUSAL = re.compile(r"\b(because|due to|owing to|caused by|explained by|the reason|results? from|driven by|leads? to|thanks to|as a result of)\b", re.IGNORECASE)
_HEDGE = re.compile(r"\b(may|might|could|possibly|perhaps|plausibly|potentially|probably|we speculate|it is possible|a possible|one possible)\b", re.IGNORECASE)
_ABSOLUTE = re.compile(r"\b(always|never|universally|in general|generally speaking|all tabular|every tabular|any dataset|all datasets|every dataset|all data)\b", re.IGNORECASE)
_SCOPABLE = {"all datasets", "every dataset"}
_SCOPE = re.compile(DATASET_SCOPE, re.IGNORECASE)
_NEGATIONS = ("not ", "n't", "fail", "unable", "cannot", "no ")
_QUOTED = re.compile(r'"([^"]{20,})"')
_DATASET_NAME = re.compile(r"\b(?:tb_[a-z0-9]+|" + "|".join(re.escape(key) for key in sorted(DATASETS, key=len, reverse=True)) + r")\b")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_NAMED_DIGITS = re.compile(r"\bF1\b|\bC\d+\b|" + _DATASET_NAME.pattern)


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]


def _model_pattern(key: str) -> re.Pattern[str]:
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key).split()
    return re.compile(r"\b" + r"[ -]?".join(re.escape(word) for word in words) + r"\b", re.IGNORECASE)


def _digit_issues(sections: dict[str, str]) -> list[str]:
    issues = []
    for name in LLM_SECTIONS:
        text = _NAMED_DIGITS.sub("", sections.get(name, ""))
        if name == "Introduction":
            text = _YEAR.sub("", text)
        found = _DIGITS.findall(text)
        if found:
            issues.append(f"The {name} must contain no digits, but it contains: {', '.join(found[:MAX_EXAMPLES])}.")
    return issues


def _certainty_issues(sections: dict[str, str]) -> list[str]:
    issues = []
    for name in LLM_SECTIONS:
        for match in _FORBIDDEN_CERTAINTY.finditer(sections.get(name, "")):
            issues.append(
                f"The {name} uses the word {match.group(0)!r}; use only the given verdict words and hedged wording: "
                "do not use confirm, refute, prove, demonstrate or support, and state a result with the verdict word or a plain comparison such as 'scored higher'."
            )
            break
    return issues


def _significance_issues(sections: dict[str, str]) -> list[str]:
    issues = []
    for name in LLM_SECTIONS:
        match = _SIGNIFICANCE.search(sections.get(name, ""))
        if match:
            issues.append(f"The {name} uses statistical wording ({match.group(0)!r}); only the Results state significance, so compare with plain words such as larger, smaller, ahead or behind.")
    return issues


def _verdict_issues(sections: dict[str, str], analysis: dict[str, Any]) -> list[str]:
    verdicts = {claim["verdict"] for claim in analysis.get("claims") or []}
    issues = []
    intro = _VERDICT_WORDS.search(sections.get("Introduction", ""))
    if intro:
        issues.append(f"The Introduction must not state verdicts, but it uses {intro.group(0)!r}.")
    text = sections.get("Discussion", "")
    for sentence in _sentences(text):
        lowered = sentence.lower()
        for match in _VERDICT_WORDS.finditer(sentence):
            word = match.group(0).lower()
            negated = any(token in lowered[: match.start()][-NEGATION_WINDOW:] for token in _NEGATIONS)
            if word.startswith("contradict") and "contradicted" not in verdicts:
                issues.append(f"The Discussion says {word!r} although no claim was contradicted: {sentence[:100]}")
            elif word.startswith("replicat") and not negated and not verdicts & {"replicated", "partially_replicated"}:
                issues.append(f"The Discussion says {word!r} although no claim was replicated: {sentence[:100]}")
            elif word == "inconclusive" and not verdicts & {"inconclusive", "not_testable"}:
                issues.append(f"The Discussion says 'inconclusive' although no claim was inconclusive: {sentence[:100]}")
    return issues


def _speculation_issues(sections: dict[str, str]) -> list[str]:
    issues = []
    for sentence in _sentences(sections.get("Discussion", "")):
        if _CAUSAL.search(sentence) and not _HEDGE.search(sentence):
            issues.append(f"A cause is stated as a fact in the Discussion; hedge it (may, might, could, we speculate): {sentence[:100]}")
    return issues


def _scoped(text: str, match: re.Match[str]) -> bool:
    if match.group(0).lower() not in _SCOPABLE:
        return False
    return _SCOPE.match(text, match.end()) is not None


def _generalisation_issues(sections: dict[str, str]) -> list[str]:
    issues = []
    for name in LLM_SECTIONS:
        text = sections.get(name, "")
        match = next((found for found in _ABSOLUTE.finditer(text) if not _scoped(text, found)), None)
        if match:
            issues.append(f"The {name} generalises beyond the datasets tested with {match.group(0)!r}; write 'the datasets tested' instead.")
    return issues


def _scope_issues(sections: dict[str, str], spec: dict[str, Any]) -> list[str]:
    run = [str(model) for model in spec.get("models") or []]
    datasets = set(spec.get("datasets") or [])
    issues = []
    for name in LLM_SECTIONS:
        text = sections.get(name, "")
        for key in ESTIMATORS:
            if key in run or any(key.lower() in model.lower() for model in run):
                continue
            if _model_pattern(key).search(text):
                issues.append(f"The {name} mentions {key}, which was not run in this campaign.")
        for match in dict.fromkeys(_DATASET_NAME.findall(text)):
            if match not in datasets:
                issues.append(f"The {name} mentions the dataset {match}, which was not part of this campaign.")
    return issues


def _citation_issues(sections: dict[str, str], spec: dict[str, Any], sources: list[dict[str, str]]) -> list[str]:
    known = {str(paper["title"]).strip().lower() for paper in sources}
    title = (spec.get("source") or {}).get("title")
    if title:
        known.add(str(title).strip().lower())
    issues = []
    for quoted in _QUOTED.findall(sections.get("Introduction", "")):
        if quoted.strip().lower() not in known:
            issues.append(f"The Introduction cites {quoted[:80]!r}, which is not one of the provided sources.")
    return issues


def _structure_issues(sections: dict[str, str], spec: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    issues = []
    abstract = sections.get("Abstract", "")
    for claim in analysis.get("claims") or []:
        title = VERDICT_TITLES[claim["verdict"]]
        own = [sentence for sentence in _sentences(abstract) if f"**{claim['id']}**" in sentence]
        if not any(f"**{title}**" in sentence for sentence in own):
            issues.append(f"The Abstract does not state the verdict of {claim['id']}: {title}.")
    source = spec.get("source") or {}
    if source.get("title") and source["title"] not in abstract + sections.get("Methodology", ""):
        issues.append("The source title appears neither in the Abstract nor in the Methodology.")
    methodology = sections.get("Methodology", "")
    for note in source.get("deviations") or []:
        if f"- {note}" not in methodology:
            issues.append(f"The Methodology omits the deviation: {note[:80]}")
    limitations = sections.get("Limitations", "")
    for dataset in (analysis.get("coverage") or {}).get("failed") or {}:
        if dataset not in limitations:
            issues.append(f"The Limitations do not mention the failed dataset {dataset}.")
    return issues


def meta_issues(
    paper: str,
    spec: dict[str, Any],
    analysis: dict[str, Any],
    ledger: list[dict[str, Any]],
    sources: list[dict[str, str]] | None = None,
) -> list[str]:
    sections = split_sections(paper)
    issues = report_issues(paper, ledger, CHECKED_SECTIONS)
    issues += _digit_issues(sections)
    issues += _certainty_issues(sections)
    issues += _significance_issues(sections)
    issues += _verdict_issues(sections, analysis)
    issues += _speculation_issues(sections)
    issues += _generalisation_issues(sections)
    issues += _scope_issues(sections, spec)
    issues += _citation_issues(sections, spec, sources or [])
    issues += _structure_issues(sections, spec, analysis)
    return issues
