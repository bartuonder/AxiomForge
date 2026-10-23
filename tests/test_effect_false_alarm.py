import pytest

from app.agents.consistency import _prose_sentences, parameter_effect_issues

METHODOLOGY = (
    "# Methodology\n"
    "The dataset used in this study was generated using `make_classification` with 1000 samples, 20 features, "
    "and a class imbalance ratio of 0.89 negative to 0.11 positive. The models tested were RandomForest with "
    "n_estimators set to 50 and LogisticRegression with C set to 0.5. A single train-test split with a random "
    "state of 42 was used, and no data leakage or execution errors were detected. The hypothesis tested was: "
    "\"LogisticRegression with C set to 0.5 has a higher PR-AUC than RandomForest with n_estimators set to 50 "
    "on the imbalanced dataset.\" The control group included models with default parameters to assess the "
    "impact of parameter tuning.\n"
)


def effect(model, metric="pr_auc"):
    return {
        "model": model,
        "params": {"x": 1},
        "metric": metric,
        "mean_difference": 0.001,
        "effect_size_dz": 0.1,
        "p_value": 0.8,
        "adjusted_p_value": 1.0,
        "significant": False,
    }


EFFECTS = [effect("RandomForest"), effect("LogisticRegression")]


def test_a_closing_quote_ends_the_sentence():
    sentences = _prose_sentences(METHODOLOGY)
    hypothesis = next(sentence for sentence in sentences if "hypothesis tested" in sentence)
    assert "default" not in hypothesis
    assert any(sentence.startswith("The control group") for sentence in sentences)


def test_the_real_methodology_paragraph_raises_no_alarm():
    assert parameter_effect_issues(METHODOLOGY, EFFECTS) == []


def test_a_hypothesis_sentence_that_mentions_default_is_exempt():
    paper = "The hypothesis was that RandomForest tuned this way has a higher PR-AUC than RandomForest with default parameters.\n"
    assert parameter_effect_issues(paper, [effect("RandomForest")]) == []


def test_a_purpose_sentence_that_mentions_default_is_exempt():
    paper = "We evaluate whether RandomForest tuned this way reaches a higher PR-AUC than with default parameters.\n"
    assert parameter_effect_issues(paper, [effect("RandomForest")]) == []


def test_a_default_mention_in_another_clause_does_not_count():
    paper = "RandomForest reached a higher PR-AUC in this run, while the default settings were kept for the rest.\n"
    assert parameter_effect_issues(paper, EFFECTS) == []


def test_a_real_claim_of_improvement_is_still_flagged():
    paper = "RandomForest with the listed parameters has a higher PR-AUC than RandomForest with default parameters.\n"
    issues = parameter_effect_issues(paper, [effect("RandomForest")])
    assert len(issues) == 1
    assert "significant false" in issues[0]


@pytest.mark.parametrize(
    "paper",
    [
        'He wrote "done." Then RandomForest with the listed parameters improved PR-AUC over default parameters.\n',
        "(see above.) RandomForest with the listed parameters improved PR-AUC over default parameters.\n",
    ],
)
def test_other_closing_marks_do_not_hide_a_real_claim(paper):
    assert len(parameter_effect_issues(paper, [effect("RandomForest")])) == 1
