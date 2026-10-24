import re

import pytest

import app.graph.nodes as nodes
from app.agents.consistency import (
    SIMILARITY_LIMIT,
    method_issues,
    repetition_issues,
    summary_completeness_issues,
)
from app.agents.report import SYSTEM_PROMPT, _brief
from app.graph.evidence import evidence_sentences, summary_sentences

LEADER = {
    "model": "HistGradientBoosting",
    "metric": "roc_auc",
    "mean": 0.91212,
    "not_significant_against": ["LogisticRegression"],
}


def effect(model, metric, significant, difference=0.02):
    return {
        "model": model,
        "params": {"x": 1},
        "metric": metric,
        "mean_difference": difference,
        "effect_size_dz": 3.0 if difference > 0 else -3.0,
        "p_value": 0.001,
        "adjusted_p_value": 0.001 if significant else 0.9,
        "significant": significant,
    }


RUN_TEN = {
    "leader": LEADER,
    "parameter_effects": [
        effect("KNN", "roc_auc", True, 0.0216),
        effect("KNN", "pr_auc", True, 0.0421),
        effect("KNN", "f1", False, -0.0106),
        effect("HistGradientBoosting", "roc_auc", False, 0.0011),
    ],
}


def words(sentence):
    return set(re.findall(r"[a-z0-9]+", sentence.lower()))


def similarity(first, second):
    return len(words(first) & words(second)) / len(words(first) | words(second))


def test_the_run_ten_decision_gets_one_leader_and_one_effect_sentence_for_each_section():
    sentences = summary_sentences(RUN_TEN)
    assert sentences["Abstract"] == [
        "HistGradientBoosting had the highest mean ROC-AUC (0.9121), but its lead over LogisticRegression "
        "is not statistically significant.",
        "KNN with the listed parameters had a higher mean ROC-AUC and PR-AUC than KNN with default parameters.",
    ]
    assert sentences["Conclusion"] == [
        "Averaged over the ten splits, the strongest ROC-AUC (0.9121) came from HistGradientBoosting, "
        "although no statistically significant lead over LogisticRegression was established.",
        "Compared with default parameters, the listed parameters raised KNN's ROC-AUC and PR-AUC.",
    ]


CASES = {
    "run ten": RUN_TEN,
    "clear leader": {"leader": {**LEADER, "not_significant_against": []}, "parameter_effects": []},
    "three rivals": {"leader": {**LEADER, "not_significant_against": ["A", "B", "C"]}, "parameter_effects": []},
    "lowered effect": {"leader": None, "parameter_effects": [effect("KNN", "f1", True, -0.05)]},
    "all three metrics": {
        "leader": None,
        "parameter_effects": [effect("RandomForest", metric, True) for metric in ("roc_auc", "pr_auc", "f1")],
    },
    "two models": {
        "leader": LEADER,
        "parameter_effects": [effect("KNN", "roc_auc", True), effect("LogisticRegression", "pr_auc", True, -0.01)],
    },
}


@pytest.mark.parametrize("case", list(CASES))
def test_the_two_lists_say_the_same_things_in_clearly_different_words(case):
    sentences = summary_sentences(CASES[case])
    assert len(sentences["Abstract"]) == len(sentences["Conclusion"])
    for first, second in zip(sentences["Abstract"], sentences["Conclusion"]):
        assert first != second
        assert similarity(first, second) < SIMILARITY_LIMIT - 0.2


@pytest.mark.parametrize("case", list(CASES))
def test_each_list_alone_satisfies_the_completeness_check_for_its_section(case):
    decision = CASES[case]
    sentences = summary_sentences(decision)
    text = "# Abstract\n" + " ".join(sentences["Abstract"]) + "\n# Conclusion\n" + " ".join(sentences["Conclusion"]) + "\n"
    assert summary_completeness_issues(text, decision["leader"], decision["parameter_effects"]) == []


@pytest.mark.parametrize("case", list(CASES))
def test_copying_each_list_into_its_own_section_raises_no_repetition(case):
    sentences = summary_sentences(CASES[case])
    text = (
        "# Abstract\nWe compared several models. "
        + " ".join(sentences["Abstract"])
        + " The hypothesis was inconclusive.\n# Conclusion\nThe overall picture is mixed. "
        + " ".join(sentences["Conclusion"])
        + " The hypothesis was inconclusive.\n"
    )
    assert repetition_issues(text) == []


def test_putting_the_abstract_list_in_both_sections_is_still_caught():
    sentences = summary_sentences(RUN_TEN)
    text = "# Abstract\n" + " ".join(sentences["Abstract"]) + "\n# Conclusion\n" + " ".join(sentences["Abstract"]) + "\n"
    assert len(repetition_issues(text)) >= 1


def test_mixed_directions_get_their_own_sentence_each():
    decision = {
        "leader": None,
        "parameter_effects": [effect("KNN", "roc_auc", True, 0.02), effect("KNN", "f1", True, -0.03)],
    }
    abstract = summary_sentences(decision)["Abstract"]
    assert abstract == [
        "KNN with the listed parameters had a higher mean ROC-AUC than KNN with default parameters.",
        "KNN with the listed parameters had a lower mean F1 than KNN with default parameters.",
    ]
    assert summary_sentences(decision)["Conclusion"][1].endswith("lowered KNN's F1.")


def test_nothing_is_written_without_a_leader_or_a_significant_effect():
    assert summary_sentences(None) == {"Abstract": [], "Conclusion": []}
    assert summary_sentences({}) == {"Abstract": [], "Conclusion": []}
    quiet = {"leader": None, "parameter_effects": [effect("KNN", "roc_auc", False)]}
    assert summary_sentences(quiet) == {"Abstract": [], "Conclusion": []}


def test_unknown_metrics_are_skipped():
    decision = {"leader": None, "parameter_effects": [effect("KNN", "accuracy", True)]}
    assert summary_sentences(decision) == {"Abstract": [], "Conclusion": []}
    assert summary_sentences({"leader": {**LEADER, "metric": "accuracy"}}) == {"Abstract": [], "Conclusion": []}


def test_the_brief_hands_each_list_to_the_writer_under_its_own_heading():
    state = {"query": "q", "statistical_decision": RUN_TEN}
    brief = _brief(state, [], "run")
    abstract_part = brief.split("Abstract sentences")[1].split("Conclusion sentences")[0]
    conclusion_part = brief.split("Conclusion sentences")[1].split("Final code")[0]
    for sentence in summary_sentences(RUN_TEN)["Abstract"]:
        assert sentence in abstract_part and sentence not in conclusion_part
    for sentence in summary_sentences(RUN_TEN)["Conclusion"]:
        assert sentence in conclusion_part and sentence not in abstract_part


def test_a_brief_without_a_decision_has_two_empty_lists():
    brief = _brief({"query": "q"}, [], "run")
    assert "Abstract sentences" in brief and "Conclusion sentences" in brief


def test_the_notices_point_to_the_prepared_sentences():
    issues = summary_completeness_issues("# Abstract\nA.\n# Conclusion\nC.\n", LEADER, RUN_TEN["parameter_effects"])
    assert all("sentences' listesinde" in issue for issue in issues)
    assert any("Abstract sentences" in issue for issue in issues)
    assert any("Conclusion sentences" in issue for issue in issues)


def build_paper(decision):
    sentences = summary_sentences(decision)
    return (
        "# Abstract\nThis study compares four models. "
        + " ".join(sentences["Abstract"])
        + " The hypothesis was contradicted.\n# Introduction\nContext.\n# Methodology\n"
        "The models were evaluated on 10 repeated stratified train/test splits. No data leakage or execution errors were detected.\n"
        "# Results\n" + "\n".join(evidence_sentences(decision)) + "\n# Conclusion\nThe evidence is mixed. "
        + " ".join(sentences["Conclusion"])
        + " The hypothesis was contradicted.\n"
    )


def test_a_paper_that_copies_the_prepared_sentences_passes_the_whole_gate():
    decision = {
        **RUN_TEN,
        "n_splits": 10,
        "outcome": "tie",
        "instability": {"unstable": False, "std_threshold": 0.05, "flagged": []},
        "performance": [
            {"metric": "roc_auc", "a": "HistGradientBoosting", "b": "KNN", "mean_difference": 0.04, "effect_size_dz": 8.0, "adjusted_p_value": 0.001, "significant": True},
            {"metric": "roc_auc", "a": "HistGradientBoosting", "b": "LogisticRegression", "mean_difference": 0.0075, "effect_size_dz": 0.6, "adjusted_p_value": 0.08, "significant": False},
            {"metric": "roc_auc", "a": "LogisticRegression", "b": "KNN", "mean_difference": 0.03, "effect_size_dz": 6.0, "adjusted_p_value": 0.001, "significant": True},
        ],
        "hypothesis": {
            "claim": {"kind": "performance", "metric": "pr_auc", "subject": "KNN", "other": "HistGradientBoosting"},
            "verdict": "contradicted",
            "evidence": {"mean_difference": -0.13, "effect_size_dz": -10.9, "adjusted_p_value": 0.001},
        },
    }
    state = {
        "paper_markdown": build_paper(decision),
        "statistical_results": {},
        "statistical_decision": decision,
        "verification_status": "Passed",
        "hypotheses": ["stmt"],
        "experiment_specs": [
            {"statement": "stmt", "dataset": "adult_income", "models": ["KNN", "HistGradientBoosting", "LogisticRegression"],
             "params": {"KNN": {"n_neighbors": 10}}}
        ],
    }
    issues = nodes._gate_issues(state)
    assert issues == []


def test_the_writer_is_told_to_keep_the_two_lists_apart():
    assert "kasten farklı sözcüklerle söyler, birini diğer bölüme koyma" in SYSTEM_PROMPT
    assert method_issues("# Methodology\nThe models were evaluated on 10 repeated stratified train/test splits.\n", 10) == []
