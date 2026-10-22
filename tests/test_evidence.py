import pytest

from app.agents.consistency import (
    direction_conflict,
    hypothesis_issues,
    instability_issues,
    performance_issues,
    reliability_issue,
)
from app.agents.report import SYSTEM_PROMPT, _brief
from app.graph.evidence import (
    evidence_sentences,
    hypothesis_sentences,
    instability_sentences,
    performance_sentences,
)
from app.graph.verifier import (
    hypothesis_verdict,
    instability_finding,
    performance_comparisons,
    stability_decision,
    summarize_seed_runs,
)

HI = [0.90, 0.91, 0.89, 0.92, 0.90, 0.91, 0.90, 0.89, 0.92, 0.91]
LO = [0.70, 0.72, 0.69, 0.71, 0.70, 0.73, 0.68, 0.70, 0.72, 0.71]
NEAR = [0.91, 0.90, 0.92, 0.91, 0.89, 0.92, 0.91, 0.90, 0.90, 0.92]
WILD = [0.95, 0.60, 0.97, 0.70, 0.99] * 2


def row(model, value):
    return {
        "model": model,
        "accuracy": 0.9,
        "f1": value,
        "roc_auc": value,
        "pr_auc": value,
        "train_seconds": 0.1,
        "tn": 175.0,
        "fp": 5.0,
        "fn": 5.0,
        "tp": 15.0,
    }


def decision_for(series, claim=None):
    length = len(next(iter(series.values())))
    runs = [[row(name, series[name][index]) for name in series] for index in range(length)]
    summary = summarize_seed_runs(runs)
    decision = stability_decision(runs)
    decision["instability"] = instability_finding(summary)
    decision["performance"] = performance_comparisons(runs, 1000.0)
    decision["hypothesis"] = hypothesis_verdict(claim, decision)
    return decision


def claim(kind="performance", metric="roc_auc", subject="Hi", other="Lo"):
    return {"kind": kind, "metric": metric, "subject": subject, "other": other}


def test_a_significant_row_becomes_a_complete_sentence_with_the_leader_first():
    rows = [
        {
            "metric": "roc_auc",
            "a": "RandomForest",
            "b": "LogisticRegression",
            "mean_difference": 0.115731,
            "effect_size_dz": 2.2431,
            "adjusted_p_value": 0.004276,
            "significant": True,
        }
    ]
    assert performance_sentences(rows) == [
        "RandomForest has a higher mean ROC-AUC than LogisticRegression "
        "(mean difference 0.1157, adjusted p = 0.00428, dz = 2.24)."
    ]


def test_a_negative_difference_puts_the_other_model_first_and_keeps_the_effect_size_positive():
    rows = [
        {
            "metric": "f1",
            "a": "SVM",
            "b": "KNN",
            "mean_difference": -0.2,
            "effect_size_dz": -3.5,
            "adjusted_p_value": 8.77e-07,
            "significant": True,
        }
    ]
    assert performance_sentences(rows) == [
        "KNN has a higher mean F1 than SVM (mean difference 0.2000, adjusted p = 8.77e-07, dz = 3.50)."
    ]


def test_an_insignificant_row_says_no_difference_was_found():
    rows = [
        {
            "metric": "pr_auc",
            "a": "SVM",
            "b": "KNN",
            "mean_difference": 0.01,
            "effect_size_dz": 0.2,
            "adjusted_p_value": 0.4,
            "significant": False,
        }
    ]
    assert performance_sentences(rows) == ["No significant difference in PR-AUC was found between SVM and KNN (adjusted p = 0.4)."]


def test_unknown_metrics_and_missing_rows_are_skipped():
    assert performance_sentences(None) == []
    assert performance_sentences([]) == []
    assert performance_sentences([{"metric": "accuracy", "a": "A", "b": "B", "adjusted_p_value": 0.1}]) == []


@pytest.mark.parametrize("verdict", ["supported", "contradicted", "inconclusive"])
def test_a_decided_hypothesis_states_its_verdict_with_the_evidence(verdict):
    series = {"Hi": HI, "Lo": LO} if verdict != "inconclusive" else {"Hi": HI, "Near": NEAR}
    subject, other = ("Hi", "Lo") if verdict == "supported" else (("Lo", "Hi") if verdict == "contradicted" else ("Hi", "Near"))
    decision = decision_for(series, claim(subject=subject, other=other))
    sentences = hypothesis_sentences(decision["hypothesis"])
    assert len(sentences) == 1
    assert sentences[0].startswith(f"The hypothesis was {verdict} (")
    assert f"{subject} versus {other} on ROC-AUC" in sentences[0]


def test_a_stability_claim_reports_the_two_variances():
    decision = decision_for({"Wild": WILD, "Steady": ([0.90, 0.91, 0.89, 0.92, 0.90] * 2)}, claim("stability", "roc_auc", "Steady", "Wild"))
    sentence = hypothesis_sentences(decision["hypothesis"])[0]
    assert sentence.startswith("The hypothesis was supported (Steady versus Wild on ROC-AUC variance: variance ")
    assert "against" in sentence


def test_an_untested_hypothesis_says_so_and_no_decision_says_nothing():
    assert hypothesis_sentences({"claim": None, "verdict": "untested", "evidence": {}}) == [
        "The hypothesis could not be tested with this data."
    ]
    assert hypothesis_sentences(None) == []
    assert hypothesis_sentences({}) == []
    assert hypothesis_sentences({"verdict": "unknown"}) == []


def test_instability_gets_one_sentence_per_flagged_metric():
    finding = {
        "unstable": True,
        "std_threshold": 0.05,
        "flagged": [
            {"model": "SVM", "metric": "roc_auc", "std": 0.1794},
            {"model": "KNN", "metric": "f1", "std": 0.0912},
        ],
    }
    assert instability_sentences(finding) == [
        "SVM shows high variance across splits (ROC-AUC std = 0.179, threshold 0.05).",
        "KNN shows high variance across splits (F1 std = 0.091, threshold 0.05).",
    ]
    assert instability_sentences({"unstable": False, "flagged": []}) == []
    assert instability_sentences(None) == []


def test_the_sentences_come_in_a_fixed_order():
    decision = decision_for({"Hi": HI, "Wild": WILD}, claim(subject="Hi", other="Wild"))
    sentences = evidence_sentences(decision)
    assert sentences[0].startswith("The hypothesis was ")
    assert any(sentence.startswith("No significant") or "has a higher mean" in sentence for sentence in sentences[1:4])
    assert "shows high variance across splits" in sentences[-1]
    assert evidence_sentences(None) == []
    assert evidence_sentences({}) == []


def paper_from(decision, verdict_sentence):
    unstable = decision["instability"]["unstable"]
    flagged = decision["instability"]["flagged"]
    abstract = f"We compare two models. {verdict_sentence}"
    if unstable:
        abstract += f" {flagged[0]['model']} shows high variance across splits."
    return (
        "# Abstract\n" + abstract + "\n# Methodology\nWe trained models.\n"
        "# Results\n" + "\n".join(evidence_sentences(decision)) + "\n"
        "# Conclusion\n" + verdict_sentence + "\n"
    )


CASES = {
    "supported": ({"Hi": HI, "Lo": LO}, claim()),
    "contradicted": ({"Hi": HI, "Lo": LO}, claim(subject="Lo", other="Hi")),
    "inconclusive": ({"Hi": HI, "Near": NEAR}, claim(subject="Hi", other="Near")),
    "untested": ({"Hi": HI, "Lo": LO}, None),
    "unstable": ({"Hi": HI, "Wild": WILD}, claim(subject="Hi", other="Wild")),
}


@pytest.mark.parametrize("case", list(CASES))
def test_a_paper_that_copies_the_evidence_sentences_passes_every_check(case):
    series, chosen = CASES[case]
    decision = decision_for(series, chosen)
    verdict = decision["hypothesis"]["verdict"]
    sentence = (
        "The hypothesis could not be tested with this data."
        if verdict == "untested"
        else f"The hypothesis was {verdict}."
    )
    text = paper_from(decision, sentence)
    assert performance_issues(text, decision["performance"]) == []
    assert hypothesis_issues(text, decision["hypothesis"]) == []
    assert instability_issues(text, decision["instability"]) == []
    assert reliability_issue(text, "Passed") == ""
    assert direction_conflict(text, {**decision, "outcome": "tie"}) == ""


def test_the_property_covers_a_run_with_an_instability_finding():
    decision = decision_for(*CASES["unstable"])
    assert decision["instability"]["unstable"] is True
    assert decision["hypothesis"]["verdict"] in {"supported", "contradicted", "inconclusive"}


def test_the_brief_hands_the_evidence_sentences_to_the_writer():
    decision = decision_for(*CASES["supported"])
    state = {"query": "q", "statistical_decision": decision}
    brief = _brief(state, [], "run")
    assert "Evidence sentences" in brief
    for sentence in evidence_sentences(decision):
        assert f"- {sentence}" in brief


def test_the_writer_is_told_to_copy_them_word_for_word():
    assert "Evidence sentences bölümündeki her cümleyi Results içinde aynen kopyala" in SYSTEM_PROMPT
    assert "yeniden yazma" in SYSTEM_PROMPT
