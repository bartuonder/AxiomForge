import numpy as np
import pytest

from app.research import generate
from app.research.protocol import ExplorationView, Hypothesis, Registry

DATASETS = [f"e{index}" for index in range(6)]


def view(models, datasets=DATASETS):
    per_dataset = {}
    for position, dataset in enumerate(datasets):
        per_dataset[dataset] = {
            name: {"roc_auc_mean": float(values[position]), "pr_auc_mean": 0.5, "f1_mean": 0.5}
            for name, values in models.items()
        }
    return ExplorationView(per_dataset, list(datasets))


def flat(level, count=6):
    return [level] * count


def propose(models, registry=None, stage="default", count=10, **kwargs):
    proposals, skipped = generate.propose(view(models), registry or Registry(25), stage, count, **kwargs)
    return proposals, skipped


class TestPairs:
    def test_the_winner_on_the_exploration_datasets_is_the_subject(self):
        proposals, _ = propose({"A": flat(0.80), "B": flat(0.85)})
        assert [(item.subject, item.other) for item in proposals] == [(("B",), ("A",))]

    def test_the_subject_does_not_depend_on_the_order_of_the_names(self):
        first, _ = propose({"A": flat(0.80), "B": flat(0.85)})
        second, _ = propose({"B": flat(0.85), "A": flat(0.80)})
        assert (first[0].subject, first[0].other) == (second[0].subject, second[0].other)

    def test_the_evidence_is_the_exploration_estimate(self):
        proposals, _ = propose({"A": flat(0.80), "B": flat(0.83)})
        assert proposals[0].evidence == {"median_difference": pytest.approx(0.03), "wins": 6, "datasets": 6, "scope": "exploration"}

    def test_the_hypothesis_is_about_the_primary_metric_and_the_stage(self):
        proposals, _ = propose({"A": flat(0.80), "B": flat(0.85)}, stage="tuned")
        item = proposals[0]
        assert item.metric == "roc_auc" and item.stage == "tuned" and "tuned" in item.statement and "B" in item.statement and "A" in item.statement

    def test_a_small_effect_is_not_worth_a_hypothesis(self):
        assert propose({"A": flat(0.800), "B": flat(0.805)})[0] == []

    def test_the_effect_threshold_is_inclusive(self):
        assert len(propose({"A": flat(0.80), "B": flat(0.81)})[0]) == 1
        assert propose({"A": flat(0.80), "B": flat(0.81)}, effect=0.02)[0] == []

    def test_an_inconsistent_difference_is_not_proposed(self):
        a = [0.80, 0.80, 0.80, 0.90, 0.90, 0.90]
        b = [0.85, 0.85, 0.85, 0.80, 0.80, 0.80]
        assert propose({"A": a, "B": b})[0] == []

    def test_five_wins_out_of_six_is_consistent_enough_and_four_is_not(self):
        base = flat(0.80)
        five = [0.85, 0.85, 0.85, 0.85, 0.85, 0.70]
        four = [0.85, 0.85, 0.85, 0.85, 0.70, 0.70]
        assert len(propose({"A": base, "B": five})[0]) == 1
        assert propose({"A": base, "B": four})[0] == []

    def test_equal_models_give_nothing_even_without_an_effect_threshold(self):
        assert propose({"A": flat(0.80), "B": flat(0.80)}, effect=0.0, consistency=0.0)[0] == []

    def test_equal_models_give_nothing(self):
        assert propose({"A": flat(0.80), "B": flat(0.80)})[0] == []

    def test_the_best_differences_come_first_and_the_count_limits_them(self):
        models = {"A": flat(0.70), "B": flat(0.75), "C": flat(0.80), "D": flat(0.90)}
        proposals, _ = propose(models, count=3)
        sizes = [item.evidence["median_difference"] for item in proposals]
        assert len(proposals) == 3 and sizes == sorted(sizes, reverse=True)
        assert proposals[0].subject == ("D",) and proposals[0].other == ("A",)

    def test_more_wins_come_first_when_the_effect_is_the_same(self):
        models = {"A": flat(0.80), "B": flat(0.85), "C": [0.85, 0.85, 0.85, 0.85, 0.85, 0.60]}
        proposals, _ = propose(models, count=10)
        order = [(item.subject, item.other) for item in proposals]
        assert order.index((("B",), ("A",))) < order.index((("C",), ("A",)))

    def test_the_statement_is_a_plain_sentence(self):
        assert generate.statement("B", "A", "roc_auc", "default") == "B scores higher than A on roc_auc (default stage)"

    def test_the_budget_of_the_registry_limits_them_too(self):
        models = {"A": flat(0.70), "B": flat(0.75), "C": flat(0.80), "D": flat(0.90)}
        assert len(propose(models, registry=Registry(2), count=10)[0]) == 2

    def test_nothing_is_proposed_when_the_budget_is_used_up(self):
        registry = Registry(1)
        registry.register(Hypothesis("H1", ("X",), ("Y",), "default", "roc_auc", "x", {}))
        assert propose({"A": flat(0.7), "B": flat(0.9)}, registry=registry)[0] == []

    def test_ties_in_size_are_broken_by_the_names(self):
        models = {"A": flat(0.70), "B": flat(0.80), "C": flat(0.80)}
        proposals, _ = propose(models, count=10)
        pairs = [(item.subject, item.other) for item in proposals]
        assert pairs.index((("B",), ("A",))) < pairs.index((("C",), ("A",)))

    def test_the_ids_continue_after_the_registered_ones(self):
        registry = Registry(25)
        registry.register(Hypothesis("H1", ("X",), ("Y",), "default", "roc_auc", "x", {}))
        proposals, _ = propose({"A": flat(0.7), "B": flat(0.9), "C": flat(0.8)}, registry=registry)
        assert [item.id for item in proposals] == ["H2", "H3", "H4"]

    def test_the_proposals_can_all_be_registered(self):
        registry = Registry(25)
        proposals, _ = propose({"A": flat(0.7), "B": flat(0.9), "C": flat(0.8)}, registry=registry)
        for item in proposals:
            registry.register(item)
        assert len(registry.records) == 3

    def test_only_the_exploration_datasets_are_counted(self):
        proposals, _ = propose({"A": flat(0.7, 6), "B": flat(0.9, 6)})
        assert proposals[0].evidence["datasets"] == 6

    def test_a_model_without_the_metric_is_ignored(self):
        data = view({"A": flat(0.7), "B": flat(0.9)})
        for record in data.per_dataset.values():
            record["C"] = {"pr_auc_mean": 0.5}
        proposals, _ = generate.propose(data, Registry(25), "default", 10)
        assert all("C" not in item.subject + item.other for item in proposals)


class TestBaselines:
    def test_two_default_controls_are_never_compared_with_each_other(self):
        proposals, _ = propose({"A__default": flat(0.7), "B__default": flat(0.9)})
        assert proposals == []

    def test_a_model_is_compared_with_its_own_default_control(self):
        proposals, _ = propose({"A": flat(0.9), "A__default": flat(0.7)})
        assert [(item.subject, item.other) for item in proposals] == [(("A",), ("A__default",))]

    def test_a_model_is_not_compared_with_the_control_of_another(self):
        proposals, _ = propose({"A": flat(0.9), "B__default": flat(0.7)})
        assert proposals == []

    def test_a_tuned_stage_offers_pairs_and_tuning_effects_together(self):
        models = {"A": flat(0.90), "B": flat(0.85), "A__default": flat(0.80), "B__default": flat(0.84)}
        proposals, _ = propose(models, stage="tuned")
        pairs = {(item.subject, item.other) for item in proposals}
        assert pairs == {(("A",), ("B",)), (("A",), ("A__default",)), (("B",), ("B__default",))}


class TestNovelty:
    def test_a_registered_claim_is_not_proposed_again(self):
        registry = Registry(25)
        registry.register(Hypothesis("H1", ("B",), ("A",), "default", "roc_auc", "B beats A", {}))
        proposals, skipped = propose({"A": flat(0.7), "B": flat(0.9)}, registry=registry)
        assert proposals == []
        assert skipped == [{"statement": proposals_statement("B", "A", "default"), "reason": "already registered in this session"}]

    def test_a_claim_known_from_earlier_sessions_is_skipped_with_its_reason(self):
        proposals, skipped = propose({"A": flat(0.7), "B": flat(0.9)}, known={(("B",), ("A",))})
        assert proposals == []
        assert [item["reason"] for item in skipped] == ["already confirmed in an earlier session"]

    def test_a_known_claim_does_not_stop_other_proposals(self):
        proposals, skipped = propose({"A": flat(0.7), "B": flat(0.9), "C": flat(0.8)}, known={(("B",), ("A",))})
        assert len(proposals) == 2 and len(skipped) == 1

    def test_the_same_pair_at_another_stage_is_still_new(self):
        registry = Registry(25)
        registry.register(Hypothesis("H1", ("B",), ("A",), "default", "roc_auc", "B beats A", {}))
        proposals, _ = propose({"A": flat(0.7), "B": flat(0.9)}, registry=registry, stage="tuned")
        assert len(proposals) == 1

    def test_the_skipped_ones_do_not_use_up_the_count(self):
        proposals, skipped = propose({"A": flat(0.7), "B": flat(0.9), "C": flat(0.8)}, known={(("B",), ("A",))}, count=1)
        assert len(proposals) == 1 and len(skipped) == 1


def proposals_statement(subject, other, stage):
    return generate.statement(subject, other, "roc_auc", stage)


class TestTuningTrigger:
    def make(self, size):
        return Hypothesis("H1", ("A",), ("B",), "default", "roc_auc", "x", {"median_difference": size})

    def test_a_large_exploration_effect_asks_for_the_tuned_stage(self):
        assert generate.needs_tuning([self.make(0.03)], 0.02) is True

    def test_a_small_one_does_not(self):
        assert generate.needs_tuning([self.make(0.015)], 0.02) is False

    def test_the_threshold_is_inclusive(self):
        assert generate.needs_tuning([self.make(0.02)], 0.02) is True

    def test_the_default_threshold_is_two_points(self):
        assert generate.needs_tuning([self.make(0.02)]) is True
        assert generate.needs_tuning([self.make(0.019)]) is False

    def test_nothing_proposed_means_no_tuned_stage(self):
        assert generate.needs_tuning([], 0.02) is False

    def test_one_large_effect_among_small_ones_is_enough(self):
        assert generate.needs_tuning([self.make(0.001), self.make(0.05)], 0.02) is True


class TestSealing:
    def test_the_proposals_depend_only_on_the_view(self):
        rng = np.random.default_rng(0)
        models = {"A": rng.uniform(0.6, 0.9, 6), "B": rng.uniform(0.6, 0.9, 6), "C": rng.uniform(0.6, 0.9, 6)}
        first = generate.propose(view(models), Registry(25), "default", 10)[0]
        second = generate.propose(view(models), Registry(25), "default", 10)[0]
        assert [item.digest() for item in first] == [item.digest() for item in second]

    def test_the_function_takes_no_confirmation_data(self):
        import inspect

        parameters = set(inspect.signature(generate.propose).parameters)
        assert parameters == {"view", "registry", "stage", "count", "effect", "consistency", "known"}
