import pytest

from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report
from app.campaign.stats import ALPHA
from app.datasets import benchmark_keys

MODELS = ["RandomForest", "DecisionTree", "GradientBoosting", "HistGradientBoosting", "GaussianNB", "KNN", "MLP"]
CLAIMS = [{"id": "C1", "statement": "Forests beat trees", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"], "subject": ["RandomForest"], "other": ["DecisionTree"]}]
KEYS = benchmark_keys()
METRICS = ("roc_auc", "pr_auc", "f1")
TUNED = {"iterations": 12, "folds": 3}


def spec_for(models, tuning=None, params=None):
    return {"title": "T", "models": models, "params": params or {}, "tuning": tuning or {}, "claims": CLAIMS, "datasets": KEYS, "source": {}}


def outcome(models, gain):
    datasets = {}
    for index, key in enumerate(KEYS):
        summary = {}
        for number, model in enumerate(models):
            base = 0.6 + 0.02 * number + 0.001 * index
            summary[model] = {f"{metric}_mean": base + gain(model, index) for metric in METRICS}
            summary[f"{model}__default"] = {f"{metric}_mean": base for metric in METRICS}
        datasets[key] = {
            "summary": summary,
            "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
            "descriptors": {},
            "provenance": {},
            "tuning": {},
            "seconds": 1.0,
            "attempts": 1,
            "script": key,
        }
    return {"order": list(KEYS), "datasets": datasets, "failed": {}}


def always(model, index):
    return 0.01 + 0.0005 * index


def rows_of(analysis, model):
    return [row for row in analysis["parameter_effects"] if row["model"] == model]


class TestFamily:
    def test_the_metrics_of_one_model_are_the_family(self):
        spec = spec_for(MODELS, TUNED)
        analysis = analyze_campaign(spec, outcome(MODELS, always))
        for model in MODELS:
            for row in rows_of(analysis, model):
                assert row["adjusted_p_value"] == pytest.approx(3 * 2 / 2**9)
                assert row["significant"] is True

    def test_seven_tuned_models_are_significant_per_model_but_not_across_all_models(self):
        spec = spec_for(MODELS, TUNED)
        analysis = analyze_campaign(spec, outcome(MODELS, always))
        for row in analysis["parameter_effects"]:
            assert row["adjusted_p_value_all"] == pytest.approx(21 * 2 / 2**9)
            assert row["adjusted_p_value_all"] > ALPHA and row["significant_all"] is False

    def test_few_models_stay_significant_under_the_stricter_adjustment(self):
        models = ["RandomForest", "DecisionTree"]
        analysis = analyze_campaign(spec_for(models, TUNED), outcome(models, always))
        for row in analysis["parameter_effects"]:
            assert row["adjusted_p_value_all"] == pytest.approx(6 * 2 / 2**9)
            assert row["significant"] is True and row["significant_all"] is True

    def test_a_model_without_an_effect_does_not_change_the_family_of_another(self):
        def gain(model, index):
            return 0.01 + 0.0005 * index if model == "RandomForest" else 0.0

        models = ["RandomForest", "DecisionTree"]
        analysis = analyze_campaign(spec_for(models, TUNED), outcome(models, gain))
        assert all(row["significant"] for row in rows_of(analysis, "RandomForest"))
        assert not any(row["significant"] for row in rows_of(analysis, "DecisionTree"))
        assert all(row["adjusted_p_value"] is None and row["adjusted_p_value_all"] is None for row in rows_of(analysis, "DecisionTree"))

    def test_the_strict_adjustment_counts_only_testable_rows(self):
        def gain(model, index):
            return 0.01 + 0.0005 * index if model == "RandomForest" else 0.0

        models = ["RandomForest", "DecisionTree"]
        analysis = analyze_campaign(spec_for(models, TUNED), outcome(models, gain))
        assert all(row["adjusted_p_value_all"] == pytest.approx(3 * 2 / 2**9) for row in rows_of(analysis, "RandomForest"))

    def test_listed_parameters_use_the_same_family(self):
        models = ["RandomForest", "DecisionTree"]
        spec = spec_for(models, params={"RandomForest": {"n_estimators": 200}, "DecisionTree": {"max_depth": 3}})
        analysis = analyze_campaign(spec, outcome(models, always))
        assert all(row["adjusted_p_value"] == pytest.approx(3 * 2 / 2**9) for row in analysis["parameter_effects"])

    def test_too_few_datasets_leave_every_effect_untested(self):
        spec = spec_for(["RandomForest", "DecisionTree"], TUNED)
        data = outcome(["RandomForest", "DecisionTree"], always)
        for key in KEYS[4:]:
            del data["datasets"][key]
        data["order"] = KEYS[:4]
        analysis = analyze_campaign(spec, data)
        assert all(row["significant"] is False and row["significant_all"] is False and row["adjusted_p_value_all"] is None for row in analysis["parameter_effects"])


class TestReport:
    def render(self, models, gain, tuning=TUNED, params=None):
        spec = spec_for(models, tuning, params)
        data = outcome(models, gain)
        analysis = analyze_campaign(spec, data)
        markdown, _ = render_report(spec, data, analysis)
        return markdown

    def limitations(self, markdown):
        return markdown.split("## Limitations")[1].split("## Evidence ledger")[0]

    def test_the_statistics_paragraph_names_the_family_of_the_effects(self):
        markdown = self.render(MODELS, always)
        assert "The effect of tuning is adjusted across the metrics of each model." in markdown.split("## Protocol")[1].split("## Results")[0]

    def test_listed_parameters_are_named_in_the_family_sentence(self):
        markdown = self.render(["RandomForest", "DecisionTree"], always, tuning={}, params={"RandomForest": {"n_estimators": 200}, "DecisionTree": {"max_depth": 3}})
        assert "The effect of the listed parameters is adjusted across the metrics of each model." in markdown

    def test_no_effects_leave_the_paragraph_unchanged(self):
        spec = {**spec_for(["RandomForest", "DecisionTree"]), "params": {}}
        data = outcome(["RandomForest", "DecisionTree"], always)
        markdown, _ = render_report(spec, data, analyze_campaign(spec, data))
        assert "is adjusted across the metrics of each model" not in markdown

    def test_the_limitations_say_how_many_effects_survive_the_strict_adjustment(self):
        text = self.limitations(self.render(MODELS, always))
        assert "Significant tuning effects within their model: 21; of these, 0 remain significant when the adjustment spans all models and metrics." in text

    def test_all_surviving_effects_are_counted(self):
        text = self.limitations(self.render(["RandomForest", "DecisionTree"], always))
        assert "Significant tuning effects within their model: 6; of these, 6 remain significant when the adjustment spans all models and metrics." in text

    def test_listed_parameter_effects_use_their_own_wording(self):
        text = self.limitations(self.render(["RandomForest", "DecisionTree"], always, tuning={}, params={"RandomForest": {"n_estimators": 200}, "DecisionTree": {"max_depth": 3}}))
        assert "Significant parameter effects within their model: 6; of these, 6 remain significant" in text

    def test_a_single_effect_model_needs_no_such_sentence(self):
        markdown = self.render(["RandomForest", "DecisionTree"], always, tuning={}, params={"RandomForest": {"n_estimators": 200}})
        assert "remain significant when the adjustment spans all models" not in markdown

    def test_a_second_effect_model_without_a_significant_effect_still_gets_the_sentence(self):
        markdown = self.render(["RandomForest", "DecisionTree"], lambda model, index: 0.01 + 0.0005 * index if model == "RandomForest" else 0.0)
        assert "Significant tuning effects within their model: 3; of these, 3 remain significant" in markdown

    def test_without_a_significant_effect_there_is_no_such_sentence(self):
        markdown = self.render(["RandomForest", "DecisionTree"], lambda model, index: 0.0)
        assert "remain significant when the adjustment spans all models" not in markdown


@pytest.fixture(scope="module")
def mlflow_store(tmp_path_factory):
    import mlflow

    import app.campaign.tracking as tracking

    folder = tmp_path_factory.mktemp("mlflow_family")
    patch = pytest.MonkeyPatch()
    patch.chdir(folder)
    uri = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"
    patch.setattr(tracking, "MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield uri
    patch.undo()


class TestTracking:
    def test_the_strict_adjustment_is_logged_beside_the_family_one(self, mlflow_store):
        import mlflow

        import app.campaign.tracking as tracking

        spec = spec_for(MODELS, TUNED)
        data = outcome(MODELS, always)
        analysis = analyze_campaign(spec, data)
        markdown, ledger = render_report(spec, data, analysis)
        metrics = mlflow.get_run(tracking.log_campaign("family", spec, data, analysis, markdown, ledger, "completed")).data.metrics
        assert metrics["significant_parameter_effects"] == 21.0 and metrics["significant_parameter_effects_all"] == 0.0
        assert metrics["effect/RandomForest/roc_auc/adjusted_p_value"] == pytest.approx(3 * 2 / 2**9)
        assert metrics["effect/RandomForest/roc_auc/adjusted_p_value_all"] == pytest.approx(21 * 2 / 2**9)
