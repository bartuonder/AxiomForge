import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.campaign import store
from app.campaign.meta_evidence import VERDICT_TITLES, discussion_facts, exception_sentences, leader_sentence, margin_sentences, verdict_sentences
from app.config import OPENAI_API_KEY
from app.seeds import SPLIT_SEEDS

MODEL = "gpt-4o"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
PROSE_SECTIONS = ("introduction", "discussion")

INTRODUCTION_RULES = (
    "You write the Introduction of a replication report in English. "
    "Use only the source abstracts, the user query and the claim statements you are given. "
    "Write two or three short paragraphs: the research question, what the sources say about it, "
    "why testing a claim across many datasets matters, and which claims are tested. "
    "Hard rules: state no result, no verdict and no number; use no digits at all; "
    "never use the words replicated, contradicted, confirmed, supported, supports, refuted, significant or significantly; "
    "mention a source only by its exact title in quotation marks; do not invent sources, authors or facts that the abstracts do not contain. "
    "A publication year may be written with digits, for example Grinsztajn et al. 2022. "
    "If no source paper states the claims, say only that they come from the user question and do not comment on sources, abstracts or the lack of them."
)
DISCUSSION_RULES = (
    "You write the Discussion of a replication report in English. "
    "You are given facts that were computed by the system. Describe the pattern they show: where the claims held, "
    "where they did not, and how the models ranked. "
    "Hard rules: use no digits at all, so write no numbers, p-values or scores; refer to models and datasets by name only; "
    "any explanation of why a result looks as it does is a speculation and must use hedged wording "
    "such as may, might, could, possibly or we speculate; never present a cause as a fact; "
    "never generalise beyond the datasets named in the facts; mention only models and datasets that appear in the facts; "
    "do not introduce a verdict that the facts do not state; "
    "never use the words significant, significantly, supported, supports, confirmed or proved, because significance is reported only in the Results, "
    "and compare with plain words such as larger, smaller, ahead or behind. "
    "Never write the phrases all datasets, every dataset, always or in general; write the datasets tested instead. "
    "Also avoid the words demonstrated, demonstrates, proves, refutes and refuted. "
    "If no facts are given, return an empty discussion."
)
SYSTEM_PROMPT = (
    "You write two sections of a replication report and return only JSON with the keys introduction and discussion, "
    "each a string of Markdown paragraphs without headings. "
    f"Introduction rules: {INTRODUCTION_RULES} "
    f"Discussion rules: {DISCUSSION_RULES}"
)


def split_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    parts = re.split(r"(?m)^## (.+)$", markdown)
    for heading, body in zip(parts[1::2], parts[2::2]):
        sections[heading.strip()] = body.strip()
    return sections


def _dataset_refs(ledger: list[dict[str, Any]]) -> str:
    return " ".join(f"[{entry['id']}]" for entry in ledger if entry["kind"] == "dataset")


def _source_phrase(spec: dict[str, Any]) -> str:
    title = (spec.get("source") or {}).get("title")
    return f'the claims of "{title}"' if title else "the stated claims"


def abstract(spec: dict[str, Any], analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> str:
    finished = analysis["coverage"]["finished"]
    refs = _dataset_refs(ledger)
    if not finished or "error" in analysis:
        return (
            f"This report tried to replicate {_source_phrase(spec)} across {len(analysis['coverage']['requested'])} datasets, "
            f"but no dataset finished, so no claim could be assessed."
        )
    models = ", ".join(spec["models"][:-1]) + " and " + spec["models"][-1] if len(spec["models"]) > 1 else spec["models"][0]
    lines = [
        f"This report replicates {_source_phrase(spec)} on {len(finished)} tabular classification datasets {refs}. "
        f"It compares {models} with {len(SPLIT_SEEDS)} repeated stratified splits per dataset and tests every claim across datasets with exact signed-rank and Friedman tests."
    ]
    if (spec.get("source") or {}).get("deviations"):
        lines.append("The protocol differs from the original study in documented ways, listed in the Methodology.")
    lines.append(" ".join(verdict_sentences(analysis, ledger)))
    lines.extend(leader_sentence(analysis, ledger))
    return "\n\n".join(lines)


def conclusion(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> str:
    if "error" in analysis or not analysis.get("claims"):
        return "No claim could be assessed, so this report draws no conclusion about the source."
    outcomes = " and ".join(f"**{claim['id']}** was {VERDICT_TITLES[claim['verdict']]}" for claim in analysis["claims"])
    return f"Under this protocol, {outcomes}. These verdicts concern only the datasets tested and the estimators named in the Methodology."


def results(sections: dict[str, str], analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> str:
    parts = [sections.get("Summary", ""), sections.get("Results", "")]
    if "error" not in analysis and analysis.get("claims"):
        facts = exception_sentences(analysis, ledger) + margin_sentences(analysis, ledger)
        parts.append("### Where the claims did not hold, and where they held most clearly\n\n" + "\n\n".join(facts))
    return "\n\n".join(part for part in parts if part)


def claim_sources(spec: dict[str, Any], sources: list[dict[str, str]]) -> list[dict[str, str]]:
    title = (spec.get("source") or {}).get("title")
    return [paper for paper in sources if title and paper["title"] == title]


def _brief(query: str, sources: list[dict[str, str]], spec: dict[str, Any], facts: list[str], feedback: str, previous: dict[str, str] | None = None) -> str:
    own = claim_sources(spec, sources)
    listing = "\n\n".join(f'"{paper["title"]}": {paper["abstract"]}' for paper in own) or "No source paper states these claims; they come from the user query."
    claims = "\n".join(f"- {claim['id']}: {claim['statement']}" for claim in spec["claims"])
    text = f"User query:\n{query}\n\nSource abstracts:\n{listing}\n\nClaims under test:\n{claims}\n\nFacts for the discussion:\n"
    text += "\n".join(f"- {fact}" for fact in facts) if facts else "(none)"
    if feedback:
        text += f"\n\nYour previous text was rejected for these reasons, rewrite both sections and fix them: {feedback}"
        shown = [(name, (previous or {}).get(name, "")) for name in PROSE_SECTIONS]
        shown = [(name, value) for name, value in shown if value]
        if shown:
            text += "".join(f"\n\nYour previous {name.capitalize()}:\n{value}" for name, value in shown)
            text += "\n\nKeep every sentence that the reasons do not touch and change only what they require."
    return text


def _previous_prose(paper: str) -> dict[str, str]:
    sections = split_sections(paper or "")
    return {name: sections.get(name.capitalize(), "") for name in PROSE_SECTIONS}


def _complete(user: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
    )
    return response.choices[0].message.content or ""


DATASET_SCOPE = r"\s+(?:that\s+(?:were\s+)?)?(?:tested|examined|studied|evaluated|included|in this campaign|of this campaign|in the campaign)\b"
_UNSCOPED = re.compile(r"\b(all|every)\s+(datasets?)\b(?!" + DATASET_SCOPE + ")", re.IGNORECASE)


def scope_datasets(text: str) -> str:
    return _UNSCOPED.sub(lambda match: f"{match.group(1)} the datasets tested" if match.group(2).lower() == "datasets" else f"{match.group(1)} dataset tested", text)


def write_prose(query: str, sources: list[dict[str, str]], spec: dict[str, Any], analysis: dict[str, Any], ledger: list[dict[str, Any]], feedback: str = "", previous: dict[str, str] | None = None) -> dict[str, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    facts = discussion_facts(analysis, ledger)
    try:
        payload = json.loads(_complete(_brief(query, sources, spec, facts, feedback, previous)))
    except json.JSONDecodeError as exc:
        raise RuntimeError("meta reporter returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("meta reporter did not return an object")
    prose = {}
    for name in PROSE_SECTIONS:
        value = payload.get(name)
        if not isinstance(value, str):
            raise RuntimeError(f"meta reporter did not return {name}")
        prose[name] = scope_datasets(value.strip())
    if not facts:
        prose["discussion"] = ""
    if not prose["introduction"]:
        raise RuntimeError("meta reporter returned an empty introduction")
    return prose


def compose(
    spec: dict[str, Any],
    analysis: dict[str, Any],
    ledger: list[dict[str, Any]],
    campaign_report: str,
    prose: dict[str, str],
) -> str:
    sections = split_sections(campaign_report)
    blocks = [
        f"# {spec['title']}",
        "## Abstract\n\n" + abstract(spec, analysis, ledger),
        "## Introduction\n\n" + prose["introduction"],
        "## Methodology\n\n" + sections.get("Protocol", ""),
        "## Results\n\n" + results(sections, analysis, ledger),
    ]
    if prose.get("discussion"):
        blocks.append("## Discussion\n\n" + prose["discussion"])
    blocks.append("## Limitations\n\n" + sections.get("Limitations", ""))
    blocks.append("## Conclusion\n\n" + conclusion(analysis, ledger))
    blocks.append("## Evidence ledger\n\n" + sections.get("Evidence ledger", ""))
    return "\n\n".join(blocks) + "\n"


def write_meta_paper(state: dict[str, Any], run_id: str) -> str:
    campaign_id = state.get("campaign_id") or ""
    campaign_report = store.load_report(campaign_id) if campaign_id else None
    if campaign_report is None:
        raise RuntimeError("the campaign report is missing")
    spec = state.get("campaign_spec") or {}
    analysis = state.get("campaign_analysis") or {}
    ledger = list(state.get("campaign_ledger") or [])
    prose = write_prose(
        state.get("query", ""),
        list(state.get("literature_sources") or []),
        spec,
        analysis,
        ledger,
        state.get("consistency_feedback", ""),
        _previous_prose(state.get("paper_markdown", "")),
    )
    markdown = compose(spec, analysis, ledger, campaign_report, prose)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{run_id}_paper.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)
