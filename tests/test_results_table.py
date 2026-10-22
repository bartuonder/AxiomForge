import pytest

import app.graph.nodes as nodes
from app.agents.consistency import (
    TABLE_CELL_NOTICE,
    TABLE_COLUMN_NOTICE,
    TABLE_MISSING_NOTICE,
    TABLE_ROW_NOTICE,
    table_issues,
)
from app.agents.report import SYSTEM_PROMPT

RESULTS = {
    "RandomForest": {
        "accuracy_mean": 0.9705, "accuracy_std": 0.0069,
        "f1_mean": 0.8396, "f1_std": 0.0406,
        "roc_auc_mean": 0.9346, "roc_auc_std": 0.0296,
        "pr_auc_mean": 0.8486, "pr_auc_std": 0.0373,
        "train_seconds_mean": 0.1717, "train_seconds_std": 0.0126,
    },
    "LogisticRegression": {
        "accuracy_mean": 0.7640, "accuracy_std": 0.0228,
        "f1_mean": 0.3875, "f1_std": 0.0350,
        "roc_auc_mean": 0.8189, "roc_auc_std": 0.0469,
        "pr_auc_mean": 0.6037, "pr_auc_std": 0.0830,
        "train_seconds_mean": 0.0043, "train_seconds_std": 0.0072,
    },
    "statistical_conclusion": "Tie.",
}

HEADER = "| Model | Accuracy | F1 | ROC-AUC | PR-AUC | Train seconds |\n| --- | --- | --- | --- | --- | --- |\n"
RF = "| RandomForest | 0.9705 ± 0.0069 | 0.8396 ± 0.0406 | 0.9346 ± 0.0296 | 0.8486 ± 0.0373 | 0.1717 ± 0.0126 |\n"
LR = "| LogisticRegression | 0.7640 ± 0.0228 | 0.3875 ± 0.0350 | 0.8189 ± 0.0469 | 0.6037 ± 0.0830 | 0.0043 ± 0.0072 |\n"
GOOD = "# Results\nThe table follows.\n\n" + HEADER + RF + LR + "\nMore text.\n"


def test_a_table_with_the_verified_numbers_passes():
    assert table_issues(GOOD, RESULTS) == []


def test_the_real_second_run_table_format_passes():
    table = (
        "| Model | Accuracy | F1 | ROC-AUC | PR-AUC | Train seconds |\n"
        "|-------|----------|----|---------|--------|---------------|\n"
        "| RandomForest | 0.9705 ± 0.0069 | 0.8396 ± 0.0406 | 0.9346 ± 0.0296 | 0.8486 ± 0.0373 | 0.1717 ± 0.0126 |\n"
        "| LogisticRegression | 0.7640 ± 0.0228 | 0.3875 ± 0.0350 | 0.8189 ± 0.0469 | 0.6037 ± 0.0830 | 0.0043 ± 0.0072 |\n"
    )
    assert table_issues("# Results\n" + table, RESULTS) == []


def test_honest_rounding_to_three_or_two_decimals_is_accepted():
    rounded = (
        HEADER
        + "| RandomForest | 0.971 ± 0.007 | 0.84 ± 0.04 | 0.935 ± 0.030 | 0.849 ± 0.037 | 0.172 ± 0.013 |\n"
        + "| LogisticRegression | 0.764 ± 0.023 | 0.39 ± 0.04 | 0.819 ± 0.047 | 0.604 ± 0.083 | 0.004 ± 0.007 |\n"
    )
    assert table_issues(rounded, RESULTS) == []


def test_a_wrong_mean_is_reported_with_the_verified_value():
    text = GOOD.replace("0.9346 ± 0.0296", "0.9456 ± 0.0296")
    assert table_issues(text, RESULTS) == [
        TABLE_CELL_NOTICE.format(
            model="RandomForest", metric="ROC-AUC", found="0.9456 ± 0.0296", expected="0.9346 ± 0.0296"
        )
    ]


def test_a_wrong_std_is_reported():
    text = GOOD.replace("0.8486 ± 0.0373", "0.8486 ± 0.0830")
    issues = table_issues(text, RESULTS)
    assert len(issues) == 1
    assert "PR-AUC" in issues[0] and "0.8486 ± 0.0373" in issues[0]


def test_swapped_models_are_both_reported():
    swapped = GOOD.replace("| RandomForest |", "| TMP |").replace("| LogisticRegression |", "| RandomForest |").replace("| TMP |", "| LogisticRegression |")
    issues = table_issues(swapped, RESULTS)
    assert len(issues) == 10
    assert all("RandomForest" in item or "LogisticRegression" in item for item in issues)


def test_a_rounding_that_is_too_coarse_is_not_the_verified_value():
    text = GOOD.replace("0.9346 ± 0.0296", "0.94 ± 0.03")
    assert len(table_issues(text, RESULTS)) == 1


def test_a_cell_without_the_plus_minus_form_is_reported():
    text = GOOD.replace("0.9346 ± 0.0296", "0.9346")
    issues = table_issues(text, RESULTS)
    assert len(issues) == 1
    assert "'0.9346'" in issues[0]


def test_an_empty_cell_is_reported_as_empty():
    text = GOOD.replace("0.9346 ± 0.0296", "")
    assert "'boş'" in table_issues(text, RESULTS)[0]


def test_a_missing_model_row_is_reported():
    text = "# Results\n" + HEADER + RF
    assert table_issues(text, RESULTS) == [TABLE_ROW_NOTICE.format(model="LogisticRegression")]


def test_a_missing_column_is_reported_once_and_its_cells_are_not():
    header = "| Model | Accuracy | F1 | ROC-AUC | Train seconds |\n| --- | --- | --- | --- | --- |\n"
    rf = "| RandomForest | 0.9705 ± 0.0069 | 0.8396 ± 0.0406 | 0.9346 ± 0.0296 | 0.1717 ± 0.0126 |\n"
    lr = "| LogisticRegression | 0.7640 ± 0.0228 | 0.3875 ± 0.0350 | 0.8189 ± 0.0469 | 0.0043 ± 0.0072 |\n"
    assert table_issues("# Results\n" + header + rf + lr, RESULTS) == [TABLE_COLUMN_NOTICE.format(metric="PR-AUC")]


def test_a_paper_without_a_table_is_reported():
    assert table_issues("# Results\nThe numbers are in the text only.", RESULTS) == [TABLE_MISSING_NOTICE]


def test_a_table_without_metric_columns_does_not_count():
    other = "| Name | Value |\n| --- | --- |\n| a | 1 |\n"
    assert table_issues("# Results\n" + other, RESULTS) == [TABLE_MISSING_NOTICE]


def test_the_first_table_with_metric_columns_is_the_one_checked():
    other = "| Name | Value |\n| --- | --- |\n| a | 1 |\n\n"
    assert table_issues("# Results\n" + other + HEADER + RF + LR, RESULTS) == []


def test_a_later_unrelated_table_does_not_matter():
    pvalues = "\n| Comparison | Adjusted p |\n| --- | --- |\n| RF vs LR | 0.004 |\n"
    assert table_issues(GOOD + pvalues, RESULTS) == []


def test_model_names_may_have_spaces_case_and_markup():
    text = GOOD.replace("| RandomForest |", "| **Random Forest** |").replace("| LogisticRegression |", "| logistic regression |")
    assert table_issues(text, RESULTS) == []


def test_header_names_may_use_common_variants():
    header = "| Model | Accuracy | F1-score | ROC AUC | PR_AUC | Training time |\n| --- | --- | --- | --- | --- | --- |\n"
    assert table_issues("# Results\n" + header + RF + LR, RESULTS) == []


def test_the_ascii_plus_minus_is_accepted():
    text = GOOD.replace("±", "+/-")
    assert table_issues(text, RESULTS) == []


def test_columns_may_come_in_any_order():
    header = "| Model | Train seconds | PR-AUC | ROC-AUC | F1 | Accuracy |\n| --- | --- | --- | --- | --- | --- |\n"
    rf = "| RandomForest | 0.1717 ± 0.0126 | 0.8486 ± 0.0373 | 0.9346 ± 0.0296 | 0.8396 ± 0.0406 | 0.9705 ± 0.0069 |\n"
    lr = "| LogisticRegression | 0.0043 ± 0.0072 | 0.6037 ± 0.0830 | 0.8189 ± 0.0469 | 0.3875 ± 0.0350 | 0.7640 ± 0.0228 |\n"
    assert table_issues("# Results\n" + header + rf + lr, RESULTS) == []


def test_scientific_notation_in_a_cell_is_compared_with_a_relative_tolerance():
    small = {"A": {**{f"{m}_mean": 0.5 for m in ("accuracy", "f1", "roc_auc", "pr_auc")}, **{f"{m}_std": 0.01 for m in ("accuracy", "f1", "roc_auc", "pr_auc")}, "train_seconds_mean": 4.3e-05, "train_seconds_std": 1.2e-05}}
    row = "| A | 0.5000 ± 0.0100 | 0.5000 ± 0.0100 | 0.5000 ± 0.0100 | 0.5000 ± 0.0100 | 4.3e-05 ± 1.2e-05 |\n"
    assert table_issues("# R\n" + HEADER + row, small) == []
    assert len(table_issues("# R\n" + HEADER + row.replace("4.3e-05", "9.0e-05"), small)) == 1


def test_nothing_is_checked_without_verified_results():
    assert table_issues("no table at all", {}) == []
    assert table_issues("no table at all", None) == []
    assert table_issues("no table at all", {"statistical_conclusion": "x"}) == []


def state(**overrides):
    base = {
        "paper_markdown": GOOD,
        "statistical_results": RESULTS,
        "statistical_decision": {"outcome": "none"},
        "consistency_rounds": 0,
        "verification_status": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def referee(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))


def test_the_node_sends_back_a_paper_with_a_wrong_table_cell(referee):
    result = nodes.consistency_checker_node(state(paper_markdown=GOOD.replace("0.9346 ± 0.0296", "0.9456 ± 0.0296")))
    assert result["consistency_continue"] is True
    assert "0.9346 ± 0.0296" in result["consistency_feedback"]
    assert "research_status" not in result


def test_the_node_accepts_a_correct_table(referee):
    assert nodes.consistency_checker_node(state())["research_status"] == "Completed"


def test_a_wrong_table_ends_in_needs_review_after_two_rewrites(referee):
    wrong = state(paper_markdown=GOOD.replace("0.9346 ± 0.0296", "0.9456 ± 0.0296"), consistency_rounds=2)
    assert nodes.consistency_checker_node(wrong)["research_status"] == "NeedsReview"


def test_a_run_without_verified_results_is_not_asked_for_a_table(referee):
    bare = state(paper_markdown="# Abstract\nNothing ran.", statistical_results={})
    assert nodes.consistency_checker_node(bare)["research_status"] == "Completed"


def test_the_writer_is_told_to_copy_the_cells_with_four_decimals():
    assert "dört ondalıkla kopyala" in SYSTEM_PROMPT
    assert "0.9346 ± 0.0296" in SYSTEM_PROMPT
