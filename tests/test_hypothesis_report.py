import pytest

import app.graph.nodes as nodes
from app.agents.consistency import (
    HYPOTHESIS_MISSING_NOTICE,
    HYPOTHESIS_REVERSED_NOTICE,
    hypothesis_issues,
    section_of,
)
from app.agents.report import SYSTEM_PROMPT

PAPER = """# Paper

## Abstract

{abstract}

## Methodology

We trained two models.

## Results

Numbers.

## Conclusion

{conclusion}
"""


def paper(abstract, conclusion):
    return PAPER.format(abstract=abstract, conclusion=conclusion)


def verdict(value):
    return {"claim": {"kind": "performance"}, "verdict": value, "evidence": {}}


@pytest.mark.parametrize(
    ("value", "sentence"),
    [
        ("supported", "The hypothesis was supported."),
        ("supported", "Our hypothesis is supported by the data."),
        ("contradicted", "The hypothesis was contradicted."),
        ("contradicted", "The data contradict the hypothesis."),
        ("inconclusive", "The hypothesis was inconclusive."),
        ("inconclusive", "The result is inconclusive."),
    ],
)
def test_a_paper_that_states_the_verdict_in_both_sections_passes(value, sentence):
    text = paper(f"We compare models. {sentence}", f"In short: {sentence}")
    assert hypothesis_issues(text, verdict(value)) == []


@pytest.mark.parametrize("value", ["supported", "contradicted", "inconclusive"])
def test_a_paper_that_never_states_the_verdict_is_flagged_in_both_sections(value):
    text = paper("We compare two models.", "Random Forest is a good model.")
    issues = hypothesis_issues(text, verdict(value))
    assert issues == [
        HYPOTHESIS_MISSING_NOTICE.format(verdict=value, section="Abstract"),
        HYPOTHESIS_MISSING_NOTICE.format(verdict=value, section="Conclusion"),
    ]


def test_the_verdict_may_be_missing_from_only_one_section():
    text = paper("The hypothesis was supported.", "Random Forest is a good model.")
    assert hypothesis_issues(text, verdict("supported")) == [
        HYPOTHESIS_MISSING_NOTICE.format(verdict="supported", section="Conclusion")
    ]


@pytest.mark.parametrize("sentence", ["The hypothesis was not supported.", "The hypothesis is unsupported."])
def test_a_negated_support_is_not_support(sentence):
    text = paper(sentence, sentence)
    assert len(hypothesis_issues(text, verdict("supported"))) == 2


@pytest.mark.parametrize("value", ["contradicted", "inconclusive"])
def test_claiming_support_against_the_verdict_is_flagged(value):
    text = paper(
        f"The hypothesis was {value}, yet it was also supported.",
        f"The hypothesis was {value}.",
    )
    assert hypothesis_issues(text, verdict(value)) == [
        HYPOTHESIS_REVERSED_NOTICE.format(verdict=value, section="Abstract")
    ]


@pytest.mark.parametrize("value", ["contradicted", "inconclusive"])
def test_a_negated_support_is_fine_next_to_a_contradicted_or_inconclusive_verdict(value):
    text = paper(
        f"The hypothesis was not supported: it was {value}.",
        f"The hypothesis was {value} and so not supported.",
    )
    assert hypothesis_issues(text, verdict(value)) == []


def test_an_untested_or_missing_verdict_asks_for_nothing():
    text = paper("Nothing.", "Nothing.")
    assert hypothesis_issues(text, verdict("untested")) == []
    assert hypothesis_issues(text, None) == []
    assert hypothesis_issues(text, {}) == []
    assert hypothesis_issues(text, {"verdict": "unknown"}) == []


def test_a_paper_without_headings_is_searched_as_a_whole():
    assert hypothesis_issues("The hypothesis was supported.", verdict("supported")) == []
    assert len(hypothesis_issues("Plain text.", verdict("supported"))) == 2


def test_a_section_runs_to_the_next_heading():
    text = paper("First part.", "Last part.")
    assert "First part." in section_of(text, "abstract")
    assert "We trained" not in section_of(text, "Abstract")
    assert section_of(text, "Conclusion").strip() == "Last part."


def state(**overrides):
    base = {
        "paper_markdown": paper("We compare two models.", "Random Forest is good."),
        "statistical_results": {},
        "statistical_decision": {"outcome": "none", "hypothesis": verdict("supported")},
        "consistency_rounds": 0,
        "verification_status": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def referee(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))


def test_the_node_sends_back_a_paper_that_does_not_state_the_verdict(referee):
    result = nodes.consistency_checker_node(state())
    assert result["consistency_continue"] is True
    assert "the hypothesis was supported" in result["consistency_feedback"]
    assert "research_status" not in result


def test_the_node_accepts_a_paper_that_states_the_verdict(referee):
    text = paper("The hypothesis was supported.", "The hypothesis was supported.")
    assert nodes.consistency_checker_node(state(paper_markdown=text))["research_status"] == "Completed"


def test_a_missing_verdict_ends_in_needs_review_after_two_rewrites(referee):
    result = nodes.consistency_checker_node(state(consistency_rounds=2))
    assert result["research_status"] == "NeedsReview"


def test_an_untested_hypothesis_is_not_asked_for_a_verdict(referee):
    untested = state(statistical_decision={"outcome": "none", "hypothesis": verdict("untested")})
    assert nodes.consistency_checker_node(untested)["research_status"] == "Completed"


def test_the_writer_is_told_the_exact_phrases_and_not_to_reframe():
    for phrase in ("the hypothesis was supported", "the hypothesis was contradicted", "the hypothesis was inconclusive"):
        assert phrase in SYSTEM_PROMPT
    assert "Hipotezi yeniden çerçeveleme" in SYSTEM_PROMPT
    assert "Methodology içinde hipotezin cümlesini aynen yaz" in SYSTEM_PROMPT
