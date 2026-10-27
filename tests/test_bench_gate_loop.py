import pytest

from app.campaign.tuning import DEFAULT_FOLDS
from tools import bench_gate_loop


class TestGateSpec:
    def test_without_tuning_it_is_the_plain_benchmark(self):
        spec = bench_gate_loop.gate_spec()
        assert not spec.get("tuning")
        assert any(str(item).startswith("No hyperparameter search") for item in spec["source"]["deviations"])

    def test_with_tuning_the_spec_is_tuned_and_the_note_names_the_search(self):
        spec = bench_gate_loop.gate_spec(12)
        assert spec["tuning"]["iterations"] == 12 and spec["tuning"]["folds"] == DEFAULT_FOLDS
        deviations = spec["source"]["deviations"]
        assert not any(str(item).startswith("No hyperparameter search") for item in deviations)
        assert any("random search of 12 configurations" in str(item) for item in deviations)

    def test_the_number_of_other_deviations_is_kept(self):
        assert len(bench_gate_loop.gate_spec(12)["source"]["deviations"]) == len(bench_gate_loop.gate_spec()["source"]["deviations"])

    def test_the_models_and_claims_do_not_change(self):
        plain, tuned = bench_gate_loop.gate_spec(), bench_gate_loop.gate_spec(12)
        assert plain["models"] == tuned["models"] and plain["claims"] == tuned["claims"] and plain["datasets"] == tuned["datasets"]

    def test_a_bad_iteration_count_is_refused(self):
        with pytest.raises(Exception):
            bench_gate_loop.gate_spec(1)


class TestCommand:
    def test_a_campaign_without_artifacts_is_refused(self, capsys, monkeypatch, tmp_path):
        import app.campaign.store as store

        monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
        assert bench_gate_loop.main(["nothing", "1"]) == 2
        assert "no stored analysis" in capsys.readouterr().out

    def test_the_tuning_option_reaches_the_spec(self, monkeypatch):
        import app.campaign.store as store

        seen = []
        monkeypatch.setattr(bench_gate_loop, "gate_spec", lambda tuning=None: seen.append(tuning) or {})
        monkeypatch.setattr(store, "load_analysis", lambda campaign: None)
        bench_gate_loop.main(["x", "1", "--tuning", "12"])
        bench_gate_loop.main(["x", "1"])
        assert seen == [12, None]
