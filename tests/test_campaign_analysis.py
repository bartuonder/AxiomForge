import pytest

from app.campaign.analysis import analyze_campaign
from app.campaign.stats import MIN_DATASETS

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {
        "id": "C1",
        "statement": "Trees beat the MLP",
        "metric": "roc_auc",
        "metrics": ["roc_auc", "pr_auc"],
        "subject": ["RandomForest", "HistGradientBoosting"],
        "other": ["MLP"],
    },
    {
        "id": "C2",
        "statement": "MLP beats LR",
        "metric": "f1",
        "metrics": ["f1"],
        "subject": ["MLP"],
        "other": ["LogisticRegression"],
    },
]
SPEC = {"models": MODELS, "params": {"MLP": {"alpha": 0.01}}, "claims": CLAIMS}


def summary(shift, mlp_default_shift=0.0):
    base = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}
    record = {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in base.items()}
    record["MLP__default"] = {f"{metric}_mean": 0.85 + shift + mlp_default_shift for metric in ("roc_auc", "pr_auc", "f1")}
    record["statistical_conclusion"] = "text"
    return record


def outcome(count, failed=None):
    keys = [f"d{index}" for index in range(count)] + list((failed or {}))
    return {
        "order": keys,
        "datasets": {f"d{index}": {"summary": summary(0.001 * index, mlp_default_shift=-0.01)} for index in range(count)},
        "failed": failed or {},
    }


def test_nine_datasets_support_every_test():
    result = analyze_campaign(SPEC, outcome(9))
    assert result["coverage"]["enough_for_tests"] is True
    assert result["coverage"]["finished"] == [f"d{index}" for index in range(9)]
    assert result["coverage"]["failed"] == {}
    assert result["coverage"]["minimum"] == MIN_DATASETS
    assert result["models"] == MODELS
    assert set(result["pairwise"]) == {"roc_auc", "pr_auc", "f1"}
    assert len(result["pairwise"]["roc_auc"]) == 6
    assert set(result["friedman"]) == {"roc_auc", "pr_auc", "f1"}
    assert result["friedman"]["roc_auc"]["mean_ranks"]["HistGradientBoosting"] == 1.0


def test_the_claims_get_their_verdicts_with_their_id_and_statement():
    result = analyze_campaign(SPEC, outcome(9))
    first, second = result["claims"]
    assert (first["id"], first["statement"], first["verdict"]) == ("C1", "Trees beat the MLP", "replicated")
    assert [row["metric"] for row in first["rows"]] == ["roc_auc", "pr_auc"]
    assert (second["id"], second["verdict"]) == ("C2", "replicated")


def test_the_controls_are_not_models_of_the_comparisons():
    result = analyze_campaign(SPEC, outcome(9))
    names = {name for row in result["pairwise"]["roc_auc"] for name in (row["a"], row["b"])}
    assert names == set(MODELS)


def test_the_parameter_effect_is_tested_across_datasets():
    result = analyze_campaign(SPEC, outcome(9))
    rows = result["parameter_effects"]
    assert [(row["model"], row["metric"]) for row in rows] == [("MLP", "roc_auc"), ("MLP", "pr_auc"), ("MLP", "f1")]
    for row in rows:
        assert row["params"] == {"alpha": 0.01}
        assert row["wins"] == 9
        assert row["mean_difference"] == pytest.approx(0.01)
        assert row["significant"] is True
        assert row["adjusted_p_value"] == pytest.approx(3 * 2 / 2**9)


def test_a_campaign_without_parameters_has_no_effect_rows():
    result = analyze_campaign({**SPEC, "params": {}}, outcome(9))
    assert result["parameter_effects"] == []


def test_a_failed_dataset_is_listed_and_the_rest_is_analysed():
    result = analyze_campaign(SPEC, outcome(8, failed={"dx": {"error": "boom", "attempts": 2}}))
    assert result["coverage"]["finished"] == [f"d{index}" for index in range(8)]
    assert result["coverage"]["failed"] == {"dx": {"error": "boom", "attempts": 2}}
    assert result["coverage"]["requested"][-1] == "dx"
    assert result["claims"][0]["verdict"] == "replicated"


def test_too_few_finished_datasets_make_every_claim_untestable_but_still_reported():
    result = analyze_campaign(SPEC, outcome(4, failed={"dx": {"error": "e", "attempts": 2}, "dy": {"error": "e", "attempts": 2}}))
    assert result["coverage"]["enough_for_tests"] is False
    assert [claim["verdict"] for claim in result["claims"]] == ["not_testable", "not_testable"]
    assert all(row["significant"] is False and row["adjusted_p_value"] is None for row in result["parameter_effects"])
    assert result["friedman"]["roc_auc"]["testable"] is False
    assert result["friedman"]["roc_auc"]["mean_ranks"]["RandomForest"] == 2.0


def test_nothing_finished_is_reported_as_an_error_not_an_exception():
    result = analyze_campaign(SPEC, {"order": ["a", "b"], "datasets": {}, "failed": {"a": {"error": "x", "attempts": 2}, "b": {"error": "x", "attempts": 2}}})
    assert result["error"] == "no dataset finished, so nothing can be compared"
    assert result["coverage"]["finished"] == []
    assert "claims" not in result


def test_a_dataset_that_lacks_a_model_is_reported_as_an_error():
    data = outcome(7)
    del data["datasets"]["d3"]["summary"]["MLP"]
    result = analyze_campaign(SPEC, data)
    assert "d3 has no" in result["error"]
    assert result["coverage"]["finished"][3] == "d3"


def test_the_order_of_the_request_is_kept_in_the_coverage():
    data = outcome(7)
    data["order"] = list(reversed(data["order"]))
    assert analyze_campaign(SPEC, data)["coverage"]["finished"] == [f"d{index}" for index in reversed(range(7))]


def test_the_result_is_plain_data_that_survives_json():
    import json

    json.dumps(analyze_campaign(SPEC, outcome(9)))


def test_the_models_of_the_spec_decide_the_order_of_the_comparisons():
    reversed_spec = {**SPEC, "models": list(reversed(MODELS))}
    rows = analyze_campaign(reversed_spec, outcome(9))["pairwise"]["roc_auc"]
    assert (rows[0]["a"], rows[0]["b"]) == ("LogisticRegression", "MLP")
    assert list(analyze_campaign(reversed_spec, outcome(9))["friedman"]["roc_auc"]["mean_ranks"]) == list(reversed(MODELS))
