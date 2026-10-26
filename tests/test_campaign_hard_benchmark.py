import pytest

from app.campaign.hard_benchmark import (
    DECISIVE,
    HARD_PLAN_CASES,
    NEAR_PAIRS,
    classify_plan,
    effect_summary,
    hard_claims,
    hard_models,
    hard_spec,
    near_cases,
    near_models,
    near_spec,
    score_near_equal,
    wilson_interval,
)
from app.campaign.protocol import ESTIMATORS
from app.campaign.tuning import SEARCH_SPACES
from app.datasets import benchmark_keys


def analysis(verdicts):
    return {"claims": [{"id": key, "verdict": value} for key, value in verdicts.items()]}


def undecided():
    return analysis({case["id"]: "inconclusive" for case in near_cases()})


def plan(*claims):
    return {"spec": {"claims": [{"subject": list(subject), "other": list(other)} for subject, other in claims]}}


class TestCases:
    def test_every_pair_is_asked_in_both_directions(self):
        cases = near_cases()
        assert len(cases) == 2 * len(NEAR_PAIRS) == 14
        for number, (first, second) in enumerate(NEAR_PAIRS):
            forward, backward = [case for case in cases if case["pair"] == number]
            assert (forward["subject"], forward["other"]) == ([first], [second])
            assert (backward["subject"], backward["other"]) == ([second], [first])

    def test_ids_continue_after_the_known_claims_without_clashes(self):
        assert [case["id"] for case in near_cases()] == [f"N{number}" for number in range(1, 15)]

    def test_the_queries_name_both_models_with_the_right_verb(self):
        queries = [case["query"] for case in near_cases()]
        assert queries[0] == "Random forests outperform extremely randomized trees on tabular classification data."
        assert queries[2] == "Histogram gradient boosting outperforms gradient boosting on tabular classification data."
        assert queries[5] == "A linear support vector machine outperforms logistic regression on tabular classification data."
        assert queries[6] == "LightGBM outperforms histogram gradient boosting on tabular classification data."
        assert queries[8] == "XGBoost outperforms LightGBM on tabular classification data."
        assert queries[12] == "XGBoost outperforms histogram gradient boosting on tabular classification data."
        assert queries[10] == "Logistic regression outperforms linear discriminant analysis on tabular classification data."

    def test_the_new_pairs_join_the_old_ones_at_the_end(self):
        assert NEAR_PAIRS[:3] == [("RandomForest", "ExtraTrees"), ("HistGradientBoosting", "GradientBoosting"), ("LogisticRegression", "LinearSVC")]
        assert set(NEAR_PAIRS[3:]) == {("LightGBM", "HistGradientBoosting"), ("XGBoost", "LightGBM"), ("LogisticRegression", "LDA"), ("XGBoost", "HistGradientBoosting")}

    def test_no_pair_repeats_and_no_model_is_paired_with_itself(self):
        assert len({frozenset(pair) for pair in NEAR_PAIRS}) == len(NEAR_PAIRS) and all(first != second for first, second in NEAR_PAIRS)

    def test_every_model_is_runnable_and_has_a_search_space(self):
        models = hard_models()
        assert len(models) == len(set(models)) == 13
        assert set(models) <= set(ESTIMATORS) and set(models) <= set(SEARCH_SPACES)

    def test_the_claims_are_the_known_ones_then_the_near_equal_ones(self):
        claims = hard_claims()
        assert [claim["id"] for claim in claims] == [f"B{n}" for n in range(1, 11)] + [f"N{n}" for n in range(1, 15)]
        assert all(claim["metrics"] == ["roc_auc", "pr_auc", "f1"] and not claim["statement"].endswith(".") for claim in claims)


class TestSpec:
    def test_the_spec_is_valid(self):
        spec = hard_spec()
        assert spec["datasets"] == benchmark_keys() and len(spec["claims"]) == 24 and not spec["tuning"]

    def test_the_tuning_reaches_the_spec(self):
        assert hard_spec({"iterations": 12, "folds": 3})["tuning"] == {"iterations": 12, "folds": 3}

    def test_the_dataset_count_is_forwarded(self):
        assert len(hard_spec(dataset_count=8)["datasets"]) == 8


class TestNearSpec:
    def test_only_the_near_equal_claims_are_asked(self):
        spec = near_spec()
        assert [claim["id"] for claim in spec["claims"]] == [f"N{n}" for n in range(1, 15)] and not spec["tuning"]

    def test_only_the_models_of_the_pairs_are_run(self):
        models = near_models()
        assert len(models) == len(set(models)) == 9 and set(models) == {name for pair in NEAR_PAIRS for name in pair}
        assert near_spec()["models"] == models

    def test_the_tuning_and_the_dataset_count_are_forwarded(self):
        spec = near_spec({"iterations": 12, "folds": 3}, dataset_count=8)
        assert spec["tuning"] == {"iterations": 12, "folds": 3} and len(spec["datasets"]) == 8

    def test_every_model_has_a_search_space(self):
        assert set(near_models()) <= set(SEARCH_SPACES) and set(near_models()) <= set(ESTIMATORS)


class TestNearEqual:
    def test_all_undecided_pairs_are_clean(self):
        score = score_near_equal(undecided())
        assert score["decisive_claims"] == 0 and score["decisive_rate"] == 0.0 and score["contradictory_pairs"] == 0
        assert [pair["state"] for pair in score["pairs"]] == ["undecided"] * 7 and score["claims"] == 14

    def test_a_decisive_verdict_marks_its_pair(self):
        verdicts = {case["id"]: "inconclusive" for case in near_cases()}
        verdicts["N3"] = "replicated"
        verdicts["N4"] = "contradicted"
        score = score_near_equal(analysis(verdicts))
        assert score["pairs"][1] == {"pair": ["HistGradientBoosting", "GradientBoosting"], "forward": "replicated", "backward": "contradicted", "state": "decisive"}
        assert score["decisive_claims"] == 2 and score["decisive_rate"] == pytest.approx(2 / 14)

    def test_both_directions_replicated_is_contradictory(self):
        verdicts = {case["id"]: "inconclusive" for case in near_cases()}
        verdicts["N1"] = verdicts["N2"] = "replicated"
        score = score_near_equal(analysis(verdicts))
        assert score["pairs"][0]["state"] == "contradictory" and score["contradictory_pairs"] == 1

    def test_one_contradicted_alone_is_decisive_not_contradictory(self):
        verdicts = {case["id"]: "inconclusive" for case in near_cases()}
        verdicts["N5"] = "contradicted"
        assert score_near_equal(analysis(verdicts))["pairs"][2]["state"] == "decisive"

    def test_partial_and_untestable_verdicts_count_as_undecided(self):
        verdicts = {case["id"]: "partially_replicated" for case in near_cases()}
        verdicts["N2"] = "not_testable"
        score = score_near_equal(analysis(verdicts))
        assert score["decisive_claims"] == 0 and score["pairs"][0]["state"] == "undecided"

    def test_missing_claims_are_undecided(self):
        score = score_near_equal({"error": "x"})
        assert score["pairs"][0]["forward"] == "missing" and score["decisive_claims"] == 0

    def test_the_decisive_words(self):
        assert DECISIVE == ("replicated", "contradicted")


class TestEffects:
    def row(self, model, adjusted, significant, significant_all):
        return {"model": model, "adjusted_p_value": adjusted, "significant": significant, "significant_all": significant_all}

    def test_the_counts(self):
        rows = [self.row("A", 0.01, True, True), self.row("A", 0.02, True, False), self.row("B", None, False, False), self.row("B", 0.3, False, False)]
        assert effect_summary({"parameter_effects": rows}) == {"effects": 4, "models": 2, "testable": 3, "significant": 2, "significant_all": 1}

    def test_no_effects(self):
        assert effect_summary({}) == {"effects": 0, "models": 0, "testable": 0, "significant": 0, "significant_all": 0}


class TestWilson:
    def test_known_values(self):
        low, high = wilson_interval(8, 10)
        assert low == pytest.approx(0.4902, abs=1e-3) and high == pytest.approx(0.9433, abs=1e-3)

    def test_all_successes_reach_one_but_not_the_lower_bound(self):
        low, high = wilson_interval(10, 10)
        assert high == 1.0 and 0.65 < low < 0.75

    def test_no_successes_start_at_zero(self):
        low, high = wilson_interval(0, 10)
        assert low == 0.0 and 0.25 < high < 0.35

    def test_more_samples_narrow_the_interval(self):
        small = wilson_interval(5, 10)
        large = wilson_interval(50, 100)
        assert large[1] - large[0] < small[1] - small[0]

    @pytest.mark.parametrize(("successes", "total"), [(1, 0), (-1, 5), (6, 5)])
    def test_impossible_counts_are_refused(self, successes, total):
        with pytest.raises(ValueError, match="successes must lie between 0 and a positive total"):
            wilson_interval(successes, total)


class TestPlans:
    def case(self, identifier):
        return next(case for case in HARD_PLAN_CASES if case["id"] == identifier)

    def test_there_are_eight_cases_with_unique_ids(self):
        assert len(HARD_PLAN_CASES) == 8 and len({case["id"] for case in HARD_PLAN_CASES}) == 8

    def test_the_exact_pair_is_accepted_where_allowed(self):
        result = classify_plan(self.case("H4"), [plan((["MLP"], ["SVM"]))])
        assert result == {"id": "H4", "outcome": "exact", "accepted": True}

    def test_the_reversed_pair_is_refused_where_only_exact_counts(self):
        result = classify_plan(self.case("H4"), [plan((["SVM"], ["MLP"]))])
        assert result["outcome"] == "reversed" and result["accepted"] is False

    def test_unsupported_is_the_right_answer_for_an_off_topic_query(self):
        assert classify_plan(self.case("H7"), [], unsupported=True) == {"id": "H7", "outcome": "unsupported", "accepted": True}

    def test_a_candidate_for_an_off_topic_query_is_not_accepted(self):
        result = classify_plan(self.case("H3"), [plan((["MLP"], ["RandomForest"]))])
        assert result["outcome"] == "other" and result["accepted"] is False

    def test_no_candidates_count_as_unsupported(self):
        assert classify_plan(self.case("H7"), [])["outcome"] == "unsupported"

    def test_the_first_candidate_decides(self):
        result = classify_plan(self.case("H4"), [plan((["KNN"], ["SVM"])), plan((["MLP"], ["SVM"]))])
        assert result["outcome"] == "other"

    def test_an_exact_claim_after_a_reversed_one_in_a_candidate_wins(self):
        result = classify_plan(self.case("H4"), [plan((["SVM"], ["MLP"]), (["MLP"], ["SVM"]))])
        assert result["outcome"] == "exact"

    def test_an_exact_claim_before_a_reversed_one_in_a_candidate_stays_exact(self):
        result = classify_plan(self.case("H4"), [plan((["MLP"], ["SVM"]), (["SVM"], ["MLP"]))])
        assert result["outcome"] == "exact"

    def test_a_reversed_claim_after_an_unrelated_one_is_found(self):
        result = classify_plan(self.case("H2"), [plan((["KNN"], ["SVM"]), (["GradientBoosting"], ["RandomForest"]))])
        assert result["outcome"] == "reversed" and result["accepted"] is True

    def test_a_case_without_a_pair_never_matches(self):
        assert classify_plan(self.case("H6"), [plan((["GradientBoosting"], ["RandomForest"]))])["outcome"] == "other"
