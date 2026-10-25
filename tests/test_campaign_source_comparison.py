import pytest

from app.campaign.analysis import analyze_campaign
from app.campaign.meta_evidence import AGREEMENT, comparison_sentences, discussion_facts
from app.campaign.report import render_report, report_issues

MODELS = ["RandomForest", "MLP", "LogisticRegression"]
QUOTE = "tree-based models remain state-of-the-art on medium-sized data"
CLAIMS = [
    {"id": "C1", "statement": "Trees beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc"], "subject": ["RandomForest"], "other": ["MLP"], "quote": QUOTE},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"], "subject": ["MLP"], "other": ["LogisticRegression"]},
]
SOURCE = {"title": "Why do trees win", "citation": "Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022)", "url": "https://arxiv.org/abs/2207.08815", "deviations": ["a note"]}
SPEC = {"title": "T", "models": MODELS, "params": {}, "claims": CLAIMS, "source": SOURCE}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h", "tb_pol", "tb_eye"]
BASE = {"RandomForest": 0.90, "MLP": 0.85, "LogisticRegression": 0.80}


def outcome(base=BASE):
    datasets = {}
    for index, key in enumerate(KEYS):
        summary = {name: {f"{metric}_mean": value + 0.001 * index for metric in ("roc_auc", "pr_auc", "f1")} for name, value in base.items()}
        datasets[key] = {
            "summary": summary,
            "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
            "seconds": 1.0,
            "attempts": 1,
            "script": key,
        }
    return {"order": list(KEYS), "datasets": datasets, "failed": {}}


def build(spec=SPEC, base=BASE):
    data = outcome(base)
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    return analysis, ledger, markdown


def section(markdown, name):
    return markdown.split(f"## {name}")[1].split("\n## ")[0]


def test_a_claim_with_a_quote_is_compared_with_the_source():
    _, ledger, markdown = build()
    text = section(markdown, "Comparison with the source")
    ref = next(entry["id"] for entry in ledger if entry["kind"] == "claim" and entry["key"] == "C1:roc_auc")
    assert f"The source states: “{QUOTE}”." in text
    assert f"The campaign result {AGREEMENT['replicated']} [{ref}]" in text


def test_the_section_names_the_source_with_its_citation():
    _, _, markdown = build()
    assert "Source of the claims: Why do trees win (Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022))." in section(markdown, "Comparison with the source")


def test_a_source_without_a_citation_is_named_by_its_title():
    spec = {**SPEC, "source": {k: v for k, v in SOURCE.items() if k != "citation"}}
    _, _, markdown = build(spec)
    assert "Source of the claims: Why do trees win." in section(markdown, "Comparison with the source")


def test_only_claims_with_a_quote_are_listed():
    _, _, markdown = build()
    text = section(markdown, "Comparison with the source")
    assert "**C1**" in text and "**C2**" not in text


def test_every_metric_reference_of_the_claim_is_cited():
    _, ledger, markdown = build()
    text = section(markdown, "Comparison with the source")
    for metric in ("roc_auc", "pr_auc"):
        entry = next(entry for entry in ledger if entry["kind"] == "claim" and entry["key"] == f"C1:{metric}")
        assert f"[{entry['id']}]" in text


def test_a_reversed_result_disagrees_with_the_source():
    flipped = {"RandomForest": 0.80, "MLP": 0.90, "LogisticRegression": 0.70}
    analysis, _, markdown = build(base=flipped)
    assert analysis["claims"][0]["verdict"] == "contradicted"
    assert AGREEMENT["contradicted"] in section(markdown, "Comparison with the source")


def test_there_is_no_section_without_a_quoted_claim():
    claims = [{k: v for k, v in claim.items() if k != "quote"} for claim in CLAIMS]
    _, _, markdown = build({**SPEC, "claims": claims})
    assert "Comparison with the source" not in markdown


def test_there_is_no_section_without_a_source():
    _, _, markdown = build({**SPEC, "source": {}})
    assert "Comparison with the source" not in markdown


def test_the_section_sits_between_results_and_limitations():
    _, _, markdown = build()
    assert markdown.index("## Results") < markdown.index("## Comparison with the source") < markdown.index("## Limitations")


def test_the_traceability_check_covers_the_new_section():
    _, ledger, markdown = build()
    assert report_issues(markdown, ledger) == []
    claim_lines = [line for line in section(markdown, "Comparison with the source").splitlines() if line.startswith("- ")]
    assert claim_lines and all("[E" in line for line in claim_lines)


def test_every_verdict_has_a_phrase():
    assert set(AGREEMENT) == {"replicated", "partially_replicated", "contradicted", "inconclusive", "not_testable"}


def test_the_facts_for_the_discussion_state_the_agreement():
    analysis, ledger, _ = build()
    sentences = comparison_sentences(analysis, ledger)
    assert len(sentences) == 1
    assert sentences[0].startswith("**C1** (Trees beat the MLP) was stated by the source and the campaign result " + AGREEMENT["replicated"])
    assert QUOTE not in sentences[0] and sentences[0].endswith(".")
    assert any(sentence in discussion_facts(analysis, ledger) for sentence in sentences)


def test_the_facts_skip_claims_without_a_quote():
    claims = [{k: v for k, v in claim.items() if k != "quote"} for claim in CLAIMS]
    analysis, ledger, _ = build({**SPEC, "claims": claims})
    assert comparison_sentences(analysis, ledger) == []


def test_a_failed_analysis_gives_no_facts():
    assert comparison_sentences({"error": "x"}, []) == []


def test_the_phrases_are_the_documented_ones():
    assert AGREEMENT == {
        "replicated": "agrees with the source",
        "partially_replicated": "agrees with the source on some metrics only",
        "contradicted": "disagrees with the source, the opposite held",
        "inconclusive": "neither confirms nor refutes the source",
        "not_testable": "could not test the claim of the source",
    }


def test_the_facts_cite_every_metric_of_the_claim():
    analysis, ledger, _ = build()
    sentence = comparison_sentences(analysis, ledger)[0]
    for metric in ("roc_auc", "pr_auc"):
        entry = next(entry for entry in ledger if entry["kind"] == "claim" and entry["key"] == f"C1:{metric}")
        assert f"[{entry['id']}]" in sentence
