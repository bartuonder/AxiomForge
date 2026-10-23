import pytest

import app.graph.nodes as nodes
from app.agents.consistency import (
    direction_conflict,
    parameter_effect_issues,
    performance_issues,
    table_issues,
)
from app.graph.evidence import effect_sentences


def effect(model="RandomForest", metric="roc_auc", difference=0.0123, dz=0.8, significant=True):
    return {
        "model": model,
        "params": {"n_estimators": 300},
        "metric": metric,
        "mean_difference": difference,
        "effect_size_dz": dz,
        "p_value": 0.001,
        "adjusted_p_value": 0.001,
        "significant": significant,
    }


GAIN = (
    "RandomForest with the listed parameters has a higher mean ROC-AUC than RandomForest with default parameters "
    "(mean difference 0.0123, adjusted p = 0.001, dz = 0.80)."
)


def test_the_copied_evidence_sentence_passes():
    paper = "# Results\n" + "\n".join(effect_sentences([effect()])) + "\n"
    assert parameter_effect_issues(paper, [effect()]) == []


def test_a_missing_sentence_is_flagged():
    issues = parameter_effect_issues("# Results\nNothing about parameters.\n", [effect()])
    assert len(issues) == 1
    assert "RandomForest" in issues[0] and "ROC-AUC" in issues[0]


def test_the_wrong_direction_is_flagged():
    paper = GAIN.replace("higher", "lower")
    assert len(parameter_effect_issues(paper, [effect()])) == 1


def test_a_sentence_that_also_says_the_opposite_is_flagged():
    paper = GAIN.replace("(mean", "and a lower training time (mean")
    assert len(parameter_effect_issues(paper, [effect()])) == 1


def test_a_loss_needs_the_lower_wording():
    loss = effect(difference=-0.02, dz=-0.5)
    assert parameter_effect_issues(GAIN, [loss]) != []
    paper = GAIN.replace("higher", "lower").replace("0.80", "0.50")
    assert parameter_effect_issues(paper, [loss]) == []


def test_a_wrong_effect_size_is_flagged():
    issues = parameter_effect_issues(GAIN.replace("0.80", "0.30"), [effect()])
    assert len(issues) == 1
    assert "0.80" in issues[0]


def test_a_sentence_about_another_metric_does_not_count():
    assert parameter_effect_issues(GAIN.replace("ROC-AUC", "F1"), [effect()]) != []


def test_a_sentence_about_another_model_does_not_count():
    assert parameter_effect_issues(GAIN.replace("RandomForest", "XGBoost"), [effect()]) != []


def test_a_negated_sentence_does_not_report_the_effect():
    paper = GAIN.replace("has a higher", "has not a higher")
    assert parameter_effect_issues(paper, [effect()]) != []


def test_a_claimed_gain_without_significance_is_flagged():
    issues = parameter_effect_issues(GAIN, [effect(significant=False)])
    assert len(issues) == 1
    assert "significant false" in issues[0]


def test_the_no_effect_sentence_is_accepted_when_not_significant():
    paper = "\n".join(effect_sentences([effect(significant=False)]))
    assert parameter_effect_issues(paper, [effect(significant=False)]) == []


def test_nothing_is_demanded_without_effects():
    assert parameter_effect_issues("anything", None) == []
    assert parameter_effect_issues("anything", []) == []


def test_unknown_metrics_are_skipped():
    assert parameter_effect_issues("anything", [effect(metric="accuracy")]) == []


def test_an_effect_sentence_does_not_satisfy_the_model_comparison_check():
    performance = [
        {
            "metric": "roc_auc",
            "a": "RandomForest",
            "b": "XGBoost",
            "mean_difference": 0.05,
            "effect_size_dz": 0.8,
            "adjusted_p_value": 0.001,
            "significant": True,
        }
    ]
    assert len(performance_issues(GAIN, performance)) == 1


def test_a_default_comparison_is_not_a_direction_conflict():
    paper = "RandomForest with the listed parameters outperforms RandomForest with default parameters."
    assert direction_conflict(paper, {"outcome": "tie"}) == ""
    assert direction_conflict("RandomForest outperforms XGBoost.", {"outcome": "tie"}) != ""


RESULTS = {
    "RandomForest": {"f1_mean": 0.9, "f1_std": 0.01},
    "RandomForest__default": {"f1_mean": 0.8, "f1_std": 0.02},
}


def table(rows):
    return "| Model | F1 |\n| --- | --- |\n" + "\n".join(rows) + "\n"


def test_the_default_row_is_matched_by_its_display_name():
    paper = table(["| RandomForest | 0.9000 ± 0.0100 |", "| RandomForest (default) | 0.8000 ± 0.0200 |"])
    issues = table_issues(paper, RESULTS)
    assert [issue for issue in issues if "satırı" in issue or "hücresi" in issue] == []


def test_a_missing_default_row_is_named_with_its_display_name():
    issues = table_issues(table(["| RandomForest | 0.9000 ± 0.0100 |"]), RESULTS)
    assert any("RandomForest (default) satırı yok" in issue for issue in issues)
    assert not any("__default" in issue for issue in issues)


def test_a_wrong_default_cell_is_reported():
    paper = table(["| RandomForest | 0.9000 ± 0.0100 |", "| RandomForest (default) | 0.7000 ± 0.0200 |"])
    issues = table_issues(paper, RESULTS)
    assert any("RandomForest (default) için F1 hücresi" in issue for issue in issues)


STATE = {
    "paper_markdown": "",
    "statistical_results": {},
    "statistical_decision": {"parameter_effects": [effect()]},
    "verification_status": "Passed",
}


def test_the_gate_asks_for_the_missing_effect_sentence():
    issues = nodes._gate_issues({**STATE, "paper_markdown": "# Abstract\nx\n# Results\ny\n"})
    assert any("parametrelerin varsayılana göre etkisi" in issue for issue in issues)


@pytest.mark.parametrize("paper", [GAIN])
def test_the_gate_accepts_the_copied_sentence(paper):
    issues = nodes._gate_issues({**STATE, "paper_markdown": paper})
    assert not any("parametrelerin" in issue for issue in issues)
