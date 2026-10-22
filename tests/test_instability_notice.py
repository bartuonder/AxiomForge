import pytest

import app.graph.nodes as nodes
from app.agents.consistency import (
    INSTABILITY_ABSTRACT_NOTICE,
    INSTABILITY_MODEL_NOTICE,
    instability_issues,
)
from app.agents.report import SYSTEM_PROMPT

UNSTABLE = {
    "unstable": True,
    "std_threshold": 0.05,
    "flagged": [{"model": "SVM", "metric": "roc_auc", "std": 0.1794}],
}
STEADY = {"unstable": False, "std_threshold": 0.05, "flagged": []}

PAPER = """# Paper

## Abstract

{abstract}

## Results

| Model | ROC-AUC |
| --- | --- |
| SVM | 0.842 ± 0.179 |
| LogisticRegression | 0.904 ± 0.011 |

{results}

## Conclusion

{conclusion}
"""

GOOD_ABSTRACT = "We compare two models. SVM shows high variance across splits."
GENERIC_ABSTRACT = "Some model shows high variance across splits."
GOOD_RESULTS = "The standard deviation of SVM ROC-AUC is 0.179, above the threshold of 0.05, so SVM is unstable."
GOOD_CONCLUSION = "SVM results are sensitive to data splits, which is a limitation."


def paper(abstract=GOOD_ABSTRACT, results=GOOD_RESULTS, conclusion=GOOD_CONCLUSION):
    return PAPER.format(abstract=abstract, results=results, conclusion=conclusion)


def test_a_paper_that_reports_the_finding_everywhere_passes():
    assert instability_issues(paper(), UNSTABLE) == []


def test_nothing_is_required_without_a_finding():
    assert instability_issues(paper(abstract="Plain.", results="Plain.", conclusion="Plain."), STEADY) == []
    assert instability_issues(paper(), None) == []
    assert instability_issues(paper(), {}) == []


@pytest.mark.parametrize(
    "abstract",
    [
        "SVM is unstable across the five splits.",
        "We report the instability of SVM.",
        "SVM shows high variance across splits.",
        "SVM has a large standard deviation in ROC-AUC.",
        "SVM exceeds the standard deviation threshold.",
        "SVM is sensitive to the data split.",
    ],
)
def test_the_abstract_may_word_the_finding_in_several_ways(abstract):
    assert INSTABILITY_ABSTRACT_NOTICE not in instability_issues(paper(abstract=abstract), UNSTABLE)


@pytest.mark.parametrize(
    "abstract",
    [
        "We compare two models on an imbalanced dataset.",
        "Logistic Regression is statistically significantly more stable than SVM in ROC-AUC variance.",
        "The verification status is passed, confirming the reliability of the results.",
        "",
    ],
)
def test_an_abstract_without_the_finding_is_flagged(abstract):
    assert INSTABILITY_ABSTRACT_NOTICE in instability_issues(paper(abstract=abstract), UNSTABLE)


def test_the_flagged_model_needs_a_prose_sentence_not_just_the_table():
    text = paper(
        abstract=GENERIC_ABSTRACT,
        results="The models are compared in the table.",
        conclusion="We recommend LogisticRegression.",
    )
    issues = instability_issues(text, UNSTABLE)
    assert INSTABILITY_MODEL_NOTICE.format(model="SVM") in issues
    assert INSTABILITY_ABSTRACT_NOTICE not in issues


def test_the_table_row_alone_does_not_count_as_an_explanation():
    text = paper(abstract=GENERIC_ABSTRACT, results="| SVM | unstable |", conclusion="Nothing more.")
    assert INSTABILITY_MODEL_NOTICE.format(model="SVM") in instability_issues(text, UNSTABLE)


def test_a_sentence_about_another_model_does_not_cover_the_flagged_one():
    text = paper(
        abstract="LogisticRegression shows high variance across splits.",
        results="LogisticRegression is unstable.",
        conclusion="LogisticRegression has a large standard deviation.",
    )
    assert INSTABILITY_MODEL_NOTICE.format(model="SVM") in instability_issues(text, UNSTABLE)


def test_model_names_match_with_spaces_and_case():
    flagged = {"unstable": True, "std_threshold": 0.05, "flagged": [{"model": "RandomForest", "metric": "f1", "std": 0.1}]}
    text = paper(
        abstract="Random forest shows high variance across splits.",
        results="The random forest is unstable in F1.",
        conclusion="Done.",
    )
    assert instability_issues(text, flagged) == []


def test_a_model_flagged_for_two_metrics_is_asked_about_once():
    twice = {
        "unstable": True,
        "std_threshold": 0.05,
        "flagged": [
            {"model": "SVM", "metric": "roc_auc", "std": 0.2},
            {"model": "SVM", "metric": "f1", "std": 0.1},
        ],
    }
    text = paper(abstract=GENERIC_ABSTRACT, results="Plain.", conclusion="Plain.")
    notices = [item for item in instability_issues(text, twice) if item == INSTABILITY_MODEL_NOTICE.format(model="SVM")]
    assert len(notices) == 1


def test_every_flagged_model_is_checked():
    two = {
        "unstable": True,
        "std_threshold": 0.05,
        "flagged": [
            {"model": "SVM", "metric": "roc_auc", "std": 0.2},
            {"model": "KNN", "metric": "f1", "std": 0.1},
        ],
    }
    issues = instability_issues(paper(), two)
    assert INSTABILITY_MODEL_NOTICE.format(model="KNN") in issues
    assert INSTABILITY_MODEL_NOTICE.format(model="SVM") not in issues


def state(**overrides):
    base = {
        "paper_markdown": paper(abstract="We compare two models.", results="Plain.", conclusion="Plain."),
        "statistical_results": {},
        "statistical_decision": {"outcome": "none", "instability": UNSTABLE},
        "consistency_rounds": 0,
        "verification_status": "Passed",
    }
    base.update(overrides)
    return base


@pytest.fixture
def referee(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))


def test_the_node_sends_back_a_paper_that_hides_the_finding(referee):
    result = nodes.consistency_checker_node(state())
    assert result["consistency_continue"] is True
    assert INSTABILITY_ABSTRACT_NOTICE in result["consistency_feedback"]
    assert "research_status" not in result


def test_the_node_accepts_a_paper_that_reports_the_finding(referee):
    result = nodes.consistency_checker_node(state(paper_markdown=paper()))
    assert result["research_status"] == "Completed"


def test_a_hidden_finding_ends_in_needs_review_after_two_rewrites(referee):
    result = nodes.consistency_checker_node(state(consistency_rounds=2))
    assert result["research_status"] == "NeedsReview"
    assert INSTABILITY_ABSTRACT_NOTICE in result["consistency_feedback"]


def test_a_steady_run_is_not_asked_for_anything(referee):
    steady = state(statistical_decision={"outcome": "none", "instability": STEADY})
    assert nodes.consistency_checker_node(steady)["research_status"] == "Completed"


def test_the_finding_and_a_failed_verification_are_both_reported(referee):
    result = nodes.consistency_checker_node(state(verification_status="Failed"))
    assert INSTABILITY_ABSTRACT_NOTICE in result["consistency_feedback"]
    assert "Failed" in result["consistency_feedback"]


def test_the_writer_is_told_the_phrase_and_not_to_oversell_a_pass():
    assert "high variance across splits" in SYSTEM_PROMPT
    assert "Passed yalnız deneyin hatasız çalıştığını" in SYSTEM_PROMPT
