import pytest

import app.graph.nodes as nodes
from app.agents.consistency import VERIFICATION_NOTICE, abstract_of, verification_issue
from app.agents.report import SYSTEM_PROMPT, _brief

PAPER = """# Paper

## Abstract

{abstract}

## Methodology

We trained two models.

## Results

{results}
"""


def paper(abstract, results="Numbers."):
    return PAPER.format(abstract=abstract, results=results)


@pytest.mark.parametrize(
    "sentence",
    [
        "The experiment failed verification because the imputer was fitted before the split.",
        "The run failed the leakage verification.",
        "Verification failed: the script crashed.",
        "The verification did not pass.",
        "The experiment did not pass verification.",
        "The reported numbers are unverified.",
        "The results have not been verified.",
        "The results could not be verified.",
        "The pipeline failed to verify the metrics.",
        "FAILED VERIFICATION, so treat the numbers with care.",
        "However, the verification of the experiment failed due to data leakage in the imputer.",
        "The verification of the run was rejected after the leakage check.",
    ],
)
def test_a_failed_run_is_acknowledged_in_the_abstract(sentence):
    assert verification_issue(paper(sentence), "Failed") == ""


@pytest.mark.parametrize(
    "abstract",
    [
        "We compare two models on an imbalanced dataset.",
        "XGBoost is more stable than RandomForest.",
        "The verification step ran on five splits.",
        "The verification covered five splits. Training failed on none of them.",
        "",
    ],
)
def test_a_failed_run_that_is_not_acknowledged_is_flagged(abstract):
    assert verification_issue(paper(abstract), "Failed") == VERIFICATION_NOTICE


def test_the_notice_must_be_in_the_abstract_not_only_later():
    text = paper("We compare two models.", results="The experiment failed verification.")
    assert verification_issue(text, "Failed") == VERIFICATION_NOTICE


def test_a_passed_run_needs_no_notice():
    assert verification_issue(paper("We compare two models."), "Passed") == ""


def test_an_unverified_run_needs_no_notice():
    assert verification_issue(paper("We compare two models."), "") == ""


def test_a_paper_without_an_abstract_heading_is_searched_as_a_whole():
    assert verification_issue("The experiment failed verification.", "Failed") == ""
    assert verification_issue("Just some text.", "Failed") == VERIFICATION_NOTICE


def test_the_abstract_ends_at_the_next_heading():
    text = paper("First part.", results="Second part.")
    abstract = abstract_of(text)
    assert "First part." in abstract
    assert "Second part." not in abstract
    assert "Methodology" not in abstract


def test_the_abstract_heading_may_have_a_colon_or_another_level():
    text = "# Abstract:\nfailed verification here\n# Introduction\nother"
    assert "failed verification" in abstract_of(text)
    assert "other" not in abstract_of(text)


def test_the_last_section_runs_to_the_end():
    text = "## Introduction\nintro\n## Abstract\nthe tail"
    assert abstract_of(text).strip() == "the tail"


def paper_state(**overrides):
    state = {
        "paper_markdown": paper("We compare two models."),
        "statistical_results": {},
        "statistical_decision": {"outcome": "none"},
        "consistency_rounds": 0,
        "verification_status": "Failed",
    }
    state.update(overrides)
    return state


@pytest.fixture
def referee(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))


def test_the_node_sends_back_a_failed_run_that_hides_its_failure(referee):
    result = nodes.consistency_checker_node(paper_state())
    assert result["consistency_continue"] is True
    assert result["consistency_rounds"] == 1
    assert VERIFICATION_NOTICE in result["consistency_feedback"]
    assert "research_status" not in result


def test_the_node_accepts_a_failed_run_that_says_so(referee):
    text = paper("The experiment failed verification because of leakage.")
    result = nodes.consistency_checker_node(paper_state(paper_markdown=text))
    assert result["research_status"] == "Completed"
    assert result["consistency_feedback"] == ""


def test_a_hidden_failure_ends_in_needs_review_after_two_rewrites(referee):
    result = nodes.consistency_checker_node(paper_state(consistency_rounds=2))
    assert result["research_status"] == "NeedsReview"
    assert VERIFICATION_NOTICE in result["consistency_feedback"]


def test_a_passed_run_is_not_asked_for_a_notice(referee):
    result = nodes.consistency_checker_node(paper_state(verification_status="Passed"))
    assert result["research_status"] == "Completed"


def test_the_notice_is_added_to_the_other_issues(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (False, ["number mismatch"]))
    result = nodes.consistency_checker_node(paper_state())
    assert "number mismatch" in result["consistency_feedback"]
    assert VERIFICATION_NOTICE in result["consistency_feedback"]


def test_the_notice_is_added_to_a_direction_conflict(monkeypatch):
    def forbidden(*args):
        raise AssertionError("the LLM referee must not run")

    monkeypatch.setattr(nodes, "judge_consistency", forbidden)
    state = paper_state(
        paper_markdown=paper("XGBoost is better than RandomForest."),
        statistical_decision={"outcome": "tie"},
    )
    result = nodes.consistency_checker_node(state)
    assert "Yön Çelişkisi" in result["consistency_feedback"]
    assert VERIFICATION_NOTICE in result["consistency_feedback"]


def test_the_writer_is_told_the_exact_words_the_check_looks_for():
    assert "failed verification" in SYSTEM_PROMPT
    assert "Abstract" in SYSTEM_PROMPT


def test_the_writer_receives_the_status_and_the_reason():
    brief = _brief(
        {"query": "q", "verification_status": "Failed", "verifier_feedback": "Leakage çözülemedi: x"},
        [],
        "run",
    )
    assert "Verification status: Failed" in brief
    assert "Verifier feedback: Leakage çözülemedi: x" in brief
