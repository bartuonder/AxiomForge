import pytest

import app.graph.nodes as nodes
from app.agents.consistency import (
    EFFECT_SIZE_NOTICE,
    PERFORMANCE_OMISSION_NOTICE,
    performance_issues,
)
from app.agents.report import SYSTEM_PROMPT


def row(metric, p, dz, significant=True, a="RandomForest", b="LogisticRegression", diff=0.1):
    return {
        "metric": metric,
        "a": a,
        "b": b,
        "mean_difference": diff,
        "effect_size_dz": dz,
        "p_value": p,
        "adjusted_p_value": p,
        "significant": significant,
    }


REAL_RUN = [
    row("roc_auc", 0.004276, 2.243),
    row("pr_auc", 0.003101, 2.646),
    row("f1", 8.773e-07, 7.949),
]

REAL_TABLE = """| Model | ROC-AUC |
| --- | --- |
| RandomForest | 0.9346 ± 0.0296 |
"""

REAL_PAPER_AS_WRITTEN = (
    "# Abstract\n"
    "No statistically significant difference in ROC-AUC stability between the models. "
    "However, significant differences were observed in other metrics, with Random Forest showing higher mean values "
    "in F1 and PR-AUC.\n"
    "# Results\n" + REAL_TABLE + "\n"
    "The statistical analysis revealed no significant difference in ROC-AUC stability between the models "
    "(adjusted p-value = 0.2085). However, Random Forest demonstrated significantly higher mean values in F1 "
    "(adjusted p-value = 8.77e-07) and PR-AUC (adjusted p-value = 0.0031) compared to Logistic Regression.\n"
    "# Conclusion\n"
    "Random Forest exhibits higher performance in F1 and PR-AUC metrics.\n"
)

FIXED_PAPER = (
    "# Abstract\n"
    "Random Forest has significantly higher ROC-AUC, PR-AUC and F1 than Logistic Regression.\n"
    "# Results\n" + REAL_TABLE + "\n"
    "Random Forest has a significantly higher mean ROC-AUC (adjusted p = 0.0043, dz = 2.24). "
    "Random Forest has a significantly higher mean PR-AUC (adjusted p = 0.0031, dz = 2.65). "
    "Random Forest has a significantly higher mean F1 (adjusted p = 8.77e-07, dz = 7.95).\n"
    "# Conclusion\n"
    "Random Forest performs better in all three metrics.\n"
)


def test_the_paper_as_actually_written_is_flagged_for_the_missing_roc_auc_and_effect_sizes():
    issues = performance_issues(REAL_PAPER_AS_WRITTEN, REAL_RUN)
    assert PERFORMANCE_OMISSION_NOTICE.format(metric="ROC-AUC", a="RandomForest", b="LogisticRegression") in issues
    assert EFFECT_SIZE_NOTICE.format(metric="F1", value="7.95") in issues
    assert EFFECT_SIZE_NOTICE.format(metric="PR-AUC", value="2.65") in issues


def test_a_stability_sentence_does_not_count_as_reporting_the_mean_difference():
    only_stability = "# Results\nThe ROC-AUC variance of Random Forest is significantly lower than that of Logistic Regression.\n"
    issues = performance_issues(only_stability, [row("roc_auc", 0.004, 2.2)])
    assert issues == [PERFORMANCE_OMISSION_NOTICE.format(metric="ROC-AUC", a="RandomForest", b="LogisticRegression")]


def test_a_paper_that_reports_every_significant_difference_with_its_effect_size_passes():
    assert performance_issues(FIXED_PAPER, REAL_RUN) == []


def test_the_effect_size_may_be_written_with_more_digits():
    text = FIXED_PAPER.replace("dz = 7.95", "dz = 7.949")
    assert performance_issues(text, REAL_RUN) == []


def test_the_effect_size_may_be_written_as_an_absolute_value_when_the_gap_is_negative():
    flipped = [row("f1", 8.773e-07, -7.949)]
    assert performance_issues(FIXED_PAPER, flipped) == []


def test_a_wrong_effect_size_is_flagged():
    text = FIXED_PAPER.replace("dz = 7.95", "dz = 3.10")
    issues = performance_issues(text, REAL_RUN)
    assert issues == [EFFECT_SIZE_NOTICE.format(metric="F1", value="7.95")]


def test_a_missing_effect_size_is_flagged_once_the_metric_is_reported():
    text = FIXED_PAPER.replace(", dz = 2.24", "")
    assert performance_issues(text, REAL_RUN) == [EFFECT_SIZE_NOTICE.format(metric="ROC-AUC", value="2.24")]


def test_a_metric_reported_only_in_the_table_is_flagged():
    text = "# Results\n" + REAL_TABLE + "\nThe table shows the numbers.\n"
    issues = performance_issues(text, [row("roc_auc", 0.004, 2.2)])
    assert len(issues) == 1
    assert "ROC-AUC" in issues[0]


def test_a_negated_sentence_does_not_report_a_significant_difference():
    text = "# Results\nThere is no significant difference in F1 between the models.\n"
    issues = performance_issues(text, [row("f1", 0.001, 3.0)])
    assert issues == [PERFORMANCE_OMISSION_NOTICE.format(metric="F1", a="RandomForest", b="LogisticRegression")]


def test_nothing_is_required_for_a_difference_that_is_not_significant():
    quiet = [row("f1", 0.4, 0.3, significant=False), row("roc_auc", 0.2, 0.4, significant=False)]
    assert performance_issues("# Results\nNothing to see.\n", quiet) == []


def test_nothing_is_required_without_performance_tests():
    assert performance_issues("# Results\nText.\n", []) == []
    assert performance_issues("# Results\nText.\n", None) == []


def test_a_zero_effect_size_is_not_demanded():
    text = "# Results\nRandom Forest has a significantly higher mean F1.\n"
    assert performance_issues(text, [row("f1", 0.0, 0.0)]) == []


def test_metric_names_are_matched_in_their_common_spellings():
    spellings = ["ROC AUC", "ROC-AUC", "roc_auc", "roc-auc"]
    for spelling in spellings:
        text = f"# Results\nRandom Forest has a significantly higher {spelling} (dz = 2.24).\n"
        assert performance_issues(text, [row("roc_auc", 0.004, 2.243)]) == [], spelling


def test_average_precision_counts_for_pr_auc():
    text = "# Results\nRandom Forest has a significantly higher average precision (dz = 2.65).\n"
    assert performance_issues(text, [row("pr_auc", 0.003, 2.646)]) == []


def state(**overrides):
    base = {
        "paper_markdown": REAL_PAPER_AS_WRITTEN,
        "statistical_results": {},
        "statistical_decision": {"outcome": "none", "performance": REAL_RUN},
        "consistency_rounds": 0,
        "verification_status": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def referee(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))


def test_the_node_sends_back_the_paper_that_hides_a_significant_metric(referee):
    result = nodes.consistency_checker_node(state())
    assert result["consistency_continue"] is True
    assert "ROC-AUC için" in result["consistency_feedback"]
    assert "research_status" not in result


def test_the_node_accepts_a_complete_paper(referee):
    assert nodes.consistency_checker_node(state(paper_markdown=FIXED_PAPER))["research_status"] == "Completed"


def test_an_incomplete_paper_ends_in_needs_review_after_two_rewrites(referee):
    result = nodes.consistency_checker_node(state(consistency_rounds=2))
    assert result["research_status"] == "NeedsReview"


def test_a_run_without_performance_tests_is_not_asked_for_anything(referee):
    quiet = state(statistical_decision={"outcome": "none"})
    assert nodes.consistency_checker_node(quiet)["research_status"] == "Completed"


def test_the_writer_is_told_to_report_every_significant_row_with_its_effect_size():
    assert "significant true olan HER satırı" in SYSTEM_PROMPT
    assert "effect_size_dz" in SYSTEM_PROMPT
    assert "ROC-AUC dahil" in SYSTEM_PROMPT
