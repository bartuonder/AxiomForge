import numpy as np
import pytest
from scipy import stats

from app.campaign.stats import (
    ALPHA,
    MIN_DATASETS,
    CampaignStatsError,
    claim_verdict,
    compare_scores,
    family_scores,
    friedman_test,
    pairwise_comparisons,
    score_matrix,
)


def results(columns, metrics=("roc_auc", "pr_auc", "f1")):
    count = len(next(iter(columns.values())))
    return {
        f"d{index}": {
            **{name: {f"{metric}_mean": values[index] for metric in metrics} for name, values in columns.items()},
            "statistical_conclusion": "text",
        }
        for index in range(count)
    }


def test_the_matrix_keeps_the_dataset_and_model_order_and_ignores_controls_and_text():
    data = results({"A": [0.9, 0.8], "B": [0.7, 0.6]})
    for record in data.values():
        record["A__default"] = {"roc_auc_mean": 0.99}
    datasets, names, matrix = score_matrix(data, "roc_auc")
    assert datasets == ["d0", "d1"]
    assert names == ["A", "B"]
    assert matrix.tolist() == [[0.9, 0.7], [0.8, 0.6]]


def test_a_chosen_model_order_is_respected():
    _, names, matrix = score_matrix(results({"A": [0.9], "B": [0.7]}), "roc_auc", ["B", "A"])
    assert names == ["B", "A"] and matrix.tolist() == [[0.7, 0.9]]


def test_a_missing_mean_or_no_results_is_an_error():
    data = results({"A": [0.9, 0.8], "B": [0.7, 0.6]})
    del data["d1"]["B"]
    with pytest.raises(CampaignStatsError, match="d1 has no roc_auc mean"):
        score_matrix(data, "roc_auc")
    with pytest.raises(CampaignStatsError, match="no dataset results"):
        score_matrix({}, "roc_auc")


def test_a_family_is_scored_by_its_best_member_on_each_dataset():
    matrix = np.array([[0.9, 0.7, 0.8], [0.6, 0.9, 0.5]])
    assert family_scores(matrix, ["A", "B", "C"], ["A", "B"]).tolist() == [0.9, 0.9]
    assert family_scores(matrix, ["A", "B", "C"], ["C"]).tolist() == [0.8, 0.5]


def test_an_unknown_or_empty_family_is_an_error():
    matrix = np.array([[0.9, 0.7]])
    with pytest.raises(CampaignStatsError, match="Z"):
        family_scores(matrix, ["A", "B"], ["A", "Z"])
    with pytest.raises(CampaignStatsError):
        family_scores(matrix, ["A", "B"], [])


def test_eight_wins_out_of_eight_give_the_smallest_exact_p_value():
    result = compare_scores(np.arange(1, 9) + 1.0, np.arange(1, 9) * 0.0 + 1.0 - 0.5 + np.arange(8) * 0.0)
    assert result["wins"] == 8 and result["losses"] == 0 and result["ties"] == 0
    assert result["testable"] is True
    assert result["p_value"] == pytest.approx(2 / 2**8)
    assert result["rank_biserial"] == pytest.approx(1.0)


def test_five_datasets_can_never_reach_significance_so_they_are_not_testable():
    result = compare_scores(np.ones(5) * 0.9, np.ones(5) * 0.5)
    assert result["p_value"] == pytest.approx(2 / 2**5)
    assert result["p_value"] > ALPHA
    assert result["testable"] is False
    assert MIN_DATASETS == 6


def test_the_smallest_testable_sample_is_six_datasets():
    result = compare_scores(np.ones(6) * 0.9, np.ones(6) * 0.5)
    assert result["p_value"] == pytest.approx(2 / 2**6)
    assert result["p_value"] < ALPHA
    assert result["testable"] is True


def test_it_agrees_with_scipy_on_the_classic_wilcoxon_example():
    differences = np.array([6, 8, 14, 16, 23, 24, 28, 29, 41, -48, 49, 56, 60, -67, 75], dtype=float)
    result = compare_scores(differences, np.zeros_like(differences))
    expected = stats.wilcoxon(differences).pvalue
    assert result["p_value"] == pytest.approx(expected)
    assert 0.04 < result["p_value"] < 0.042
    assert result["wins"] == 13 and result["losses"] == 2


def test_zero_differences_are_counted_as_ties_and_dropped_from_the_test():
    first = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1])
    second = first - np.array([0.1, 0.2, 0.3, 0.0, 0.0, 0.4, 0.5, 0.6, 0.7])
    result = compare_scores(first, second)
    assert result["ties"] == 2
    assert result["wins"] == 7
    assert result["testable"] is True


def test_identical_scores_give_p_one_and_no_effect():
    result = compare_scores(np.ones(8), np.ones(8))
    assert result["p_value"] == 1.0
    assert result["rank_biserial"] == 0.0
    assert result["testable"] is False
    assert result["median_difference"] == 0.0


def test_a_mixed_result_has_an_intermediate_rank_biserial_correlation():
    differences = np.array([1.0, 2.0, 3.0, 4.0, 5.0, -6.0])
    result = compare_scores(differences, np.zeros(6))
    assert result["rank_biserial"] == pytest.approx((15 - 6) / 21)
    assert result["median_difference"] == pytest.approx(2.5)
    assert result["mean_difference"] == pytest.approx(1.5)


def test_the_direction_flips_the_sign_of_the_effect_not_the_p_value():
    first, second = np.arange(8) + 1.0, np.zeros(8)
    forward = compare_scores(first, second)
    backward = compare_scores(second, first)
    assert forward["p_value"] == pytest.approx(backward["p_value"])
    assert forward["rank_biserial"] == pytest.approx(-backward["rank_biserial"])


def test_unequal_vectors_are_an_error():
    with pytest.raises(CampaignStatsError):
        compare_scores(np.ones(3), np.ones(4))


ORDERED = {"A": [0.95 - 0.001 * i for i in range(9)], "B": [0.85 - 0.001 * i for i in range(9)], "C": [0.75 - 0.001 * i for i in range(9)]}


def test_three_models_in_the_same_order_everywhere_are_all_significant_after_holm():
    rows = pairwise_comparisons(results(ORDERED), "roc_auc")
    assert [(row["a"], row["b"]) for row in rows] == [("A", "B"), ("A", "C"), ("B", "C")]
    for row in rows:
        assert row["p_value"] == pytest.approx(2 / 2**9)
        assert row["adjusted_p_value"] == pytest.approx(3 * 2 / 2**9)
        assert row["significant"] is True
        assert row["wins"] == 9


def test_holm_is_applied_only_to_the_testable_pairs():
    data = results({"A": [0.9] * 9, "B": [0.8] * 9, "C": [0.7] * 9})
    rows = pairwise_comparisons(data, "roc_auc")
    assert [round(row["adjusted_p_value"], 6) for row in rows] == [round(3 * 2 / 2**9, 6)] * 3
    small = pairwise_comparisons(results({"A": [0.9] * 4, "B": [0.8] * 4}), "roc_auc")
    assert small[0]["adjusted_p_value"] is None and small[0]["significant"] is False


def test_pairwise_comparisons_follow_the_requested_metric():
    data = results({"A": [0.9] * 8, "B": [0.8] * 8})
    for record in data.values():
        record["A"]["f1_mean"] = 0.1
        record["B"]["f1_mean"] = 0.5
    assert pairwise_comparisons(data, "roc_auc")[0]["median_difference"] > 0
    assert pairwise_comparisons(data, "f1")[0]["median_difference"] < 0


def test_friedman_matches_scipy_and_ranks_the_best_model_first():
    result = friedman_test(results(ORDERED), "roc_auc")
    assert result["mean_ranks"] == {"A": 1.0, "B": 2.0, "C": 3.0}
    assert result["statistic"] == pytest.approx(18.0)
    assert result["p_value"] == pytest.approx(stats.chi2.sf(18.0, 2))
    assert result["significant"] is True and result["testable"] is True
    columns = [np.array(values) for values in ORDERED.values()]
    assert result["p_value"] == pytest.approx(stats.friedmanchisquare(*columns).pvalue)


def test_friedman_needs_three_models_and_five_datasets():
    two = friedman_test(results({"A": [0.9] * 8, "B": [0.8] * 8}), "roc_auc")
    few = friedman_test(results({"A": [0.9] * 4, "B": [0.8] * 4, "C": [0.7] * 4}), "roc_auc")
    for result in (two, few):
        assert result["testable"] is False
        assert result["p_value"] is None and result["statistic"] is None and result["significant"] is False
    assert few["mean_ranks"] == {"A": 1.0, "B": 2.0, "C": 3.0}


def test_equal_scores_share_their_rank():
    result = friedman_test(results({"A": [0.9] * 6, "B": [0.9] * 6, "C": [0.7] * 6}), "roc_auc")
    assert result["mean_ranks"] == {"A": 1.5, "B": 1.5, "C": 3.0}


TREES = {"RandomForest": [0.90 + 0.001 * i for i in range(9)], "HistGradientBoosting": [0.92 + 0.001 * i for i in range(9)],
         "MLP": [0.85 + 0.001 * i for i in range(9)], "LogisticRegression": [0.80 + 0.001 * i for i in range(9)]}
CLAIM = {"metric": "roc_auc", "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]}


def test_a_family_that_wins_everywhere_replicates_the_claim():
    result = claim_verdict(results(TREES), CLAIM)
    assert result["verdict"] == "replicated"
    row = result["rows"][0]
    assert row["verdict"] == "replicated" and row["wins"] == 9 and row["significant"] is True
    assert row["adjusted_p_value"] == pytest.approx(2 / 2**9)


def test_a_family_that_loses_everywhere_reverses_the_claim():
    result = claim_verdict(results(TREES), {**CLAIM, "subject": ["MLP"], "other": ["RandomForest", "HistGradientBoosting"]})
    assert result["verdict"] == "contradicted"


def test_a_mixed_picture_is_inconclusive():
    mixed = {"A": [0.9, 0.7, 0.9, 0.7, 0.9, 0.7, 0.9, 0.7], "B": [0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]}
    result = claim_verdict(results(mixed), {"metric": "roc_auc", "subject": ["A"], "other": ["B"]})
    assert result["verdict"] == "inconclusive"
    assert result["rows"][0]["wins"] == 4 and result["rows"][0]["testable"] is True


def test_too_few_datasets_make_the_claim_not_testable():
    result = claim_verdict(results({k: v[:5] for k, v in TREES.items()}), CLAIM)
    assert result["verdict"] == "not_testable"
    assert result["rows"][0]["wins"] == 5


def test_a_claim_over_several_metrics_can_be_partially_replicated():
    data = results(TREES)
    for index, record in enumerate(data.values()):
        record["RandomForest"]["f1_mean"] = 0.5 + (0.1 if index % 2 else -0.1)
        record["HistGradientBoosting"]["f1_mean"] = 0.5 + (0.1 if index % 2 else -0.1)
        record["MLP"]["f1_mean"] = 0.5
    result = claim_verdict(data, {**CLAIM, "metrics": ["roc_auc", "f1"]})
    assert [row["verdict"] for row in result["rows"]] == ["replicated", "inconclusive"]
    assert result["verdict"] == "partially_replicated"


def test_holm_is_applied_across_the_metrics_of_one_claim():
    data = results(TREES)
    result = claim_verdict(data, {**CLAIM, "metrics": ["roc_auc", "pr_auc"]})
    assert [row["adjusted_p_value"] for row in result["rows"]] == [pytest.approx(2 * 2 / 2**9)] * 2
    assert result["verdict"] == "replicated"


def test_the_claim_is_returned_with_the_verdict():
    assert claim_verdict(results(TREES), CLAIM)["claim"] == CLAIM
