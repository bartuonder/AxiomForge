import json
import random

import pytest

from app.campaign.analysis import analyze_campaign
from app.campaign.runner import run_campaign
from app.datasets import DATASETS, benchmark_keys
from app.seeds import SPLIT_SEEDS
from app.variants import baseline_name, expected_keys
from tools import null_seed

MODELS = ["RandomForest", "MLP", "DecisionTree"]
KEYS = benchmark_keys()


def fake_execute(spread=0.004, shift=0.0):
    generator = random.Random(5)

    def execute(script, schema):
        dataset = next(key for key in KEYS if DATASETS[key]["config"] in script)
        base = 0.7 + 0.02 * KEYS.index(dataset)
        lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
        spec = null_seed.null_spec(MODELS, datasets=KEYS)
        for _ in SPLIT_SEEDS:
            for key in expected_keys(MODELS, spec):
                value = base + generator.gauss(0, spread) + (shift if key in MODELS else 0.0)
                lines.append(
                    f"model={key} accuracy={value:.4f} f1={value - 0.05:.4f} roc_auc={value:.4f} pr_auc={value - 0.02:.4f} "
                    "train_seconds=0.1000 tn=500 fp=100 fn=100 tp=500"
                )
        return "\n".join(lines)

    return execute


def analyzed(execute):
    spec = null_seed.null_spec(MODELS, datasets=KEYS)
    outcome = run_campaign(spec, execute, workers=1)
    return spec, outcome, analyze_campaign(spec, outcome)


class TestNullSpec:
    def test_every_model_gets_only_a_different_random_state(self):
        spec = null_seed.null_spec(MODELS, seed=7, datasets=KEYS)
        assert spec["params"] == {model: {"random_state": 7} for model in MODELS}
        assert spec["models"] == MODELS and spec["datasets"] == KEYS

    def test_it_is_a_valid_campaign_apart_from_the_seed(self):
        spec = null_seed.null_spec()
        assert spec["models"] == null_seed.MODELS and len(spec["datasets"]) == len(benchmark_keys())
        assert spec["tuning"] == {} and spec["claims"]

    def test_the_seed_must_differ_from_the_one_of_the_control(self):
        with pytest.raises(ValueError, match="differ"):
            null_seed.null_spec(MODELS, seed=0)

    def test_the_script_trains_the_control_with_the_fixed_seed(self):
        from app.campaign.protocol import build_script

        spec = null_seed.null_spec(MODELS, seed=3, datasets=KEYS)
        script = build_script(KEYS[0], spec["models"], spec["params"], SPLIT_SEEDS)
        assert "RandomForestClassifier(random_state=3)" in script
        assert "RandomForestClassifier(random_state=0)" in script
        assert baseline_name("RandomForest") in script

    def test_only_models_whose_score_depends_on_the_seed_are_used(self):
        assert set(null_seed.MODELS) <= {"RandomForest", "ExtraTrees", "MLP", "DecisionTree", "GradientBoosting", "AdaBoost"}
        assert len(null_seed.MODELS) >= 4


class TestSummary:
    def test_it_counts_the_effects_of_each_model(self):
        _, _, analysis = analyzed(fake_execute())
        result = null_seed.summarize(analysis)
        assert result["models"] == MODELS
        assert result["effects"] == len(MODELS) * 3
        assert sum(item["effects"] for item in result["by_model"].values()) == result["effects"]
        for item in result["by_model"].values():
            assert item["effects"] == 3 and set(item) >= {"testable", "raw_significant", "family_significant", "strict_significant", "median_differences"}

    def test_noise_alone_gives_few_decisions(self):
        _, _, analysis = analyzed(fake_execute(spread=0.004))
        result = null_seed.summarize(analysis)
        assert result["strict_significant"] == 0
        assert result["family_significant"] <= 1
        assert result["testable"] >= 1

    def test_a_real_shift_is_detected_in_every_effect(self):
        _, _, analysis = analyzed(fake_execute(spread=0.0005, shift=0.02))
        result = null_seed.summarize(analysis)
        assert result["testable"] == result["effects"]
        assert result["strict_significant"] == result["effects"] and result["raw_significant"] == result["effects"]

    def test_the_rates_are_shares_of_the_testable_effects_with_an_interval(self):
        _, _, analysis = analyzed(fake_execute(spread=0.0005, shift=0.02))
        result = null_seed.summarize(analysis)
        assert result["raw_rate"] == 1.0
        low, high = result["raw_rate_interval"]
        assert 0.0 < low < 1.0 and high == pytest.approx(1.0, abs=1e-9)

    def test_nothing_testable_gives_no_rate(self):
        result = null_seed.summarize({"models": MODELS, "parameter_effects": []})
        assert result["effects"] == 0 and result["raw_rate"] is None and result["raw_rate_interval"] is None

    def test_a_failed_analysis_is_reported(self):
        with pytest.raises(ValueError, match="nothing can be compared"):
            null_seed.summarize({"coverage": {}, "error": "no dataset finished, so nothing can be compared"})

    def test_the_summary_is_plain_json(self):
        _, _, analysis = analyzed(fake_execute())
        json.dumps(null_seed.summarize(analysis))

    def test_the_median_difference_is_kept_per_metric(self):
        _, _, analysis = analyzed(fake_execute(spread=0.0005, shift=0.02))
        medians = null_seed.summarize(analysis)["by_model"]["RandomForest"]["median_differences"]
        assert set(medians) == {"roc_auc", "pr_auc", "f1"}
        assert all(value == pytest.approx(0.02, abs=0.004) for value in medians.values())


def row(model, metric, testable, p_value, significant, strict, median=0.01, mean=0.5):
    return {"model": model, "metric": metric, "testable": testable, "p_value": p_value, "significant": significant, "significant_all": strict, "median_difference": median, "mean_difference": mean}


class TestCounts:
    ANALYSIS = {
        "models": ["A", "B"],
        "parameter_effects": [
            row("A", "roc_auc", True, 0.01, True, True, median=0.011),
            row("A", "pr_auc", True, 0.20, False, False, median=0.022),
            row("A", "f1", False, 0.001, False, False, median=0.033),
            row("B", "roc_auc", True, 0.04, True, False, median=0.044),
            row("B", "pr_auc", True, 0.06, False, False, median=0.055),
        ],
    }

    def test_each_kind_of_count_has_its_own_rule(self):
        result = null_seed.summarize(self.ANALYSIS)
        assert result["effects"] == 5 and result["testable"] == 4
        assert result["raw_significant"] == 2 and result["family_significant"] == 2 and result["strict_significant"] == 1
        assert result["by_model"]["A"] | {"median_differences": None} == {"effects": 3, "testable": 2, "raw_significant": 1, "family_significant": 1, "strict_significant": 1, "median_differences": None}
        assert result["by_model"]["B"] | {"median_differences": None} == {"effects": 2, "testable": 2, "raw_significant": 1, "family_significant": 1, "strict_significant": 0, "median_differences": None}

    def test_family_and_strict_counts_are_not_mixed_up(self):
        analysis = {"models": ["A"], "parameter_effects": [row("A", "roc_auc", True, 0.04, True, False), row("A", "pr_auc", True, 0.5, False, False)]}
        result = null_seed.summarize(analysis)
        assert result["family_significant"] == 1 and result["strict_significant"] == 0

    def test_the_raw_threshold_is_five_percent(self):
        analysis = {"models": ["A"], "parameter_effects": [row("A", "roc_auc", True, 0.049, False, False), row("A", "pr_auc", True, 0.051, False, False), row("A", "f1", True, 0.3, False, False)]}
        assert null_seed.summarize(analysis)["raw_significant"] == 1

    def test_the_rate_uses_the_testable_effects(self):
        result = null_seed.summarize(self.ANALYSIS)
        assert result["raw_rate"] == 0.5

    def test_the_median_not_the_mean_is_kept(self):
        assert null_seed.summarize(self.ANALYSIS)["by_model"]["A"]["median_differences"] == {"roc_auc": 0.011, "pr_auc": 0.022, "f1": 0.033}

    def test_each_model_counts_only_its_own_rows(self):
        analysis = {"models": ["A", "B"], "parameter_effects": [row("A", "roc_auc", True, 0.01, True, True)]}
        by_model = null_seed.summarize(analysis)["by_model"]
        assert by_model["A"]["effects"] == 1 and by_model["B"]["effects"] == 0 and by_model["B"]["raw_significant"] == 0


class TestRun:
    def test_it_runs_the_datasets_and_summarizes(self):
        result = null_seed.run(MODELS, 1, KEYS, fake_execute(), workers=1)
        assert result["summary"]["effects"] == len(MODELS) * 3
        assert result["finished"] == len(KEYS) and result["failed"] == {}
        assert result["seed"] == 1

    def test_a_failed_dataset_is_reported_and_the_rest_still_counts(self):
        good = fake_execute()

        def flaky(script, schema):
            if DATASETS[KEYS[0]]["config"] in script:
                raise RuntimeError("sandbox died")
            return good(script, schema)

        result = null_seed.run(MODELS, 1, KEYS, flaky, workers=1)
        assert result["finished"] == len(KEYS) - 1 and KEYS[0] in result["failed"]
        assert result["summary"]["effects"] == len(MODELS) * 3


class TestCommandLine:
    def test_it_prints_the_summary_and_writes_the_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(null_seed, "run", lambda models, seed, datasets, execute=None, workers=3: {"seed": seed, "finished": 1, "failed": {}, "summary": {"effects": 1}})
        target = tmp_path / "out.json"
        assert null_seed.main(["--seed", "4", "--out", str(target)]) == 0
        assert json.loads(target.read_text(encoding="utf-8"))["seed"] == 4
        assert '"effects": 1' in capsys.readouterr().out

    def test_the_models_and_datasets_can_be_chosen(self, monkeypatch, capsys):
        seen = {}

        def fake(models, seed, datasets, execute=None, workers=3):
            seen.update(models=models, datasets=datasets, workers=workers)
            return {"seed": seed, "finished": 0, "failed": {}, "summary": {}}

        monkeypatch.setattr(null_seed, "run", fake)
        assert null_seed.main(["--models", "RandomForest,MLP", "--datasets", "tb_credit", "--workers", "2"]) == 0
        assert seen == {"models": ["RandomForest", "MLP"], "datasets": ["tb_credit"], "workers": 2}

    def test_the_seed_of_the_control_is_refused(self, capsys):
        assert null_seed.main(["--seed", "0"]) == 2
        assert "differ" in capsys.readouterr().err
