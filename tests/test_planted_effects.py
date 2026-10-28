import json

import numpy as np
import pytest

from tools import planted_effects as planted

MODELS = [f"M{index}" for index in range(6)]


def world(delta=0.02, strong=2, sigma=0.01, datasets=16):
    return planted.World(models=MODELS, abilities={model: (delta if index < strong else 0.0) for index, model in enumerate(MODELS)}, interaction=sigma, datasets=datasets)


class TestTruth:
    ABILITIES = {"A": 0.02, "B": 0.0, "C": 0.0}

    def test_a_correct_direction_is_a_true_discovery(self):
        assert planted.is_true("A", "B", self.ABILITIES) is True

    def test_the_wrong_direction_is_false(self):
        assert planted.is_true("B", "A", self.ABILITIES) is False

    def test_equal_models_are_a_false_discovery_in_either_direction(self):
        assert planted.is_true("B", "C", self.ABILITIES) is False and planted.is_true("C", "B", self.ABILITIES) is False

    def test_the_number_of_real_pairs_counts_the_unequal_ones(self):
        assert planted.real_pairs(self.ABILITIES) == 2
        assert planted.real_pairs({"A": 0.0, "B": 0.0}) == 0
        assert planted.real_pairs({"A": 0.0, "B": 0.01, "C": 0.02}) == 3


class TestTally:
    ABILITIES = {"A": 0.02, "B": 0.0, "C": 0.0}

    def test_it_counts_reports_false_ones_and_found_real_pairs(self):
        reports = [("A", "B"), ("B", "C"), ("C", "A")]
        assert planted.tally(reports, self.ABILITIES) == {"reported": 3, "false": 2, "true": 1}

    def test_the_same_real_pair_reported_twice_is_found_once(self):
        assert planted.tally([("A", "B"), ("A", "B")], self.ABILITIES)["true"] == 1

    def test_nothing_reported(self):
        assert planted.tally([], self.ABILITIES) == {"reported": 0, "false": 0, "true": 0}


class TestSummary:
    def test_the_rates_over_replications(self):
        tallies = [{"reported": 4, "false": 1, "true": 3}, {"reported": 0, "false": 0, "true": 0}, {"reported": 2, "false": 2, "true": 0}]
        result = planted.summarize(tallies, real=3)
        assert result["family_wise_error"] == pytest.approx(2 / 3)
        assert result["false_discovery_proportion"] == pytest.approx((0.25 + 0 + 1) / 3)
        assert result["power"] == pytest.approx((3 / 3 + 0 + 0) / 3)
        assert result["mean_reported"] == pytest.approx(2.0)

    def test_without_any_real_pair_the_power_is_undefined(self):
        assert planted.summarize([{"reported": 1, "false": 1, "true": 0}], real=0)["power"] is None

    def test_an_interval_comes_with_the_family_wise_error(self):
        result = planted.summarize([{"reported": 1, "false": 1, "true": 0}] * 10 + [{"reported": 0, "false": 0, "true": 0}] * 90, real=0)
        low, high = result["family_wise_error_interval"]
        assert result["family_wise_error"] == 0.1 and low < 0.1 < high


class TestWorld:
    def test_the_scores_have_one_row_per_dataset_and_one_column_per_model(self):
        scores = planted.draw_scores(np.random.default_rng(0), world())
        assert scores.shape == (16, 6)

    def test_the_abilities_show_in_the_means(self):
        scores = planted.draw_scores(np.random.default_rng(0), world(delta=0.05, sigma=0.002, datasets=200))
        assert scores[:, 0].mean() - scores[:, 5].mean() == pytest.approx(0.05, abs=0.005)

    def test_the_draw_is_reproducible(self):
        assert np.array_equal(planted.draw_scores(np.random.default_rng(1), world()), planted.draw_scores(np.random.default_rng(1), world()))

    def test_the_dataset_level_changes_move_all_models_together(self):
        scores = planted.draw_scores(np.random.default_rng(0), world(sigma=0.0001, datasets=50))
        assert np.std(scores.mean(axis=1)) > 0.03

    def test_the_per_dataset_form_has_the_campaign_layout(self):
        scores = planted.draw_scores(np.random.default_rng(0), world())
        form = planted.as_per_dataset(scores, MODELS, ["d%d" % index for index in range(16)])
        assert set(form) == {"d%d" % index for index in range(16)}
        assert set(form["d0"]) == set(MODELS) and form["d0"]["M0"]["roc_auc_mean"] == pytest.approx(scores[0, 0])


class TestAgents:
    def run(self, agent, delta, reps=60, strong=2, seed=0, **kwargs):
        rng = np.random.default_rng(seed)
        tallies = []
        for _ in range(reps):
            model = world(delta=delta, strong=strong, **kwargs)
            scores = planted.draw_scores(rng, model)
            tallies.append(planted.tally(agent(scores, MODELS), model.abilities))
        return planted.summarize(tallies, planted.real_pairs(world(delta=delta, strong=strong).abilities))

    def test_the_uncorrected_all_pairs_agent_reports_false_discoveries_without_any_effect(self):
        result = self.run(planted.agent_uncorrected, 0.0, reps=200)
        assert result["family_wise_error"] > 0.3

    def test_the_holm_agent_keeps_the_family_wise_error_low_without_any_effect(self):
        result = self.run(planted.agent_all_pairs_holm, 0.0, reps=200)
        assert result["family_wise_error"] <= 0.12

    def test_the_protocol_agent_keeps_the_family_wise_error_low_without_any_effect(self):
        result = self.run(planted.agent_protocol, 0.0, reps=200)
        assert result["family_wise_error"] <= 0.12

    def test_the_same_data_agent_inflates_the_error_without_any_effect(self):
        same = self.run(planted.agent_same_data, 0.0, reps=200)
        protocol_result = self.run(planted.agent_protocol, 0.0, reps=200)
        assert same["family_wise_error"] > protocol_result["family_wise_error"]

    def test_a_large_effect_is_found_by_the_holm_and_the_protocol_agents(self):
        assert self.run(planted.agent_all_pairs_holm, 0.05, reps=40)["power"] > 0.7
        assert self.run(planted.agent_protocol, 0.05, reps=40)["power"] > 0.3

    def test_the_protocol_pays_for_its_safety_in_power(self):
        holm = self.run(planted.agent_all_pairs_holm, 0.02, reps=60)["power"]
        protocol_power = self.run(planted.agent_protocol, 0.02, reps=60)["power"]
        assert protocol_power <= holm + 0.05

    def test_an_agent_returns_pairs_of_model_names(self):
        scores = planted.draw_scores(np.random.default_rng(0), world(delta=0.05))
        for agent in (planted.agent_uncorrected, planted.agent_all_pairs_holm, planted.agent_same_data, planted.agent_protocol):
            for subject, other in agent(scores, MODELS):
                assert subject in MODELS and other in MODELS and subject != other


class TestAgentDetails:
    def crafted(self, explore_gap, confirm_gap):
        names = planted.dataset_names(16)
        explore, confirm = planted.protocol.split_pool(names, planted.EXPLORE, 0)
        rng = np.random.default_rng(0)
        scores = np.zeros((16, len(MODELS)))
        for row, name in enumerate(names):
            base = rng.uniform(0.6, 0.9)
            gap = explore_gap if name in explore else confirm_gap
            scores[row] = [base + gap, base, base, base, base, base]
        return scores + rng.normal(0, 0.0005, scores.shape), explore, confirm

    def test_the_winner_is_the_model_with_the_larger_median_not_the_first_name(self):
        scores = planted.draw_scores(np.random.default_rng(0), world(delta=0.0))
        scores[:, 3] += 0.1
        for agent in (planted.agent_uncorrected, planted.agent_all_pairs_holm):
            reports = agent(scores, MODELS)
            assert ("M3", "M0") in reports and ("M0", "M3") not in reports

    def test_identical_scores_are_never_reported(self):
        scores = np.tile(np.linspace(0.6, 0.9, 16)[:, None], (1, len(MODELS)))
        for agent in (planted.agent_uncorrected, planted.agent_all_pairs_holm, planted.agent_same_data, planted.agent_protocol):
            assert agent(scores, MODELS) == []

    def test_a_reversal_on_the_confirmation_datasets_is_not_reported(self):
        scores, _, _ = self.crafted(explore_gap=0.05, confirm_gap=-0.05)
        reports = planted.agent_protocol(scores, MODELS)
        assert ("M0", "M1") not in reports

    def test_the_same_effect_on_both_parts_is_reported(self):
        scores, _, _ = self.crafted(explore_gap=0.05, confirm_gap=0.05)
        assert ("M0", "M1") in planted.agent_protocol(scores, MODELS)

    def test_the_protocol_agent_registers_on_the_exploration_part_and_confirms_on_the_confirmation_part(self, monkeypatch):
        seen = {}
        original_propose, original_confirm = planted.generate.propose, planted.protocol.confirm

        def propose(view, *args, **kwargs):
            seen["explore"] = set(view.per_dataset)
            return original_propose(view, *args, **kwargs)

        def confirm(registry, results):
            seen["confirm"] = set(results["default"])
            return original_confirm(registry, results)

        monkeypatch.setattr(planted.generate, "propose", propose)
        monkeypatch.setattr(planted.protocol, "confirm", confirm)
        scores, explore, confirm_names = self.crafted(0.05, 0.05)
        planted.agent_protocol(scores, MODELS)
        assert seen["explore"] == set(explore) and seen["confirm"] == set(confirm_names) and len(explore) == 6

    def test_the_adaptive_agents_use_the_whole_part_of_the_data_they_are_given(self, monkeypatch):
        seen = {}
        original = planted.generate.propose

        def propose(view, *args, **kwargs):
            seen["datasets"] = len(view.datasets)
            return original(view, *args, **kwargs)

        monkeypatch.setattr(planted.generate, "propose", propose)
        planted.agent_same_data(np.zeros((16, len(MODELS))), MODELS)
        assert seen["datasets"] == 16

    def test_an_adaptive_agent_reports_at_most_the_stage_count(self):
        scores = planted.draw_scores(np.random.default_rng(0), planted.World(models=[f"M{i}" for i in range(8)], abilities={f"M{i}": 0.1 * i for i in range(8)}, interaction=0.002))
        models = [f"M{i}" for i in range(8)]
        assert len(planted.agent_protocol(scores, models)) == planted.PER_STAGE == 8
        assert len(planted.agent_same_data(scores, models)) == planted.PER_STAGE


class TestEvaluate:
    def test_it_returns_a_row_per_agent_and_setting(self):
        rows = planted.evaluate(reps=8, deltas=[0.0, 0.03], strong=2, sigma=0.01, models=MODELS, seed=0)
        assert [(row["delta"], row["agent"]) for row in rows] == [(delta, agent) for delta in (0.0, 0.03) for agent in planted.AGENTS]
        assert all({"family_wise_error", "false_discovery_proportion", "power", "mean_reported"} <= set(row) for row in rows)

    def test_the_interaction_noise_reaches_the_simulation(self):
        rows = planted.evaluate(reps=40, deltas=[0.0], strong=2, sigma=0.01, models=MODELS, seed=0)
        assert next(row for row in rows if row["agent"] == "uncorrected_all_pairs")["family_wise_error"] > 0.15

    def test_each_row_knows_how_many_real_pairs_there_were(self):
        rows = planted.evaluate(reps=4, deltas=[0.02], strong=2, sigma=0.01, models=MODELS, seed=0)
        assert {row["real_pairs"] for row in rows} == {2 * 4}

    def test_the_same_seed_gives_the_same_rows(self):
        first = planted.evaluate(reps=8, deltas=[0.02], strong=2, sigma=0.01, models=MODELS, seed=3)
        second = planted.evaluate(reps=8, deltas=[0.02], strong=2, sigma=0.01, models=MODELS, seed=3)
        assert first == second

    def test_it_is_plain_json(self):
        json.dumps(planted.evaluate(reps=4, deltas=[0.02], strong=2, sigma=0.01, models=MODELS, seed=0))


class TestCommandLine:
    def test_it_prints_a_table_and_writes_the_file(self, tmp_path, capsys):
        target = tmp_path / "out.json"
        assert planted.main(["--reps", "4", "--deltas", "0,0.03", "--out", str(target)]) == 0
        output = capsys.readouterr().out
        assert "agent" in output and "family-wise" in output.lower()
        assert len(json.loads(target.read_text(encoding="utf-8"))) == 2 * len(planted.AGENTS)

    def test_bad_numbers_are_refused(self, capsys):
        assert planted.main(["--reps", "0"]) == 2
        assert planted.main(["--strong", "99"]) == 2
