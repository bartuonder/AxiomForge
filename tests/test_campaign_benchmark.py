import pytest

from app.campaign.benchmark import CASES, REVERSED, TRUE, benchmark_claims, benchmark_models, benchmark_spec, score_campaign, score_plan
from app.campaign.protocol import ESTIMATORS
from app.datasets import benchmark_keys


def analysis(verdicts):
    return {"claims": [{"id": key, "verdict": value} for key, value in verdicts.items()]}


def perfect():
    return analysis({case["id"]: case["expected"] for case in CASES})


def plan(*claims):
    return {"spec": {"claims": [{"subject": list(subject), "other": list(other)} for subject, other in claims]}}


class TestCases:
    def test_ten_cases_half_of_them_reversed(self):
        assert len(CASES) == 10 and [case["expected"] for case in CASES].count(TRUE) == 5 and [case["expected"] for case in CASES].count(REVERSED) == 5

    def test_ids_are_unique(self):
        assert len({case["id"] for case in CASES}) == 10

    def test_every_reversed_case_mirrors_a_true_comparison_or_its_own_pair(self):
        pairs = {(tuple(case["subject"]), tuple(case["other"])) for case in CASES if case["expected"] == TRUE}
        mirrored = {(tuple(case["other"]), tuple(case["subject"])) for case in CASES if case["expected"] == REVERSED}
        assert len(pairs & mirrored) >= 3

    def test_every_model_is_runnable_and_listed_once(self):
        models = benchmark_models()
        assert len(models) == len(set(models)) and set(models) <= set(ESTIMATORS)

    def test_the_models_follow_the_first_use_order(self):
        assert benchmark_models()[:2] == ["RandomForest", "DecisionTree"]

    def test_the_query_names_the_claim_and_ends_with_a_full_stop(self):
        assert all(case["query"].endswith(".") for case in CASES)


class TestSpec:
    def test_the_claims_cover_all_metrics_and_drop_the_full_stop(self):
        claims = benchmark_claims()
        assert [claim["id"] for claim in claims] == [case["id"] for case in CASES]
        assert all(claim["metrics"] == ["roc_auc", "pr_auc", "f1"] and not claim["statement"].endswith(".") for claim in claims)

    def test_the_spec_is_valid_and_uses_the_benchmark_datasets(self):
        spec = benchmark_spec()
        assert spec["datasets"] == benchmark_keys() and spec["models"] == benchmark_models() and len(spec["claims"]) == 10

    def test_the_spec_keeps_no_source_and_no_tuning(self):
        spec = benchmark_spec()
        assert "title" not in spec["source"] and not spec["tuning"] and not spec["params"]

    def test_a_dataset_count_limits_the_datasets(self):
        assert len(benchmark_spec(dataset_count=7)["datasets"]) == 7

    def test_an_unknown_pool_is_refused(self):
        with pytest.raises(ValueError, match="pool"):
            benchmark_spec("nope")


class TestScoreCampaign:
    def test_a_perfect_campaign_scores_one(self):
        score = score_campaign(perfect())
        assert score["accuracy"] == 1.0 and score["correct"] == 10 and score["wrong"] == 0 and score["undecided"] == 0 and score["total"] == 10

    def test_an_opposite_verdict_is_wrong(self):
        verdicts = {case["id"]: case["expected"] for case in CASES}
        verdicts["B1"] = REVERSED
        score = score_campaign(analysis(verdicts))
        assert score["wrong"] == 1 and score["correct"] == 9 and score["rows"][0]["outcome"] == "wrong"

    @pytest.mark.parametrize("verdict", ["inconclusive", "partially_replicated", "not_testable"])
    def test_a_missing_decision_is_undecided_not_wrong(self, verdict):
        verdicts = {case["id"]: case["expected"] for case in CASES}
        verdicts["B6"] = verdict
        score = score_campaign(analysis(verdicts))
        assert score["undecided"] == 1 and score["wrong"] == 0 and score["rows"][5]["outcome"] == "undecided"

    def test_a_claim_missing_from_the_analysis_is_undecided(self):
        score = score_campaign(analysis({"B1": TRUE}))
        assert score["correct"] == 1 and score["undecided"] == 9 and score["rows"][1]["verdict"] == "missing"

    def test_a_failed_analysis_scores_zero(self):
        score = score_campaign({"error": "x"})
        assert score["accuracy"] == 0.0 and score["undecided"] == 10

    def test_the_accuracy_is_the_share_of_correct_cases(self):
        verdicts = {case["id"]: case["expected"] for case in CASES}
        verdicts["B1"] = "inconclusive"
        verdicts["B2"] = "inconclusive"
        assert score_campaign(analysis(verdicts))["accuracy"] == 0.8

    def test_the_rows_keep_the_expectation(self):
        row = score_campaign(perfect())["rows"][7]
        assert row == {"id": "B8", "expected": REVERSED, "verdict": REVERSED, "outcome": "correct"}


class TestScorePlan:
    CASE = CASES[0]

    def test_the_stated_direction_is_exact(self):
        result = score_plan(self.CASE, [plan((["RandomForest"], ["DecisionTree"]))])
        assert result == {"id": "B1", "candidates": 1, "first": "exact", "best": "exact", "matches": ["exact"]}

    def test_the_opposite_direction_is_reversed(self):
        assert score_plan(self.CASE, [plan((["DecisionTree"], ["RandomForest"]))])["best"] == "reversed"

    def test_other_models_are_none(self):
        assert score_plan(self.CASE, [plan((["KNN"], ["MLP"]))])["best"] == "none"

    def test_extra_models_in_a_group_are_not_exact(self):
        assert score_plan(self.CASE, [plan((["RandomForest", "ExtraTrees"], ["DecisionTree"]))])["best"] == "none"

    def test_the_best_candidate_counts_but_the_first_is_reported(self):
        result = score_plan(self.CASE, [plan((["KNN"], ["MLP"])), plan((["RandomForest"], ["DecisionTree"]))])
        assert result["first"] == "none" and result["best"] == "exact" and result["matches"] == ["none", "exact"]

    def test_an_exact_claim_after_a_reversed_one_in_a_candidate_wins(self):
        result = score_plan(self.CASE, [plan((["DecisionTree"], ["RandomForest"]), (["RandomForest"], ["DecisionTree"]))])
        assert result["matches"] == ["exact"]

    def test_an_exact_claim_before_a_reversed_one_in_a_candidate_stays_exact(self):
        result = score_plan(self.CASE, [plan((["RandomForest"], ["DecisionTree"]), (["DecisionTree"], ["RandomForest"]))])
        assert result["matches"] == ["exact"]

    def test_a_reversed_claim_after_an_unrelated_one_is_found(self):
        result = score_plan(self.CASE, [plan((["KNN"], ["MLP"]), (["DecisionTree"], ["RandomForest"]))])
        assert result["matches"] == ["reversed"]

    def test_exact_beats_reversed_across_candidates(self):
        result = score_plan(self.CASE, [plan((["DecisionTree"], ["RandomForest"])), plan((["RandomForest"], ["DecisionTree"]))])
        assert result["best"] == "exact" and result["first"] == "reversed"

    def test_no_candidates(self):
        assert score_plan(self.CASE, []) == {"id": "B1", "candidates": 0, "first": "none", "best": "none", "matches": []}
