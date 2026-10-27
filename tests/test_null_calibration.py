import json

import numpy as np
import pytest

import tools.null_calibration as calibration

REPLICATIONS = 120


def run(effect=0.0, datasets=9, noise=0.01, replications=REPLICATIONS, seed=7, metrics=3, spread=0.0):
    return calibration.simulate(replications, datasets, noise, effect, np.random.default_rng(seed), metrics, spread)


class TestScores:
    def test_the_per_dataset_scores_have_both_models_and_every_metric(self):
        scores = calibration.draw_scores(np.random.default_rng(0), 4, 0.01, 0.0, 3, 0.0)
        assert list(scores) == ["d0", "d1", "d2", "d3"]
        assert set(scores["d0"]) == {"A", "B"} and set(scores["d0"]["A"]) == {"roc_auc_mean", "pr_auc_mean", "f1_mean"}

    def test_a_positive_effect_lifts_model_a(self):
        scores = calibration.draw_scores(np.random.default_rng(0), 50, 0.001, 0.02, 3, 0.0)
        gaps = [scores[key]["A"]["roc_auc_mean"] - scores[key]["B"]["roc_auc_mean"] for key in scores]
        assert 0.015 < np.mean(gaps) < 0.025

    def test_no_effect_leaves_the_gap_centred_on_zero(self):
        scores = calibration.draw_scores(np.random.default_rng(0), 400, 0.01, 0.0, 3, 0.0)
        gaps = [scores[key]["A"]["roc_auc_mean"] - scores[key]["B"]["roc_auc_mean"] for key in scores]
        assert abs(np.mean(gaps)) < 0.002

    def test_scores_stay_between_zero_and_one(self):
        scores = calibration.draw_scores(np.random.default_rng(1), 200, 0.2, 0.3, 3, 0.1)
        values = [value for entry in scores.values() for model in entry.values() for value in model.values()]
        assert min(values) >= 0.0 and max(values) <= 1.0

    def test_the_metric_count_is_respected(self):
        scores = calibration.draw_scores(np.random.default_rng(0), 3, 0.01, 0.0, 1, 0.0)
        assert set(scores["d0"]["A"]) == {"roc_auc_mean"}

    def test_the_same_seed_gives_the_same_scores(self):
        first = calibration.draw_scores(np.random.default_rng(5), 3, 0.01, 0.0, 3, 0.0)
        second = calibration.draw_scores(np.random.default_rng(5), 3, 0.01, 0.0, 3, 0.0)
        assert first == second


class TestSimulation:
    def test_the_counts_cover_every_replication(self):
        result = run()
        assert result["replications"] == REPLICATIONS and sum(result["verdicts"].values()) == REPLICATIONS
        assert set(result["verdicts"]) == {"replicated", "contradicted", "partially_replicated", "inconclusive", "not_testable"}

    def test_the_decisive_rate_is_the_share_of_replicated_and_contradicted(self):
        result = run()
        assert result["decisive_rate"] == pytest.approx((result["verdicts"]["replicated"] + result["verdicts"]["contradicted"]) / REPLICATIONS)

    def test_the_false_positive_rate_of_a_null_comparison_stays_low(self):
        result = run(effect=0.0, replications=400)
        assert result["any_claim_rate"] < 0.06

    def test_a_large_effect_is_found(self):
        result = run(effect=0.03, noise=0.005, replications=80)
        assert result["verdicts"]["replicated"] >= 76 and result["verdicts"]["contradicted"] == 0

    def test_a_negative_effect_is_refuted(self):
        result = run(effect=-0.03, noise=0.005, replications=80)
        assert result["verdicts"]["contradicted"] >= 76 and result["verdicts"]["replicated"] == 0

    def test_fewer_datasets_than_the_minimum_cannot_be_decided(self):
        result = run(effect=0.05, noise=0.001, datasets=4, replications=20)
        assert result["verdicts"]["not_testable"] == 20 and result["decisive_rate"] == 0.0

    def test_the_same_seed_gives_the_same_result(self):
        assert run(seed=3) == run(seed=3)

    def test_different_seeds_differ_in_detail(self):
        assert run(seed=1, replications=300)["verdicts"] != run(seed=2, replications=300)["verdicts"]

    def test_a_shared_dataset_effect_does_not_create_a_difference(self):
        result = run(effect=0.0, spread=0.05, replications=300)
        assert result["any_claim_rate"] < 0.06

    def test_the_rates_are_between_zero_and_one(self):
        result = run()
        assert 0.0 <= result["decisive_rate"] <= 1.0 and 0.0 <= result["any_claim_rate"] <= 1.0


class TestCommand:
    def test_it_prints_one_json_line_per_scenario(self, capsys):
        assert calibration.main(["--replications", "30", "--seed", "1"]) == 0
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert [line["scenario"] for line in lines] == [name for name, *_ in calibration.SCENARIOS]
        assert all(line["replications"] == 30 and "decisive_rate" in line and "wilson95" in line for line in lines)

    def test_the_wilson_interval_belongs_to_the_decisive_count(self, capsys):
        calibration.main(["--replications", "50", "--seed", "1"])
        line = json.loads(capsys.readouterr().out.splitlines()[0])
        low, high = line["wilson95"]
        assert low <= line["decisive_rate"] <= high

    def test_the_datasets_can_be_chosen(self, capsys):
        calibration.main(["--replications", "10", "--datasets", "4"])
        assert all(json.loads(line)["datasets"] == 4 for line in capsys.readouterr().out.splitlines())

    def test_a_bad_replication_count_is_refused(self):
        with pytest.raises(SystemExit):
            calibration.main(["--replications", "0"])


class TestEdges:
    def test_the_spread_moves_the_metrics_of_a_dataset_apart(self):
        flat = calibration.draw_scores(np.random.default_rng(0), 60, 0.001, 0.0, 3, 0.0)
        shifted = calibration.draw_scores(np.random.default_rng(0), 60, 0.001, 0.0, 3, 0.1)

        def spread_of(scores):
            return np.mean([max(entry["A"].values()) - min(entry["A"].values()) for entry in scores.values()])

        assert spread_of(flat) < 0.005 and spread_of(shifted) > 0.03

    def capture(self, monkeypatch, verdicts):
        seen = []
        queue = iter(verdicts)

        def fake(scores, claim):
            seen.append(claim)
            return {"verdict": next(queue)}

        monkeypatch.setattr(calibration, "claim_verdict", fake)
        return seen

    def test_the_claim_uses_the_requested_number_of_metrics(self, monkeypatch):
        seen = self.capture(monkeypatch, ["inconclusive"] * 2)
        calibration.simulate(2, 9, 0.01, 0.0, np.random.default_rng(0), metrics=1)
        assert seen[0]["metrics"] == ["roc_auc"] and seen[0]["subject"] == ["A"] and seen[0]["other"] == ["B"]

    def test_the_claim_defaults_to_all_three_metrics(self, monkeypatch):
        seen = self.capture(monkeypatch, ["inconclusive"])
        calibration.simulate(1, 9, 0.01, 0.0, np.random.default_rng(0))
        assert seen[0]["metrics"] == ["roc_auc", "pr_auc", "f1"]

    def test_a_partly_confirmed_claim_counts_as_any_but_not_as_decisive(self, monkeypatch):
        self.capture(monkeypatch, ["replicated", "contradicted", "partially_replicated", "inconclusive"])
        result = calibration.simulate(4, 9, 0.01, 0.0, np.random.default_rng(0))
        assert result["decisive_rate"] == 0.5 and result["any_claim_rate"] == 0.75
        assert result["verdicts"] == {"replicated": 1, "contradicted": 1, "partially_replicated": 1, "inconclusive": 1, "not_testable": 0}

    def test_an_untestable_run_is_not_any_claim(self, monkeypatch):
        self.capture(monkeypatch, ["not_testable", "replicated"])
        assert calibration.simulate(2, 9, 0.01, 0.0, np.random.default_rng(0))["any_claim_rate"] == 0.5

    def test_the_default_number_of_datasets_is_nine(self, monkeypatch):
        seen = []

        def fake(replications, datasets, noise, effect, rng, metrics=3, spread=0.0):
            seen.append((replications, datasets))
            return {"replications": replications, "verdicts": {"replicated": 0, "contradicted": 0}, "decisive_rate": 0.0, "any_claim_rate": 0.0}

        monkeypatch.setattr(calibration, "simulate", fake)
        calibration.main(["--replications", "5"])
        assert {item for item in seen} == {(5, 9)}

    def test_the_command_uses_the_given_number_of_datasets(self, capsys):
        calibration.main(["--replications", "5", "--datasets", "4"])
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert all(line["verdicts"]["not_testable"] == 5 for line in lines)

    def test_the_command_seeds_its_simulation(self, capsys):
        calibration.main(["--replications", "40", "--seed", "5"])
        first = json.loads(capsys.readouterr().out.splitlines()[0])
        name, effect, noise = calibration.SCENARIOS[0]
        expected = calibration.simulate(40, 9, noise, effect, np.random.default_rng(5))
        assert first["verdicts"] == expected["verdicts"]

    def test_the_wilson_interval_is_the_one_of_the_decisive_count(self, capsys):
        from app.campaign.hard_benchmark import wilson_interval

        calibration.main(["--replications", "60", "--seed", "2"])
        for line in capsys.readouterr().out.splitlines():
            data = json.loads(line)
            decisive = data["verdicts"]["replicated"] + data["verdicts"]["contradicted"]
            low, high = wilson_interval(decisive, 60)
            assert data["wilson95"] == [round(low, 4), round(high, 4)]

    def test_the_scenarios_are_the_documented_ones(self):
        assert [(name, effect) for name, effect, _ in calibration.SCENARIOS] == [
            ("null (no true difference)", 0.0),
            ("small true difference (+0.005)", 0.005),
            ("moderate true difference (+0.01)", 0.01),
            ("large true difference (+0.03)", 0.03),
        ]
