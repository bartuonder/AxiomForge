import pytest

import app.graph.nodes as nodes
from app.agents.consistency import instability_issues, unfounded_instability_issues
from app.agents.report import SYSTEM_PROMPT
from app.graph.evidence import instability_sentences

MODELS = ["RandomForest", "LogisticRegression", "KNN"]
CALM = {"unstable": False, "std_threshold": 0.05, "flagged": []}
LR_ONLY = {
    "unstable": True,
    "std_threshold": 0.05,
    "flagged": [{"model": "LogisticRegression", "metric": "f1", "std": 0.063}],
}

REAL_ABSTRACT = "The Random Forest model demonstrated high variance across splits, indicating sensitivity to data partitioning."
REAL_CONCLUSION = "The Random Forest model showed high variance across splits, suggesting sensitivity to data partitioning."


def test_the_real_abstract_and_conclusion_invent_an_instability():
    paper = f"# Abstract\n{REAL_ABSTRACT}\n# Conclusion\n{REAL_CONCLUSION}\n"
    issues = unfounded_instability_issues(paper, CALM, MODELS)
    assert len(issues) == 2
    assert "instability.unstable false" in issues[0]
    assert "high variance across splits" in issues[0]


@pytest.mark.parametrize(
    "sentence",
    [
        "The Random Forest model is unstable.",
        "KNN shows instability across the splits.",
        "A large standard deviation was observed for Logistic Regression.",
        "The F1 score exceeds the threshold for variability.",
        "Results are sensitive to the data split.",
        "Results are sensitive to data partitioning.",
        "Higher variability was seen overall.",
    ],
)
def test_every_instability_wording_is_rejected_when_nothing_was_flagged(sentence):
    assert len(unfounded_instability_issues(f"# Results\n{sentence}\n", CALM, MODELS)) == 1


@pytest.mark.parametrize(
    "sentence",
    [
        "No instability was detected for any model.",
        "The models are not unstable across splits.",
        "Random Forest does not show high variance across splits.",
        "The hypothesis was that Random Forest has high variance across splits.",
        "We wanted to see whether KNN is sensitive to the data split.",
        "Random Forest has higher variance than KNN (variance 0.0007 against 0.0003).",
        "No significant difference in ROC-AUC stability was detected.",
        "Random Forest was more stable than KNN.",
        "The standard deviation stayed below the threshold of 0.05.",
    ],
)
def test_neutral_negated_and_comparative_sentences_pass(sentence):
    assert unfounded_instability_issues(f"# Results\n{sentence}\n", CALM, MODELS) == []


def test_a_flagged_model_may_be_called_unstable():
    paper = "# Results\nLogisticRegression shows high variance across splits (F1 std = 0.063, threshold 0.05).\n"
    assert unfounded_instability_issues(paper, LR_ONLY, MODELS) == []


def test_another_model_may_not_be_called_unstable_when_only_one_is_flagged():
    paper = "# Results\nThe Random Forest model showed high variance across splits.\n"
    issues = unfounded_instability_issues(paper, LR_ONLY, MODELS)
    assert len(issues) == 1
    assert "yalnız LogisticRegression için" in issues[0]
    assert "RandomForest için" in issues[0]


def test_a_sentence_naming_the_flagged_model_among_others_is_accepted():
    paper = "# Results\nLogisticRegression and KNN showed high variance across splits.\n"
    assert unfounded_instability_issues(paper, LR_ONLY, MODELS) == []


def test_a_general_remark_without_a_model_is_accepted_when_something_is_flagged():
    paper = "# Conclusion\nSome results are sensitive to the data split.\n"
    assert unfounded_instability_issues(paper, LR_ONLY, MODELS) == []


def test_the_evidence_sentences_of_a_real_finding_pass_both_instability_checks():
    paper = "# Abstract\nThere was high variance across splits for LogisticRegression.\n# Results\n" + "\n".join(
        instability_sentences(LR_ONLY)
    )
    assert unfounded_instability_issues(paper, LR_ONLY, MODELS) == []
    assert instability_issues(paper, LR_ONLY) == []


def test_a_table_row_is_not_prose():
    table = "| Model | note |\n| --- | --- |\n| Random Forest | high variance across splits |\n"
    assert unfounded_instability_issues(table, CALM, MODELS) == []


@pytest.mark.parametrize("missing", [None, {}, {"flagged": []}])
def test_without_a_finding_record_nothing_is_checked(missing):
    assert unfounded_instability_issues(REAL_ABSTRACT, missing, MODELS) == []


def test_at_most_three_sentences_are_reported():
    paper = "\n".join(f"Model {number} is unstable." for number in range(6))
    assert len(unfounded_instability_issues(paper, CALM, MODELS)) == 3


STATE = {
    "paper_markdown": "",
    "statistical_results": {},
    "statistical_decision": {"instability": CALM},
    "verification_status": "Passed",
    "hypotheses": ["stmt"],
    "experiment_specs": [{"statement": "stmt", "dataset": "customer_churn", "models": MODELS, "params": {}}],
}


def test_the_gate_sends_back_the_real_run_seven_sentences():
    issues = nodes._gate_issues({**STATE, "paper_markdown": f"# Abstract\n{REAL_ABSTRACT}\n"})
    assert any("Doğrulayıcı hiçbir modeli kararsız bulmadı" in issue for issue in issues)


def test_the_gate_names_the_models_of_the_spec():
    state = {**STATE, "statistical_decision": {"instability": LR_ONLY}, "paper_markdown": f"# Abstract\n{REAL_ABSTRACT}\n"}
    issues = nodes._gate_issues(state)
    assert any("Kararsızlık bulgusu yalnız LogisticRegression için" in issue for issue in issues)


def test_the_writer_is_told_to_stay_within_the_finding():
    assert "unstable false ise kararsızlık, yüksek varyans veya bölmeye duyarlılık iddiası kurma" in SYSTEM_PROMPT
    assert "yalnız flagged listesindeki modeller için yaz" in SYSTEM_PROMPT
