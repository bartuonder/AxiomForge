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


def perf(metric, significant=True):
    return {
        "metric": metric,
        "a": "RandomForest",
        "b": "LogisticRegression",
        "mean_difference": 0.1,
        "effect_size_dz": 2.0,
        "p_value": 0.001,
        "adjusted_p_value": 0.001,
        "significant": significant,
    }


TIE_WITH_PERFORMANCE = {
    "outcome": "tie",
    "performance": [perf("roc_auc"), perf("pr_auc"), perf("f1", significant=False)],
}


@pytest.mark.parametrize(
    "sentence",
    [
        "The hypothesis that Random Forest is more stable than Logistic Regression in ROC-AUC variance was inconclusive.",
        "The hypothesis that Logistic Regression would outperform Random Forest in terms of ROC-AUC was contradicted.",
        "We hypothesized that Random Forest is superior to Logistic Regression.",
        "Hypothesis: Random Forest is more stable than Logistic Regression.",
    ],
)
def test_a_sentence_that_describes_the_hypothesis_is_not_a_superiority_claim(sentence):
    assert direction_conflict(sentence, TIE_WITH_PERFORMANCE) == ""
    assert direction_conflict(sentence, {"outcome": "tie"}) == ""


@pytest.mark.parametrize(
    "sentence",
    [
        "Random Forest showed superior performance across ROC-AUC and PR-AUC.",
        "Random Forest outperforms Logistic Regression in ROC-AUC.",
        "Random Forest is better than Logistic Regression on PR-AUC.",
    ],
)
def test_a_superiority_claim_about_a_significant_metric_is_allowed_in_a_stability_tie(sentence):
    assert direction_conflict(sentence, TIE_WITH_PERFORMANCE) == ""


@pytest.mark.parametrize(
    "sentence",
    [
        "Random Forest is more stable than Logistic Regression in ROC-AUC variance.",
        "Random Forest has a superior ROC-AUC stability.",
        "Random Forest outperforms Logistic Regression in F1.",
        "Random Forest is superior.",
        "Random Forest is better than Logistic Regression.",
    ],
)
def test_the_guard_still_catches_stability_claims_and_claims_without_a_significant_metric(sentence):
    assert direction_conflict(sentence, TIE_WITH_PERFORMANCE) == DIRECTION_CONFLICT


def test_a_significant_metric_does_not_excuse_a_claim_about_another_metric():
    sentence = "Random Forest outperforms Logistic Regression in F1."
    assert direction_conflict(sentence, TIE_WITH_PERFORMANCE) == DIRECTION_CONFLICT
    assert direction_conflict(sentence, {"outcome": "tie", "performance": [perf("f1")]}) == ""


def test_without_performance_tests_nothing_excuses_a_metric_claim():
    sentence = "Random Forest outperforms Logistic Regression in ROC-AUC."
    assert direction_conflict(sentence, {"outcome": "tie"}) == DIRECTION_CONFLICT
    assert direction_conflict(sentence, {"outcome": "tie", "performance": []}) == DIRECTION_CONFLICT
    assert direction_conflict(sentence, {"outcome": "tie", "performance": None}) == DIRECTION_CONFLICT


def test_one_offending_sentence_among_exempt_ones_still_fails_the_paper():
    paper = (
        "The hypothesis that Random Forest is more stable was inconclusive.\n"
        "Random Forest outperforms Logistic Regression in ROC-AUC.\n"
        "Random Forest is superior overall.\n"
    )
    assert direction_conflict(paper, TIE_WITH_PERFORMANCE) == DIRECTION_CONFLICT
