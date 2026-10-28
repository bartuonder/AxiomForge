import math

import numpy as np
import pytest

from app.research import protocol
from app.research.protocol import ExplorationView, Hypothesis, ProtocolError, Registry

POOL = [f"d{index:02d}" for index in range(16)]


def per_dataset(datasets, scores, noise=0.0, seed=0):
    generator = np.random.default_rng(seed)
    result = {}
    for dataset in datasets:
        base = generator.uniform(0.6, 0.9)
        result[dataset] = {
            model: {f"{metric}_mean": float(base + shift + (generator.normal(0, noise) if noise else 0.0)) for metric in ("roc_auc", "pr_auc", "f1")}
            for model, shift in scores.items()
        }
    return result


def hypothesis(subject=("A",), other=("B",), stage="default", **changes):
    return Hypothesis(
        id=changes.pop("id", "H1"),
        subject=tuple(subject),
        other=tuple(other),
        stage=stage,
        metric=changes.pop("metric", "roc_auc"),
        statement=changes.pop("statement", "A beats B"),
        evidence=changes.pop("evidence", {"median_difference": 0.02, "wins": 6, "datasets": 6}),
    )


class TestSplit:
    def test_it_splits_the_pool_into_two_disjoint_parts_that_cover_it(self):
        explore, confirm = protocol.split_pool(POOL, 6, seed=0)
        assert len(explore) == 6 and len(confirm) == 10
        assert not set(explore) & set(confirm) and set(explore) | set(confirm) == set(POOL)

    def test_it_is_deterministic_and_depends_on_the_seed(self):
        assert protocol.split_pool(POOL, 6, 0) == protocol.split_pool(POOL, 6, 0)
        assert protocol.split_pool(POOL, 6, 0) != protocol.split_pool(POOL, 6, 1)

    def test_it_does_not_depend_on_the_order_of_the_pool(self):
        shuffled = list(reversed(POOL))
        first = protocol.split_pool(POOL, 6, 3)
        second = protocol.split_pool(shuffled, 6, 3)
        assert set(first[0]) == set(second[0]) and set(first[1]) == set(second[1])

    def test_each_part_keeps_the_order_of_the_pool(self):
        explore, confirm = protocol.split_pool(POOL, 6, 0)
        assert explore == sorted(explore, key=POOL.index) and confirm == sorted(confirm, key=POOL.index)

    def test_the_split_of_the_test_pool_with_seed_zero_is_fixed(self):
        explore, confirm = protocol.split_pool(POOL, 6, 0)
        assert explore == ['d02', 'd03', 'd04', 'd05', 'd08', 'd11']
        assert confirm == [key for key in POOL if key not in explore]

    def test_each_part_keeps_the_order_it_was_given_even_when_it_is_not_sorted(self):
        reverse = list(reversed(POOL))
        explore, confirm = protocol.split_pool(reverse, 6, 0)
        assert explore == [key for key in reverse if key in explore] and confirm == [key for key in reverse if key in confirm]
        assert explore != sorted(explore)

    def test_five_datasets_are_still_too_few_to_confirm(self):
        with pytest.raises(ProtocolError, match="at least 6"):
            protocol.split_pool(POOL[:11], 6, 0)
        assert len(protocol.split_pool(POOL[:12], 6, 0)[1]) == 6

    def test_too_few_datasets_to_confirm_is_refused(self):
        with pytest.raises(ProtocolError, match="at least 6"):
            protocol.split_pool(POOL[:10], 6, 0)

    def test_too_few_datasets_to_explore_is_refused(self):
        with pytest.raises(ProtocolError, match="at least 3"):
            protocol.split_pool(POOL, 2, 0)

    def test_duplicates_are_refused(self):
        with pytest.raises(ProtocolError, match="duplicate"):
            protocol.split_pool(POOL + ["d00"], 6, 0)


class TestBudget:
    @pytest.mark.parametrize("count,expected", [(6, 1), (7, 3), (8, 6), (9, 12), (10, 25), (11, 51), (12, 102)])
    def test_the_largest_number_of_hypotheses_that_can_all_be_significant(self, count, expected):
        assert protocol.max_hypotheses(count) == expected

    def test_the_bound_is_the_exact_condition_of_the_smallest_p_value(self):
        for count in range(6, 13):
            largest = protocol.max_hypotheses(count)
            assert largest * protocol.min_p_value(count) < protocol.ALPHA
            assert (largest + 1) * protocol.min_p_value(count) >= protocol.ALPHA

    def test_the_smallest_p_value_of_an_exact_two_sided_wilcoxon(self):
        assert protocol.min_p_value(10) == 2 / 1024
        assert protocol.min_p_value(5) == 2 / 32

    def test_the_condition_is_strict_when_the_bound_falls_exactly_on_the_level(self):
        assert protocol.max_hypotheses(6, alpha=0.25) == 7

    def test_a_looser_alpha_allows_more(self):
        assert protocol.max_hypotheses(10, alpha=0.10) > protocol.max_hypotheses(10)

    def test_a_confirmation_set_too_small_for_any_test_allows_none(self):
        assert protocol.max_hypotheses(4) == 0


class TestHypothesis:
    def test_it_is_frozen(self):
        item = hypothesis()
        with pytest.raises(Exception):
            item.subject = ("C",)

    def test_its_digest_covers_the_models_the_stage_and_the_metric(self):
        base = hypothesis().digest()
        assert base == hypothesis().digest() and len(base) == 64
        assert hypothesis(subject=("C",)).digest() != base
        assert hypothesis(other=("C",)).digest() != base
        assert hypothesis(stage="tuned").digest() != base
        assert hypothesis(metric="pr_auc").digest() != base
        assert hypothesis(id="H9").digest() != base

    def test_the_digest_does_not_depend_on_the_order_inside_a_group(self):
        assert hypothesis(subject=("A", "B")).digest() == hypothesis(subject=("B", "A")).digest()

    def test_the_key_does_not_depend_on_the_order_inside_a_group(self):
        assert hypothesis(subject=("A", "B")).key == hypothesis(subject=("B", "A")).key
        assert hypothesis(other=("A", "B")).key == hypothesis(other=("B", "A")).key

    def test_its_key_is_what_makes_two_hypotheses_the_same_claim(self):
        assert hypothesis().key == ("default", ("A",), ("B",), "roc_auc")
        assert hypothesis(id="H2", statement="other words").key == hypothesis().key


class TestRegistry:
    def test_a_registered_hypothesis_is_kept_with_its_digest_and_time(self):
        registry = Registry(5)
        record = registry.register(hypothesis())
        assert record["digest"] == hypothesis().digest() and record["registered_at"]
        assert registry.records == [record]

    def test_the_budget_is_enforced(self):
        registry = Registry(2)
        registry.register(hypothesis(id="H1", subject=("A",), other=("B",)))
        registry.register(hypothesis(id="H2", subject=("A",), other=("C",)))
        with pytest.raises(ProtocolError, match="budget"):
            registry.register(hypothesis(id="H3", subject=("B",), other=("C",)))
        assert len(registry.records) == 2 and registry.remaining == 0

    def test_the_same_claim_cannot_be_registered_twice(self):
        registry = Registry(5)
        registry.register(hypothesis())
        with pytest.raises(ProtocolError, match="already registered"):
            registry.register(hypothesis(id="H2"))

    def test_the_same_pair_at_another_stage_is_a_new_claim(self):
        registry = Registry(5)
        registry.register(hypothesis())
        registry.register(hypothesis(id="H2", stage="tuned"))
        assert len(registry.records) == 2

    def test_a_duplicate_id_is_refused(self):
        registry = Registry(5)
        registry.register(hypothesis())
        with pytest.raises(ProtocolError, match="id"):
            registry.register(hypothesis(subject=("C",)))

    def test_the_returned_record_is_a_copy(self):
        registry = Registry(5)
        record = registry.register(hypothesis())
        record["subject"] = ["Z"]
        assert registry.records[0]["subject"] == ["A"]

    def test_the_evidence_is_copied_at_registration(self):
        registry = Registry(5)
        item = hypothesis()
        registry.register(item)
        item.evidence["wins"] = 0
        assert registry.records[0]["evidence"]["wins"] == 6

    def test_the_records_cannot_be_changed_from_outside(self):
        registry = Registry(5)
        registry.register(hypothesis())
        registry.records[0]["subject"] = ["Z"]
        registry.records.append({"id": "X"})
        assert registry.records[0]["subject"] == ["A"] and len(registry.records) == 1

    def test_it_knows_whether_a_claim_is_registered(self):
        registry = Registry(5)
        registry.register(hypothesis())
        assert registry.has(hypothesis(id="H2")) is True
        assert registry.has(hypothesis(id="H2", subject=("C",))) is False

    def test_it_can_be_restored_from_saved_records(self):
        registry = Registry(5)
        registry.register(hypothesis())
        restored = Registry.restore(5, registry.records)
        assert restored.records == registry.records and restored.remaining == 4
        with pytest.raises(ProtocolError, match="already registered"):
            restored.register(hypothesis(id="H2"))

    def test_a_tampered_record_is_refused_on_restore(self):
        registry = Registry(5)
        registry.register(hypothesis())
        records = registry.records
        records[0]["subject"] = ["Z"]
        with pytest.raises(ProtocolError, match="digest"):
            Registry.restore(5, records)

    def test_a_budget_of_zero_registers_nothing(self):
        with pytest.raises(ProtocolError, match="budget"):
            Registry(0).register(hypothesis())


class TestExplorationView:
    def test_it_keeps_only_the_exploration_datasets(self):
        results = per_dataset(POOL, {"A": 0.0, "B": 0.0})
        view = ExplorationView(results, POOL[:6])
        assert set(view.per_dataset) == set(POOL[:6]) and view.datasets == POOL[:6]

    def test_it_holds_no_trace_of_the_other_datasets(self):
        results = per_dataset(POOL, {"A": 0.0, "B": 0.0})
        view = ExplorationView(results, POOL[:6])
        assert not any(name in repr(vars(view)) for name in POOL[6:])

    def test_it_is_a_copy_so_later_changes_do_not_reach_it(self):
        results = per_dataset(POOL, {"A": 0.0})
        view = ExplorationView(results, POOL[:6])
        results[POOL[0]]["A"]["roc_auc_mean"] = 123.0
        assert view.per_dataset[POOL[0]]["A"]["roc_auc_mean"] != 123.0

    def test_a_missing_exploration_dataset_is_refused(self):
        results = per_dataset(POOL[:5], {"A": 0.0})
        with pytest.raises(ProtocolError, match="exploration"):
            ExplorationView(results, POOL[:6])


class TestConfirm:
    def run(self, scores, count=10, noise=0.001, hyps=None, seed=0):
        datasets = POOL[:count]
        results = per_dataset(datasets, scores, noise, seed)
        registry = Registry(25)
        for item in hyps or [hypothesis()]:
            registry.register(item)
        return protocol.confirm(registry, {"default": results})

    def test_a_clear_true_difference_is_confirmed(self):
        outcome = self.run({"A": 0.03, "B": 0.0})
        assert len(outcome) == 1 and outcome[0]["status"] == "confirmed"
        assert outcome[0]["p_value"] == pytest.approx(2 / 1024) and outcome[0]["adjusted_p_value"] == pytest.approx(2 / 1024)
        assert outcome[0]["median_difference"] == pytest.approx(0.03, abs=0.005) and outcome[0]["wins"] == 10

    def test_noise_alone_is_not_confirmed(self):
        outcome = self.run({"A": 0.0, "B": 0.0}, noise=0.01)
        assert outcome[0]["status"] == "not_confirmed"

    def test_a_significant_difference_in_the_opposite_direction_is_reversed(self):
        outcome = self.run({"A": -0.03, "B": 0.0})
        assert outcome[0]["status"] == "reversed" and outcome[0]["median_difference"] < 0

    def test_too_few_datasets_make_it_not_testable(self):
        outcome = self.run({"A": 0.03, "B": 0.0}, count=5)
        assert outcome[0]["status"] == "not_testable" and outcome[0]["p_value"] is None

    def test_identical_scores_are_not_testable(self):
        outcome = self.run({"A": 0.0, "B": 0.0}, noise=0.0)
        assert outcome[0]["status"] == "not_testable"

    def test_every_registered_hypothesis_counts_in_the_correction(self):
        hyps = [hypothesis(id="H1", subject=("A",), other=("B",)), hypothesis(id="H2", subject=("A",), other=("C",)), hypothesis(id="H3", subject=("B",), other=("C",))]
        outcome = self.run({"A": 0.03, "B": 0.0, "C": -0.03}, hyps=hyps)
        assert [item["id"] for item in outcome] == ["H1", "H2", "H3"]
        ps = [item["p_value"] for item in outcome]
        adjusted = [item["adjusted_p_value"] for item in outcome]
        assert adjusted == pytest.approx(protocol.holm_adjust(ps))
        assert all(a >= p for a, p in zip(adjusted, ps))

    def test_the_correction_can_turn_a_borderline_result_into_not_confirmed(self):
        datasets = POOL[:8]
        generator = np.random.default_rng(1)
        rows = {}
        for dataset in datasets:
            base = generator.uniform(0.6, 0.9)
            rows[dataset] = {"A": {"roc_auc_mean": base + 0.01}, "B": {"roc_auc_mean": base}, "C": {"roc_auc_mean": base + 0.01 * generator.choice([-1, 1])}}
        registry = Registry(25)
        registry.register(hypothesis(id="H1", subject=("A",), other=("B",)))
        for index in range(12):
            registry.register(hypothesis(id=f"X{index}", subject=("A",), other=("C",), stage=f"s{index}"))
        outcome = protocol.confirm(registry, {"default": rows, **{f"s{index}": rows for index in range(12)}})
        first = outcome[0]
        assert first["p_value"] == pytest.approx(2 / 256) and first["adjusted_p_value"] > protocol.ALPHA and first["status"] == "not_confirmed"

    def test_the_benjamini_hochberg_value_differs_from_the_holm_value_when_it_should(self):
        hyps = [hypothesis(id="H1", subject=("A",), other=("B",)), hypothesis(id="H2", subject=("A",), other=("C",)), hypothesis(id="H3", subject=("B",), other=("C",))]
        outcome = self.run({"A": 0.01, "B": 0.0, "C": 0.005}, noise=0.004, hyps=hyps, seed=4)
        ps = [item["p_value"] for item in outcome]
        assert [item["q_value"] for item in outcome] == pytest.approx(protocol.bh_adjust(ps))
        assert [item["q_value"] for item in outcome] != pytest.approx([item["adjusted_p_value"] for item in outcome])

    def test_the_benjamini_hochberg_value_is_reported_too(self):
        outcome = self.run({"A": 0.03, "B": 0.0})
        assert outcome[0]["q_value"] == pytest.approx(2 / 1024)

    def test_each_hypothesis_is_tested_on_the_results_of_its_own_stage(self):
        default = per_dataset(POOL[:10], {"A": 0.03, "B": 0.0}, 0.001)
        tuned = per_dataset(POOL[:10], {"A": 0.0, "B": 0.03}, 0.001)
        registry = Registry(25)
        registry.register(hypothesis(id="H1", stage="default"))
        registry.register(hypothesis(id="H2", stage="tuned"))
        outcome = protocol.confirm(registry, {"default": default, "tuned": tuned})
        assert [item["status"] for item in outcome] == ["confirmed", "reversed"]

    def test_a_stage_without_results_is_refused(self):
        registry = Registry(25)
        registry.register(hypothesis(stage="tuned"))
        with pytest.raises(ProtocolError, match="tuned"):
            protocol.confirm(registry, {"default": {}})

    def test_a_group_of_models_is_compared_by_its_best_member(self):
        datasets = POOL[:10]
        rows = {dataset: {"A1": {"roc_auc_mean": 0.80}, "A2": {"roc_auc_mean": 0.90 + 0.001 * index}, "B": {"roc_auc_mean": 0.85}} for index, dataset in enumerate(datasets)}
        registry = Registry(25)
        registry.register(hypothesis(subject=("A1", "A2")))
        outcome = protocol.confirm(registry, {"default": rows})
        assert outcome[0]["status"] == "confirmed" and outcome[0]["median_difference"] == pytest.approx(0.055, abs=0.01)

    def test_nothing_registered_gives_nothing(self):
        assert protocol.confirm(Registry(25), {}) == []

    def test_a_missing_model_is_refused(self):
        rows = per_dataset(POOL[:10], {"A": 0.0})
        registry = Registry(25)
        registry.register(hypothesis())
        with pytest.raises(ProtocolError):
            protocol.confirm(registry, {"default": rows})


class TestAdjustments:
    def test_holm_is_the_one_of_the_campaign_engine(self):
        from app.campaign.stats import holm_adjust

        assert protocol.holm_adjust is holm_adjust

    @pytest.mark.parametrize("values,expected", [
        ([0.01, 0.04, 0.03], [0.03, 0.04, 0.04]),
        ([0.5], [0.5]),
        ([0.001, 0.2], [0.002, 0.2]),
        ([], []),
    ])
    def test_benjamini_hochberg(self, values, expected):
        assert protocol.bh_adjust(values) == pytest.approx(expected)

    def test_benjamini_hochberg_is_monotone_and_at_most_one(self):
        values = [0.9, 0.001, 0.8, 0.02, 0.3, 0.04]
        adjusted = protocol.bh_adjust(values)
        order = sorted(range(len(values)), key=lambda index: values[index])
        assert all(adjusted[order[i]] <= adjusted[order[i + 1]] + 1e-12 for i in range(len(order) - 1))
        assert max(adjusted) <= 1.0 and all(a >= v for a, v in zip(adjusted, values))

    def test_benjamini_hochberg_is_never_larger_than_holm(self):
        values = [0.001, 0.004, 0.02, 0.03, 0.2]
        assert all(b <= h + 1e-12 for b, h in zip(protocol.bh_adjust(values), protocol.holm_adjust(values)))

    def test_math_is_used_for_the_bound(self):
        assert protocol.max_hypotheses(10) == math.ceil(0.05 * 2 ** 9) - 1
