import pytest

from app.agents.consistency import DIRECTION_CONFLICT, conclusion_issues, direction_conflict

TIE = {"outcome": "tie"}
WINNER = {"outcome": "winner", "winner": "XGBoost"}


@pytest.mark.parametrize(
    "sentence",
    [
        "XGBoost performs better than RandomForest on ROC-AUC.",
        "RandomForest outperforms XGBoost on F1.",
        "XGBoost consistently outperformed all rivals.",
        "The method is superior to the baseline.",
        "This indicates the superiority of XGBoost.",
        "The better model is RandomForest.",
        "RandomForest was slightly better.",
        "Results show better stability for XGBoost.",
        "XGBoost is more stable than RandomForest.",
        "XGBoost achieves better performance overall.",
    ],
)
def test_a_tie_paper_may_not_claim_superiority(sentence):
    assert direction_conflict(sentence, TIE) == DIRECTION_CONFLICT


@pytest.mark.parametrize(
    "sentence",
    [
        "We use the extra features to better understand the data.",
        "Future work could better handle class imbalance.",
        "We tuned the threshold to better calibrate probabilities.",
        "The pipeline better reflects real deployment.",
        "Neither model performs better than the other.",
        "XGBoost is no better than RandomForest.",
        "No model is superior in ROC-AUC stability.",
        "The two models were not more stable than each other.",
        "RandomForest has a higher mean ROC-AUC.",
    ],
)
def test_neutral_and_negated_sentences_are_allowed_in_a_tie_paper(sentence):
    assert direction_conflict(sentence, TIE) == ""


def test_only_the_offending_sentence_matters():
    paper = "# Results\nThe models are comparable.\nXGBoost is better than RandomForest.\nEnd."
    assert direction_conflict(paper, TIE) == DIRECTION_CONFLICT


def test_the_direction_check_ignores_other_outcomes():
    paper = "XGBoost is better than RandomForest."
    assert direction_conflict(paper, WINNER) == ""
    assert direction_conflict(paper, {"outcome": "none"}) == ""
    assert direction_conflict(paper, {}) == ""


def test_a_winner_paper_must_name_the_winner():
    issues = conclusion_issues("RandomForest is the steadiest model.", WINNER)
    assert len(issues) == 1
    assert "XGBoost" in issues[0]


def test_a_winner_paper_may_not_report_no_difference():
    paper = "XGBoost is steadier. However there was no statistically significant difference."
    issues = conclusion_issues(paper, WINNER)
    assert len(issues) == 1
    assert "fark olmadığını" in issues[0]


@pytest.mark.parametrize(
    "phrase",
    ["indistinguishable", "(Tie)", "neither model", "No significant difference"],
)
def test_the_no_difference_phrases(phrase):
    issues = conclusion_issues(f"XGBoost was steadier, but the models are {phrase}.", WINNER)
    assert len(issues) == 1


def test_a_consistent_winner_paper_has_no_issues():
    assert conclusion_issues("XGBoost is statistically significantly more stable.", WINNER) == []


def test_conclusion_issues_only_apply_to_a_winner():
    assert conclusion_issues("indistinguishable", TIE) == []
    assert conclusion_issues("anything", {"outcome": "none"}) == []
