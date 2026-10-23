import pytest

import app.graph.nodes as nodes
from app.agents.consistency import unsupported_difference_issues


def row(metric, a, b, significant, p=0.5):
    return {
        "metric": metric,
        "a": a,
        "b": b,
        "mean_difference": 0.05,
        "effect_size_dz": 1.0,
        "p_value": p,
        "adjusted_p_value": p,
        "significant": significant,
    }


RUN_TWO = [
    row("roc_auc", "SVM", "KNN", False, 0.139),
    row("roc_auc", "SVM", "RandomForest", False, 0.122),
    row("roc_auc", "KNN", "RandomForest", True, 0.0464),
    row("pr_auc", "SVM", "KNN", False, 0.122),
    row("pr_auc", "SVM", "RandomForest", False, 0.122),
    row("pr_auc", "KNN", "RandomForest", False, 0.0591),
    row("f1", "SVM", "KNN", False, 0.417),
    row("f1", "SVM", "RandomForest", False, 0.122),
    row("f1", "KNN", "RandomForest", True, 0.0464),
]

REAL_RESULTS = (
    "The hypothesis was inconclusive (KNN versus RandomForest on ROC-AUC variance: variance 0.000851 against 0.000636, adjusted p = 1). "
    "No significant difference in ROC-AUC was found between SVM and KNN (adjusted p = 0.139). "
    "No significant difference in ROC-AUC was found between SVM and RandomForest (adjusted p = 0.122). "
    "RandomForest has a higher mean ROC-AUC than KNN (mean difference 0.0786, adjusted p = 0.0464, dz = 2.17). "
    "No significant difference in PR-AUC was found between KNN and RandomForest (adjusted p = 0.0591)."
)
REAL_CONCLUSION = (
    "The hypothesis that KNN is more stable than Random Forest in ROC-AUC variance was inconclusive. "
    "Random Forest showed higher mean ROC-AUC and F1 scores compared to KNN. "
    "However, both SVM and KNN exhibited high variance across splits in F1 scores, indicating sensitivity to data splits."
)
REAL_PAPER = "# Results\n" + REAL_RESULTS + "\n# Conclusion\n" + REAL_CONCLUSION + "\n"


def issues(text, rows=RUN_TWO):
    return unsupported_difference_issues("# Results\n" + text + "\n", rows)


def test_the_paper_the_writer_really_produced_has_no_unsupported_claim():
    assert unsupported_difference_issues(REAL_PAPER, RUN_TWO) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "RandomForest has a higher mean ROC-AUC than SVM.",
        "Random Forest outperforms SVM in ROC-AUC.",
        "KNN has a lower ROC-AUC than SVM.",
        "SVM is better than KNN on ROC-AUC.",
        "Random Forest has a higher PR-AUC than KNN.",
        "Random Forest outperforms SVM on F1.",
    ],
)
def test_a_superiority_claim_for_a_comparison_that_is_not_significant_is_flagged(sentence):
    found = issues(sentence)
    assert len(found) == 1
    assert sentence.rstrip(".") in found[0]


def test_the_message_names_the_metric_the_models_and_quotes_the_clause():
    found = issues("RandomForest has a higher mean ROC-AUC than SVM.")
    assert found[0].startswith("ROC-AUC için SVM ile RandomForest arasındaki fark anlamlı değil")
    assert '"RandomForest has a higher mean ROC-AUC than SVM."' in found[0]


@pytest.mark.parametrize(
    "sentence",
    [
        "RandomForest has a higher mean ROC-AUC than KNN (mean difference 0.0786, adjusted p = 0.0464, dz = 2.17).",
        "Random Forest showed higher mean F1 than KNN.",
    ],
)
def test_a_claim_for_a_significant_comparison_is_not_flagged(sentence):
    assert issues(sentence) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "No significant difference in ROC-AUC was found between SVM and KNN (adjusted p = 0.139).",
        "SVM is not better than KNN in PR-AUC.",
        "Neither SVM nor KNN has a higher F1.",
        "SVM and KNN do not differ in ROC-AUC, although SVM looks higher in the table.",
    ],
)
def test_negated_sentences_are_not_flagged(sentence):
    assert issues(sentence) == []


def test_a_clause_about_a_significant_pair_does_not_implicate_a_third_model():
    sentence = "Random Forest has a higher ROC-AUC than KNN, while SVM stays close to both."
    assert issues(sentence) == []


def test_a_three_model_clause_is_flagged_for_the_pair_that_is_not_significant():
    found = issues("Random Forest has a higher ROC-AUC than both KNN and SVM.")
    assert len(found) == 2
    assert any("SVM ile RandomForest" in item for item in found)
    assert any("SVM ile KNN" in item for item in found)


@pytest.mark.parametrize(
    "sentence",
    [
        "The hypothesis that Random Forest has a higher ROC-AUC than SVM was contradicted.",
        "We compare the models to determine whether Random Forest has a higher ROC-AUC than SVM.",
        "Random Forest is more stable than SVM in ROC-AUC variance.",
    ],
)
def test_hypothesis_aim_and_stability_sentences_are_not_difference_claims(sentence):
    assert issues(sentence) == []


def test_a_sentence_that_names_only_one_model_is_not_checked():
    assert issues("Random Forest has the highest mean ROC-AUC.") == []
    assert issues("Random Forest has a higher ROC-AUC.") == []


def test_table_rows_are_not_prose():
    assert issues("| RandomForest | higher than SVM | ROC-AUC |") == []


def test_each_unsupported_pair_is_reported_once():
    text = "Random Forest has a higher ROC-AUC than SVM. Random Forest outperforms SVM in ROC-AUC."
    assert len(issues(text)) == 1


def test_nothing_is_checked_without_insignificant_rows_or_rows_at_all():
    significant = [row("roc_auc", "A", "B", True, 0.001)]
    assert issues("A has a higher ROC-AUC than B.", significant) == []
    assert issues("A has a higher ROC-AUC than B.", []) == []
    assert unsupported_difference_issues("A has a higher ROC-AUC than B.", None) == []


def test_unknown_metrics_are_skipped():
    other = [row("accuracy", "A", "B", False)]
    assert issues("A has a higher accuracy than B.", other) == []


def state(paper, rounds=0):
    return {
        "paper_markdown": paper,
        "statistical_results": {},
        "statistical_decision": {"outcome": "none", "performance": RUN_TWO},
        "consistency_rounds": rounds,
        "verification_status": "",
    }


@pytest.fixture
def referee(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))


def test_the_node_sends_back_a_paper_that_claims_an_insignificant_difference(referee):
    paper = REAL_PAPER + "Random Forest has a higher PR-AUC than KNN.\n"
    result = nodes.consistency_checker_node(state(paper))
    assert result["consistency_continue"] is True
    assert "Random Forest has a higher PR-AUC than KNN" in result["consistency_feedback"]
    assert "research_status" not in result


def test_the_node_accepts_the_real_paper_on_this_check(referee):
    result = nodes.consistency_checker_node(state(REAL_PAPER))
    assert "anlamlı değil" not in result.get("consistency_feedback", "")


def test_an_unsupported_claim_ends_in_needs_review_after_two_rewrites(referee):
    paper = REAL_PAPER + "Random Forest has a higher PR-AUC than KNN.\n"
    assert nodes.consistency_checker_node(state(paper, rounds=2))["research_status"] == "NeedsReview"
