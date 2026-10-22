import pytest

from app.graph.verifier import hypothesis_verdict, performance_comparisons, stability_decision

HI = [0.90, 0.91, 0.89, 0.92, 0.90, 0.91, 0.90, 0.89, 0.92, 0.91]
LO = [0.70, 0.72, 0.69, 0.71, 0.70, 0.73, 0.68, 0.70, 0.72, 0.71]
NEAR = [0.91, 0.90, 0.92, 0.91, 0.89, 0.92, 0.91, 0.90, 0.90, 0.92]
WILD = [0.95, 0.60, 0.97, 0.70, 0.99] * 2
STEADY = [0.90, 0.91, 0.89, 0.92, 0.90] * 2


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


def decision_for(series):
    length = len(next(iter(series.values())))
    runs = [[row(name, series[name][index]) for name in series] for index in range(length)]
    decision = stability_decision(runs)
    decision["performance"] = performance_comparisons(runs, 1000.0)
    return decision


def claim(kind="performance", metric="roc_auc", subject="Hi", other="Lo"):
    return {"kind": kind, "metric": metric, "subject": subject, "other": other}


def test_a_higher_metric_with_a_significant_gap_is_supported():
    result = hypothesis_verdict(claim(), decision_for({"Hi": HI, "Lo": LO}))
    assert result["verdict"] == "supported"
    assert result["evidence"]["mean_difference"] > 0.15
    assert result["evidence"]["adjusted_p_value"] < 0.05
    assert result["evidence"]["effect_size_dz"] > 0
    assert result["claim"] == claim()


def test_a_lower_metric_with_a_significant_gap_is_contradicted():
    result = hypothesis_verdict(claim(subject="Lo", other="Hi"), decision_for({"Hi": HI, "Lo": LO}))
    assert result["verdict"] == "contradicted"
    assert result["evidence"]["mean_difference"] < -0.15
    assert result["evidence"]["effect_size_dz"] < 0


@pytest.mark.parametrize("order", [("Hi", "Lo"), ("Lo", "Hi")])
def test_the_verdict_does_not_depend_on_the_order_the_models_were_compared_in(order):
    series = {name: {"Hi": HI, "Lo": LO}[name] for name in order}
    decision = decision_for(series)
    assert hypothesis_verdict(claim(), decision)["verdict"] == "supported"
    assert hypothesis_verdict(claim(subject="Lo", other="Hi"), decision)["verdict"] == "contradicted"


def test_an_insignificant_gap_is_inconclusive():
    decision = decision_for({"Hi": HI, "Near": NEAR})
    result = hypothesis_verdict(claim(other="Near"), decision)
    assert result["verdict"] == "inconclusive"
    assert result["evidence"]["adjusted_p_value"] >= 0.05


@pytest.mark.parametrize("metric", ["roc_auc", "pr_auc", "f1"])
def test_each_tested_metric_can_carry_a_claim(metric):
    result = hypothesis_verdict(claim(metric=metric), decision_for({"Hi": HI, "Lo": LO}))
    assert result["verdict"] == "supported"
    assert result["evidence"]["metric"] == metric


def test_the_evidence_comes_from_the_claimed_metric_only():
    decision = decision_for({"Hi": HI, "Lo": LO})
    for item in decision["performance"]:
        if item["metric"] == "pr_auc":
            item["significant"] = False
            item["adjusted_p_value"] = 0.9
    assert hypothesis_verdict(claim(metric="pr_auc"), decision)["verdict"] == "inconclusive"
    assert hypothesis_verdict(claim(metric="roc_auc"), decision)["verdict"] == "supported"


def test_a_clearly_lower_variance_makes_a_stability_claim_supported():
    decision = decision_for({"Wild": WILD, "Steady": STEADY})
    result = hypothesis_verdict(claim("stability", "roc_auc", "Steady", "Wild"), decision)
    assert result["verdict"] == "supported"
    assert result["evidence"]["variance_subject"] < result["evidence"]["variance_other"]
    assert result["evidence"]["adjusted_p_value"] < 0.05


def test_the_wrong_way_round_a_stability_claim_is_contradicted():
    decision = decision_for({"Wild": WILD, "Steady": STEADY})
    result = hypothesis_verdict(claim("stability", "roc_auc", "Wild", "Steady"), decision)
    assert result["verdict"] == "contradicted"
    assert result["evidence"]["variance_subject"] > result["evidence"]["variance_other"]


def test_similar_variances_leave_a_stability_claim_inconclusive():
    decision = decision_for({"Hi": HI, "Near": NEAR})
    result = hypothesis_verdict(claim("stability", "roc_auc", "Hi", "Near"), decision)
    assert result["verdict"] == "inconclusive"


def test_the_stability_verdict_does_not_depend_on_the_comparison_order():
    for order in (("Wild", "Steady"), ("Steady", "Wild")):
        decision = decision_for({name: {"Wild": WILD, "Steady": STEADY}[name] for name in order})
        assert hypothesis_verdict(claim("stability", "roc_auc", "Steady", "Wild"), decision)["verdict"] == "supported"


def test_no_claim_leaves_the_hypothesis_untested():
    result = hypothesis_verdict(None, decision_for({"Hi": HI, "Lo": LO}))
    assert result == {"claim": None, "verdict": "untested", "evidence": {}}


def test_a_claim_about_a_pair_that_was_not_compared_is_untested():
    decision = decision_for({"Hi": HI, "Lo": LO})
    assert hypothesis_verdict(claim(subject="Hi", other="Ghost"), decision)["verdict"] == "untested"
    assert hypothesis_verdict(claim("stability", "roc_auc", "Hi", "Ghost"), decision)["verdict"] == "untested"


def test_too_few_splits_leave_every_claim_untested():
    decision = decision_for({"Hi": HI[:2], "Lo": LO[:2]})
    assert hypothesis_verdict(claim(), decision)["verdict"] == "untested"
    assert hypothesis_verdict(claim("stability", "roc_auc", "Hi", "Lo"), decision)["verdict"] == "untested"


def test_a_decision_without_any_tests_is_untested():
    assert hypothesis_verdict(claim(), {})["verdict"] == "untested"
    assert hypothesis_verdict(claim("stability", "roc_auc", "Hi", "Lo"), {"comparisons": None})["verdict"] == "untested"
