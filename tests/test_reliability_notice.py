import pytest

import app.graph.nodes as nodes
from app.agents.consistency import RELIABILITY_NOTICE, reliability_issue
from app.agents.report import SYSTEM_PROMPT

REAL_CONCLUSION = (
    "The experiment's verification status confirms the reliability of the results, "
    "with no data leakage or execution errors detected."
)


@pytest.mark.parametrize(
    "sentence",
    [
        REAL_CONCLUSION,
        "The verification step makes the results robust.",
        "Successful verification guarantees the numbers.",
        "The verified pipeline produces trustworthy estimates.",
        "Verification shows the findings are credible.",
        "The results are reliable because verification passed.",
        "VERIFICATION GIVES RELIABLE NUMBERS.",
    ],
)
def test_a_passed_paper_may_not_sell_the_pass_as_reliability(sentence):
    assert reliability_issue(f"# Conclusion\n{sentence}", "Passed") == RELIABILITY_NOTICE


@pytest.mark.parametrize(
    "sentence",
    [
        "The verification found no data leakage or execution errors.",
        "No data leakage or execution errors were detected during verification.",
        "The verification status of the experiment is passed.",
        "Random Forest is a robust classifier for tabular data.",
        "The results are reliable in the sense of repeated splits.",
        "Verification does not make the results reliable.",
        "The verification never guarantees the findings.",
    ],
)
def test_neutral_negated_or_unrelated_sentences_are_allowed(sentence):
    assert reliability_issue(f"# Conclusion\n{sentence}", "Passed") == ""


def test_the_check_only_applies_to_a_passed_run():
    assert reliability_issue(REAL_CONCLUSION, "Failed") == ""
    assert reliability_issue(REAL_CONCLUSION, "") == ""


def test_a_table_row_is_not_prose():
    assert reliability_issue("| verification | reliable |", "Passed") == ""


def test_the_claim_may_sit_in_the_abstract_or_anywhere_else():
    text = "# Abstract\nWe compare two models. Verification confirms reliable results.\n# Results\nNumbers."
    assert reliability_issue(text, "Passed") == RELIABILITY_NOTICE


def state(**overrides):
    base = {
        "paper_markdown": "# Abstract\nWe compare two models.\n# Conclusion\n" + REAL_CONCLUSION,
        "statistical_results": {},
        "statistical_decision": {"outcome": "none"},
        "consistency_rounds": 0,
        "verification_status": "Passed",
    }
    base.update(overrides)
    return base


@pytest.fixture
def referee(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))


def test_the_node_sends_back_a_paper_that_oversells_a_pass(referee):
    result = nodes.consistency_checker_node(state())
    assert result["consistency_continue"] is True
    assert RELIABILITY_NOTICE in result["consistency_feedback"]
    assert "research_status" not in result


def test_the_node_accepts_a_paper_that_states_the_pass_plainly(referee):
    text = "# Abstract\nWe compare two models.\n# Methodology\nNo data leakage or execution errors were detected."
    assert nodes.consistency_checker_node(state(paper_markdown=text))["research_status"] == "Completed"


def test_an_oversold_pass_ends_in_needs_review_after_two_rewrites(referee):
    result = nodes.consistency_checker_node(state(consistency_rounds=2))
    assert result["research_status"] == "NeedsReview"
    assert RELIABILITY_NOTICE in result["consistency_feedback"]


def test_a_failed_run_is_not_asked_about_reliability(referee):
    result = nodes.consistency_checker_node(state(verification_status="Failed"))
    assert RELIABILITY_NOTICE not in result["consistency_feedback"]


def test_the_writer_is_told_to_keep_a_pass_out_of_the_abstract_and_conclusion():
    assert "Abstract ve Conclusion içinde doğrulamadan hiç söz etme" in SYSTEM_PROMPT
    assert "no data leakage or execution errors were detected" in SYSTEM_PROMPT
    for word in ("reliable", "reliability", "robust", "trustworthy", "credible", "guarantee"):
        assert word in SYSTEM_PROMPT
