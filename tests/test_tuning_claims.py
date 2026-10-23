import pytest

import app.graph.nodes as nodes
from app.agents.consistency import tuning_claim_issues, untuned_model_issues

SPEC = {
    "statement": "LogisticRegression with C set to 0.5 has a higher PR-AUC than HistGradientBoosting with max_depth set to 5",
    "dataset": "customer_churn",
    "models": ["RandomForest", "LogisticRegression", "HistGradientBoosting"],
    "params": {"LogisticRegression": {"C": 0.5}, "HistGradientBoosting": {"max_depth": 5}},
}

REAL_ABSTRACT = (
    "The focus is on tuning the `n_estimators` parameter for Random Forest and the `C` parameter for Logistic Regression."
)
REAL_INTRODUCTION = (
    "This paper compares the performance of Random Forest, Logistic Regression, and Hist Gradient Boosting models "
    "on a telecom customer churn dataset, focusing on parameter tuning to enhance model performance."
)
REAL_METHODOLOGY = (
    "The models tested include Random Forest, Logistic Regression with `C` set to 0.5, and Hist Gradient Boosting "
    "with `max_depth` set to 5. A control group with default parameters for Logistic Regression and Hist Gradient "
    "Boosting was also included."
)
REAL_CONCLUSION = (
    "The results suggest that while parameter tuning can impact model performance, the differences between "
    "Logistic Regression and Hist Gradient Boosting were not statistically significant in this study."
)


def effect(model, metric="roc_auc", significant=False):
    return {
        "model": model,
        "params": {"x": 1},
        "metric": metric,
        "mean_difference": 0.001,
        "effect_size_dz": 0.1,
        "p_value": 0.5,
        "adjusted_p_value": 1.0,
        "significant": significant,
    }


NONE_SIGNIFICANT = [effect("LogisticRegression"), effect("HistGradientBoosting", "pr_auc")]


def test_the_real_abstract_claims_a_tuning_that_never_happened():
    issues = untuned_model_issues(REAL_ABSTRACT, SPEC)
    assert len(issues) == 1
    assert "RandomForest" in issues[0]
    assert "n_estimators" in issues[0]


def test_only_the_untuned_model_is_named():
    issues = untuned_model_issues(REAL_ABSTRACT, SPEC)
    assert "LogisticRegression için" not in issues[0]


@pytest.mark.parametrize(
    "sentence",
    [
        REAL_METHODOLOGY,
        REAL_INTRODUCTION,
        "We tuned the C of Logistic Regression, while Random Forest was left at its defaults.",
        "Random Forest was not tuned.",
        "Random Forest ran with default parameters and no tuning.",
        "Random Forest was kept at default parameters rather than tuned.",
        "Hyperparameter tuning was applied to Logistic Regression and Hist Gradient Boosting.",
        "Hyperparameter tuning was not part of this study.",
        "Logistic Regression was tuned with C set to 0.5.",
    ],
)
def test_an_honest_description_of_the_tuning_passes(sentence):
    assert untuned_model_issues(sentence, SPEC) == []


def test_a_table_row_is_not_prose():
    table = "| Model | note |\n| --- | --- |\n| Random Forest tuned | x |\n"
    assert untuned_model_issues(table, SPEC) == []


def test_a_spec_without_parameters_leaves_every_model_untuned():
    bare = {**SPEC, "params": {}}
    assert len(untuned_model_issues("Logistic Regression was tuned carefully.", bare)) == 1


def test_no_spec_means_nothing_to_check():
    assert untuned_model_issues(REAL_ABSTRACT, None) == []
    assert untuned_model_issues(REAL_ABSTRACT, {}) == []


def test_the_real_conclusion_overstates_the_tuning_when_no_effect_is_significant():
    issues = tuning_claim_issues(REAL_CONCLUSION, NONE_SIGNIFICANT, SPEC)
    assert len(issues) == 1
    assert "parameter tuning can impact model performance" in issues[0]


def test_a_significant_effect_makes_the_claim_legitimate():
    effects = [effect("LogisticRegression", significant=True), effect("HistGradientBoosting", "pr_auc")]
    assert tuning_claim_issues(REAL_CONCLUSION, effects, SPEC) == []


@pytest.mark.parametrize(
    "sentence",
    [
        REAL_INTRODUCTION,
        "No significant effect of the listed parameters on ROC-AUC was found for LogisticRegression compared with default parameters (adjusted p = 1).",
        "Tuning did not improve the performance of any model.",
        "Parameter tuning had no significant impact on performance.",
        "The hypothesis was that parameter tuning improves PR-AUC.",
        "We wanted to see whether parameter tuning would improve the results.",
        "Logistic Regression has a higher mean ROC-AUC than Random Forest.",
    ],
)
def test_a_neutral_or_negated_mention_of_tuning_passes(sentence):
    assert tuning_claim_issues(sentence, NONE_SIGNIFICANT, SPEC) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "Hyperparameter tuning improved the F1 of Logistic Regression.",
        "Careful parameter tuning boosts accuracy.",
        "Tuning the parameters had a positive impact on the results.",
        "Optimization of the settings enhanced performance.",
    ],
)
def test_an_effect_claim_without_support_is_flagged(sentence):
    assert len(tuning_claim_issues(sentence, NONE_SIGNIFICANT, SPEC)) == 1


def test_nothing_is_required_without_effects():
    assert tuning_claim_issues(REAL_CONCLUSION, [], SPEC) == []
    assert tuning_claim_issues(REAL_CONCLUSION, None, SPEC) == []


STATE = {
    "paper_markdown": "",
    "statistical_results": {},
    "statistical_decision": {"parameter_effects": NONE_SIGNIFICANT},
    "verification_status": "Passed",
    "hypotheses": [SPEC["statement"]],
    "experiment_specs": [SPEC],
}


def test_the_gate_sends_back_the_real_paper_sentences():
    paper = f"# Abstract\n{REAL_ABSTRACT}\n# Conclusion\n{REAL_CONCLUSION}\n"
    issues = nodes._gate_issues({**STATE, "paper_markdown": paper})
    assert any("RandomForest için onaylanan spesifikasyonda parametre yok" in issue for issue in issues)
    assert any("parametre ayarının sonucu etkilediğini" in issue for issue in issues)


def test_the_gate_accepts_a_corrected_paper():
    paper = (
        "# Abstract\nWe tuned Logistic Regression and Hist Gradient Boosting, while Random Forest used fixed parameters.\n"
        "# Conclusion\nNo significant effect of the parameters was found.\n"
    )
    issues = nodes._gate_issues({**STATE, "paper_markdown": paper})
    assert not any("spesifikasyonda parametre yok" in issue for issue in issues)
    assert not any("etkilediğini" in issue for issue in issues)


@pytest.mark.parametrize(
    "sentence",
    [
        "We tuned Logistic Regression and Hist Gradient Boosting.",
        "Parameter tuning was applied to Gradient Boosting and XGBoost.",
    ],
)
def test_a_boosting_model_name_is_not_an_effect_claim(sentence):
    assert tuning_claim_issues(sentence, NONE_SIGNIFICANT, SPEC) == []


def test_the_writer_is_told_both_rules():
    from app.agents.report import SYSTEM_PROMPT

    assert "yalnız Experiment spec içinde params'ı olan modeller için yaz" in SYSTEM_PROMPT
    assert "sonucu etkilediğini, iyileştirdiğini veya sonuçlara etki ettiğini yazma" in SYSTEM_PROMPT
