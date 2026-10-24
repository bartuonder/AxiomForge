import pytest

import app.campaign.planning as planning
from app.campaign.demos import demo_spec
from app.campaign.planning import (
    MAX_PLAN_DATASETS,
    PlanningError,
    assemble_spec,
    deviation_notes,
    estimate_cost,
    map_models,
    minimum_adjusted_p,
    power_check,
    select_datasets,
)
from app.campaign.protocol import ESTIMATORS
from app.campaign.spec import CampaignSpecError
from app.campaign.stats import ALPHA
from app.datasets import benchmark_keys, core_keys

CLAIM = {
    "id": "C1",
    "statement": "Tree-based models outperform a neural network",
    "metrics": ["roc_auc", "pr_auc", "f1"],
    "subject": ["RandomForest", "HistGradientBoosting"],
    "other": ["MLP"],
}
MODELS = ["RandomForest", "HistGradientBoosting", "MLP"]
SOURCE = {"title": "A paper", "citation": "Someone et al., 2022", "url": "https://arxiv.org/abs/0000.00000"}


class TestModelMapping:
    def test_exact_estimator_names_map_to_themselves_without_a_note(self):
        assert map_models(["RandomForest", "XGBoost", "LogisticRegression"]) == (["RandomForest", "XGBoost", "LogisticRegression"], [], [])

    def test_spelling_and_case_do_not_matter(self):
        models, notes, unmapped = map_models(["random forest", "Hist-Gradient-Boosting", "k-nearest neighbors", "naive bayes", "SVC"])
        assert models == ["RandomForest", "HistGradientBoosting", "KNN", "GaussianNB", "SVM"]
        assert notes == [] and unmapped == []

    def test_a_deep_architecture_is_replaced_by_the_mlp_and_the_replacement_is_noted(self):
        models, notes, unmapped = map_models(["ResNet", "FT-Transformer"])
        assert models == ["MLP"] and unmapped == []
        assert notes == ["ResNet was represented by scikit-learn's MLPClassifier.", "FT-Transformer was represented by scikit-learn's MLPClassifier."]

    def test_gradient_boosted_trees_and_linear_models_get_their_stand_ins(self):
        models, notes, _ = map_models(["gradient boosted trees", "linear models"])
        assert models == ["HistGradientBoosting", "LogisticRegression"]
        assert notes == [
            "gradient boosted trees was represented by scikit-learn's HistGradientBoostingClassifier.",
            "linear models was represented by scikit-learn's LogisticRegression.",
        ]

    def test_an_alias_without_a_note_is_a_plain_synonym(self):
        assert map_models(["MLP", "multilayer perceptron", "RF", "LR"]) == (["MLP", "RandomForest", "LogisticRegression"], [], [])

    def test_unknown_models_are_reported_and_never_guessed(self):
        models, notes, unmapped = map_models(["TabNet", "RandomForest", "TabNet", "Prophet"])
        assert models == ["RandomForest"] and notes == [] and unmapped == ["TabNet", "Prophet"]

    def test_models_stay_in_first_seen_order_without_duplicates(self):
        models, _, _ = map_models(["MLP", "RandomForest", "resnet", "mlp"])
        assert models == ["MLP", "RandomForest"]

    def test_the_same_note_is_not_repeated(self):
        _, notes, _ = map_models(["ResNet", "ResNet"])
        assert notes == ["ResNet was represented by scikit-learn's MLPClassifier."]

    def test_every_target_is_a_runnable_estimator(self):
        for name in ("resnet", "fttransformer", "deeplearning", "linearmodels", "gbdt", "supportvectormachine"):
            models, _, unmapped = map_models([name])
            assert unmapped == [] and models[0] in ESTIMATORS

    def test_an_empty_list_maps_to_nothing(self):
        assert map_models([]) == ([], [], [])


class TestDatasetSelection:
    def test_the_benchmark_pool_is_the_default_and_gives_all_nine(self):
        assert select_datasets() == benchmark_keys() and len(select_datasets()) == 9

    def test_the_core_pool_gives_the_five_core_sets(self):
        assert select_datasets("core") == core_keys()

    def test_the_all_pool_starts_with_the_benchmark_and_is_capped(self):
        chosen = select_datasets("all")
        assert len(chosen) == MAX_PLAN_DATASETS == 10
        assert chosen[:9] == benchmark_keys() and chosen[9] == core_keys()[0]

    def test_a_count_takes_the_first_datasets_in_a_stable_order(self):
        assert select_datasets("benchmark", 7) == benchmark_keys()[:7]
        assert select_datasets("benchmark", 7) == select_datasets("benchmark", 7)

    def test_a_count_above_the_cap_or_the_pool_is_refused(self):
        with pytest.raises(PlanningError, match="at most 10"):
            select_datasets("all", 11)
        with pytest.raises(PlanningError, match="only 9"):
            select_datasets("benchmark", 10)
        with pytest.raises(PlanningError, match="only 5"):
            select_datasets("core", 6)

    @pytest.mark.parametrize("count", [0, -1, 2.5, "7", True])
    def test_a_bad_count_is_refused(self, count):
        with pytest.raises(PlanningError, match="positive integer"):
            select_datasets("benchmark", count)

    def test_an_unknown_pool_names_the_valid_ones(self):
        with pytest.raises(PlanningError, match="choose one of: benchmark, core, all"):
            select_datasets("everything")


class TestPower:
    @pytest.mark.parametrize(("datasets", "metrics", "expected"), [(9, 3, 0.01171875), (8, 3, 0.0234375), (7, 3, 0.046875), (6, 3, 0.09375), (5, 1, 0.0625), (6, 1, 0.03125)])
    def test_the_smallest_reachable_adjusted_p_matches_the_exact_test(self, datasets, metrics, expected):
        assert minimum_adjusted_p(datasets, metrics) == pytest.approx(expected)

    def test_it_agrees_with_the_p_value_the_live_campaign_reached(self):
        assert minimum_adjusted_p(9, 3) == pytest.approx(0.0117, abs=1e-4)

    def test_it_is_capped_at_one(self):
        assert minimum_adjusted_p(1, 3) == 1.0

    def test_zero_datasets_or_metrics_are_refused(self):
        with pytest.raises(PlanningError):
            minimum_adjusted_p(0, 1)
        with pytest.raises(PlanningError):
            minimum_adjusted_p(5, 0)

    def test_nine_datasets_support_three_metrics(self):
        power_check(9, [CLAIM])

    def test_six_datasets_cannot_support_three_metrics(self):
        with pytest.raises(PlanningError, match="6 datasets cannot reach p < 0.05 for a claim on 3 metric"):
            power_check(6, [CLAIM])

    def test_six_datasets_support_a_single_metric_claim(self):
        power_check(6, [{**CLAIM, "metrics": ["roc_auc"]}])

    def test_the_widest_claim_decides(self):
        narrow = {**CLAIM, "metrics": ["roc_auc"]}
        with pytest.raises(PlanningError):
            power_check(6, [narrow, CLAIM])

    def test_a_claim_with_a_single_metric_key_counts_as_one_metric(self):
        power_check(6, [{"metric": "roc_auc"}])

    def test_seven_datasets_with_three_metrics_just_pass(self):
        assert minimum_adjusted_p(7, 3) < ALPHA
        power_check(7, [CLAIM])

    def test_five_datasets_never_pass(self):
        with pytest.raises(PlanningError):
            power_check(5, [{**CLAIM, "metrics": ["roc_auc"]}])


class TestDeviationNotes:
    def test_a_default_parameter_campaign_says_there_was_no_search(self):
        notes = deviation_notes(benchmark_keys(), {}, [])
        assert notes[0] == "No hyperparameter search: every model ran with library default parameters."

    def test_a_configured_campaign_says_the_parameters_were_fixed_in_advance(self):
        notes = deviation_notes(benchmark_keys(), {"MLP": {"alpha": 0.01}}, [])
        assert "single configurations chosen in advance" in notes[0] and "No hyperparameter search" not in " ".join(notes)

    def test_the_splits_are_always_described(self):
        assert any("80/20 stratified splits repeated over ten seeds" in note for note in deviation_notes(core_keys(), {}, []))

    def test_benchmark_datasets_get_the_sample_and_subset_note(self):
        notes = deviation_notes(benchmark_keys(), {}, [])
        assert any("6000-row balanced sample" in note and "numeric-feature" in note for note in notes)
        assert not any("Larger core datasets" in note for note in notes)

    def test_core_datasets_get_the_sampling_note_only(self):
        notes = deviation_notes(core_keys(), {}, [])
        assert any("Larger core datasets were sampled to at most 6000 rows" in note for note in notes)
        assert not any("balanced sample" in note for note in notes)

    def test_a_mixed_pool_gets_both_notes(self):
        notes = deviation_notes(select_datasets("all"), {}, [])
        assert any("balanced sample" in note for note in notes) and any("Larger core datasets" in note for note in notes)

    def test_mapping_notes_come_first(self):
        notes = deviation_notes(benchmark_keys(), {}, ["ResNet was represented by scikit-learn's MLPClassifier."])
        assert notes[0] == "ResNet was represented by scikit-learn's MLPClassifier."


class TestAssembly:
    def test_a_full_spec_is_valid_and_carries_everything(self):
        spec = assemble_spec("Trees against networks", MODELS, [CLAIM], SOURCE)
        assert spec["title"] == "Trees against networks" and spec["models"] == MODELS
        assert spec["datasets"] == benchmark_keys() and spec["params"] == {}
        assert spec["claims"][0]["id"] == "C1" and spec["claims"][0]["subject"] == ["RandomForest", "HistGradientBoosting"]
        assert spec["source"]["citation"] == "Someone et al., 2022" and spec["source"]["url"] == SOURCE["url"]
        assert spec["source"]["deviations"][0].startswith("No hyperparameter search")

    def test_the_demo_claim_assembles_into_the_same_shape_as_the_ready_demo(self):
        demo = demo_spec("grinsztajn-2022")
        spec = assemble_spec(demo["title"], demo["models"], demo["claims"], {key: value for key, value in demo["source"].items() if key != "deviations"})
        assert spec["datasets"] == benchmark_keys() and [claim["id"] for claim in spec["claims"]] == ["C1", "C2"]

    def test_mapping_notes_are_part_of_the_deviations(self):
        spec = assemble_spec("T", MODELS, [CLAIM], SOURCE, mapped_notes=["ResNet was represented by scikit-learn's MLPClassifier."])
        assert spec["source"]["deviations"][0] == "ResNet was represented by scikit-learn's MLPClassifier."

    def test_the_source_from_the_caller_is_kept_but_its_deviations_are_replaced(self):
        spec = assemble_spec("T", MODELS, [CLAIM], {**SOURCE, "deviations": ["invented by the model"]})
        assert "invented by the model" not in spec["source"]["deviations"]

    def test_no_source_still_gets_deviations(self):
        spec = assemble_spec("T", MODELS, [CLAIM])
        assert spec["source"]["deviations"] and "title" not in spec["source"]

    def test_a_dataset_count_limits_the_datasets(self):
        spec = assemble_spec("T", MODELS, [{**CLAIM, "metrics": ["roc_auc"]}], SOURCE, dataset_count=6)
        assert spec["datasets"] == benchmark_keys()[:6]

    def test_too_few_datasets_for_the_metrics_are_refused_with_the_arithmetic(self):
        with pytest.raises(PlanningError, match="cannot reach p < 0.05"):
            assemble_spec("T", MODELS, [CLAIM], SOURCE, dataset_count=6)

    def test_the_core_pool_alone_is_refused_for_lack_of_power(self):
        with pytest.raises(PlanningError, match="5 datasets cannot reach"):
            assemble_spec("T", MODELS, [{**CLAIM, "metrics": ["roc_auc"]}], SOURCE, pool="core")

    def test_parameters_are_validated_and_make_the_deviation_say_so(self):
        spec = assemble_spec("T", MODELS, [CLAIM], SOURCE, params={"MLP": {"alpha": 0.01}})
        assert spec["params"] == {"MLP": {"alpha": 0.01}}
        assert "single configurations chosen in advance" in spec["source"]["deviations"][0]

    def test_a_default_valued_parameter_is_refused_by_the_spec_validation(self):
        with pytest.raises(CampaignSpecError, match="library default"):
            assemble_spec("T", MODELS, [CLAIM], SOURCE, params={"MLP": {"alpha": 0.0001}})

    def test_a_claim_naming_a_model_outside_the_campaign_is_refused(self):
        with pytest.raises(CampaignSpecError, match="does not run"):
            assemble_spec("T", ["RandomForest", "MLP"], [CLAIM], SOURCE)

    def test_an_unknown_pool_is_refused_before_anything_else(self):
        with pytest.raises(PlanningError, match="unknown dataset pool"):
            assemble_spec("T", MODELS, [CLAIM], SOURCE, pool="nope")

    def test_too_many_deviation_notes_are_refused(self, monkeypatch):
        monkeypatch.setattr(planning, "MAX_NOTES", 2)
        with pytest.raises(PlanningError, match="too many deviation notes"):
            assemble_spec("T", MODELS, [CLAIM], SOURCE)

    def test_the_caller_input_is_not_modified(self):
        claims = [dict(CLAIM)]
        source = dict(SOURCE)
        assemble_spec("T", MODELS, claims, source)
        assert claims == [CLAIM] and source == SOURCE


class TestCost:
    def test_the_demo_matches_the_measured_live_run(self):
        cost = estimate_cost(demo_spec("grinsztajn-2022") | {"datasets": benchmark_keys(), "params": {}})
        assert cost["datasets"] == 9 and cost["model_runs"] == 4
        assert cost["seconds_per_dataset"] == 76
        assert cost["estimated_seconds"] == 3 * 76
        assert 200 <= cost["estimated_seconds"] <= 300

    def test_a_configured_model_counts_twice_because_of_its_default_control(self):
        spec = {"models": MODELS, "params": {"MLP": {"alpha": 0.01}}, "datasets": ["a", "b", "c"]}
        assert estimate_cost(spec)["model_runs"] == 4

    def test_the_worst_case_multiplies_by_the_attempts(self):
        spec = {"models": MODELS, "datasets": ["a", "b", "c"]}
        cost = estimate_cost(spec, workers=3, attempts=2)
        assert cost["estimated_seconds"] == 62 and cost["worst_case_seconds"] == 124
        assert cost["sandboxes"] == 3 and cost["max_sandboxes"] == 6

    def test_datasets_run_in_waves_of_the_worker_count(self):
        spec = {"models": MODELS, "datasets": list("abcdefghi")}
        assert estimate_cost(spec, workers=3)["estimated_seconds"] == 3 * 62
        assert estimate_cost(spec, workers=9)["estimated_seconds"] == 62
        assert estimate_cost(spec, workers=4)["estimated_seconds"] == 3 * 62

    def test_zero_workers_still_gives_a_finite_estimate(self):
        spec = {"models": MODELS, "datasets": ["a", "b"]}
        assert estimate_cost(spec, workers=0)["estimated_seconds"] == 2 * 62

    def test_a_missing_params_key_is_the_same_as_no_parameters(self):
        assert estimate_cost({"models": MODELS, "datasets": ["a"]})["model_runs"] == 3


class TestSurvivors:
    def test_the_name_in_a_note_has_no_surrounding_whitespace(self):
        assert map_models(["  ResNet  "])[1] == ["ResNet was represented by scikit-learn's MLPClassifier."]

    @pytest.mark.parametrize(
        ("alias", "target"),
        [
            ("gbdt", "HistGradientBoosting"),
            ("gbt", "HistGradientBoosting"),
            ("gbm", "HistGradientBoosting"),
            ("gradient boosted decision trees", "HistGradientBoosting"),
            ("dnn", "MLP"),
            ("deep learning", "MLP"),
            ("transformer", "MLP"),
            ("saint", "MLP"),
            ("neural network", "MLP"),
            ("linear model", "LogisticRegression"),
            ("logreg", "LogisticRegression"),
            ("support vector machine", "SVM"),
            ("nearest neighbors", "KNN"),
            ("random forests", "RandomForest"),
        ],
    )
    def test_each_alias_has_its_target(self, alias, target):
        assert map_models([alias])[0] == [target]

    def test_a_p_value_exactly_at_alpha_is_not_enough(self, monkeypatch):
        monkeypatch.setattr(planning, "ALPHA", minimum_adjusted_p(9, 3))
        with pytest.raises(PlanningError):
            power_check(9, [CLAIM])

    def test_the_refusal_states_the_best_reachable_p(self):
        with pytest.raises(PlanningError, match="adjusted p of 0.0938"):
            power_check(6, [CLAIM])

    def test_no_claims_means_a_single_metric_assumption(self):
        power_check(6, [])

    def test_repeated_metrics_in_a_claim_count_once(self):
        claim = {**CLAIM, "metrics": ["roc_auc", "roc_auc"]}
        spec = assemble_spec("T", MODELS, [claim], SOURCE, dataset_count=6)
        assert spec["claims"][0]["metrics"] == ["roc_auc"]

    def test_the_selected_datasets_reach_the_spec(self):
        spec = assemble_spec("T", MODELS, [{**CLAIM, "metrics": ["roc_auc"]}], SOURCE, dataset_count=7)
        assert spec["datasets"] == benchmark_keys()[:7]
