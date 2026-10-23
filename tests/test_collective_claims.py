import pytest

import app.graph.nodes as nodes
from app.agents.consistency import collective_claim_issues
from app.graph.evidence import performance_sentences


def row(metric, a, b, difference, significant):
    return {
        "metric": metric,
        "a": a,
        "b": b,
        "mean_difference": difference,
        "effect_size_dz": 1.0 if difference > 0 else -1.0,
        "p_value": 0.01,
        "adjusted_p_value": 0.01 if significant else 0.5,
        "significant": significant,
    }


RF, LR, KNN = "RandomForest", "LogisticRegression", "KNN"
RUN_SIX = [
    row("roc_auc", RF, LR, 0.0415, True),
    row("roc_auc", RF, KNN, 0.0692, True),
    row("roc_auc", LR, KNN, 0.0277, False),
    row("pr_auc", RF, LR, 0.0042, False),
    row("pr_auc", RF, KNN, 0.1204, True),
    row("pr_auc", LR, KNN, 0.1162, True),
    row("f1", RF, LR, 0.0691, True),
    row("f1", RF, KNN, 0.0472, False),
    row("f1", LR, KNN, -0.0219, False),
]

REAL_ABSTRACT = "Random Forest demonstrated higher mean ROC-AUC and PR-AUC compared to the other models."
REAL_CONCLUSION = "Random Forest showed higher performance in both ROC-AUC and PR-AUC compared to the other models."


def test_the_real_abstract_claims_a_pr_auc_lead_that_the_data_does_not_have():
    issues = collective_claim_issues(REAL_ABSTRACT, RUN_SIX)
    assert len(issues) == 1
    assert "PR-AUC" in issues[0]
    assert "RandomForest" in issues[0]
    assert "ROC-AUC için" not in issues[0]


def test_the_same_gap_in_the_conclusion_is_reported_once():
    issues = collective_claim_issues(f"# Abstract\n{REAL_ABSTRACT}\n# Conclusion\n{REAL_CONCLUSION}\n", RUN_SIX)
    assert len(issues) == 1


def test_a_lead_over_every_rival_on_the_named_metric_passes():
    assert collective_claim_issues("Random Forest outperformed all other models on ROC-AUC.", RUN_SIX) == []


def test_a_collective_claim_without_a_metric_must_hold_on_every_metric():
    issues = collective_claim_issues("Random Forest outperformed the other models.", RUN_SIX)
    assert {"PR-AUC", "F1"} == {name for name in ("PR-AUC", "F1") if any(f"{name} için" in issue for issue in issues)}
    assert not any("ROC-AUC için" in issue for issue in issues)


def test_a_collective_claim_that_holds_everywhere_passes():
    dominant = [row(metric, RF, rival, 0.1, True) for metric in ("roc_auc", "pr_auc", "f1") for rival in (LR, KNN)]
    dominant += [row(metric, LR, KNN, 0.01, False) for metric in ("roc_auc", "pr_auc", "f1")]
    assert collective_claim_issues("Random Forest outperformed the other models.", dominant) == []


def test_the_direction_is_checked_for_a_lead_that_points_the_wrong_way():
    reversed_rows = [row(metric, RF, rival, -0.1, True) for metric in ("roc_auc",) for rival in (LR, KNN)]
    reversed_rows += [row("roc_auc", LR, KNN, 0.01, False)]
    assert len(collective_claim_issues("Random Forest was better than the other models on ROC-AUC.", reversed_rows)) == 1


def test_a_collective_deficit_needs_every_pair_to_be_significant_and_lower():
    assert len(collective_claim_issues("KNN had a lower ROC-AUC than the other models.", RUN_SIX)) == 1
    assert collective_claim_issues("KNN had a lower PR-AUC than the other models.", RUN_SIX) == []


@pytest.mark.parametrize(
    "phrase",
    [
        "the other models",
        "all other models",
        "every other model",
        "the remaining models",
        "both other models",
        "the rest",
        "all models",
        "the others",
        "any other classifier",
    ],
)
def test_every_collective_wording_is_recognised(phrase):
    sentence = f"Random Forest had a higher PR-AUC than {phrase}."
    assert len(collective_claim_issues(sentence, RUN_SIX)) == 1


@pytest.mark.parametrize(
    "sentence",
    [
        "Random Forest was not significantly higher than the other models in PR-AUC.",
        "The hypothesis was that Random Forest has a higher PR-AUC than the other models.",
        "We wanted to see whether Random Forest beats the other models in PR-AUC.",
        "Random Forest was more stable than the other models.",
        "The other models performed worse.",
        "Random Forest has a higher mean PR-AUC than KNN (mean difference 0.1204, adjusted p = 1.37e-05, dz = 6.55).",
        "All models were trained on the same splits.",
        "Random Forest trained longer than the other models.",
    ],
)
def test_neutral_negated_and_pairwise_sentences_pass(sentence):
    assert collective_claim_issues(sentence, RUN_SIX) == []


def test_the_evidence_sentences_never_trigger_the_check():
    paper = "\n".join(performance_sentences(RUN_SIX))
    assert collective_claim_issues(paper, RUN_SIX) == []


def test_two_models_have_no_collective_to_check():
    two = [row("roc_auc", RF, LR, 0.1, False)]
    assert collective_claim_issues("Random Forest was better than the other model.", two) == []


def test_without_performance_tests_nothing_is_checked():
    assert collective_claim_issues(REAL_ABSTRACT, []) == []
    assert collective_claim_issues(REAL_ABSTRACT, None) == []


def test_a_table_row_is_not_prose():
    table = "| Model | note |\n| --- | --- |\n| Random Forest higher than the other models | x |\n"
    assert collective_claim_issues(table, RUN_SIX) == []


STATE = {
    "paper_markdown": "",
    "statistical_results": {},
    "statistical_decision": {"performance": RUN_SIX},
    "verification_status": "Passed",
}


def test_the_gate_sends_back_the_real_run_six_sentences():
    issues = nodes._gate_issues({**STATE, "paper_markdown": f"# Abstract\n{REAL_ABSTRACT}\n"})
    assert any("toplu bir iddia" in issue for issue in issues)


def test_the_gate_accepts_a_pairwise_wording():
    paper = "# Abstract\nRandom Forest has a higher mean ROC-AUC than KNN and than LogisticRegression.\n"
    issues = nodes._gate_issues({**STATE, "paper_markdown": paper})
    assert not any("toplu bir iddia" in issue for issue in issues)


def test_the_writer_is_told_not_to_use_collective_wording():
    from app.agents.report import SYSTEM_PROMPT

    assert "'the other models', 'all models', 'the rest' gibi toplu ifadelerle" in SYSTEM_PROMPT
    assert "çift çift yaz" in SYSTEM_PROMPT
