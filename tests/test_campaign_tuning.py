import ast
import contextlib
import importlib
import io
import math

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import train_test_split

import app.campaign.tuning as tuning
from app.campaign.protocol import ESTIMATORS
from app.campaign.tuning import (
    DEFAULT_FOLDS,
    DEFAULT_ITERATIONS,
    SEARCH_SPACES,
    TuningError,
    grid_size,
    parse_tuning,
    tuning_code,
    validate_tuning,
)


def installed(model):
    package = ESTIMATORS[model].get("package")
    if package is None:
        return True
    try:
        importlib.import_module(ESTIMATORS[model]["module"])
        return True
    except ImportError:
        return False


class TestSpaces:
    def test_every_estimator_has_a_search_space(self):
        assert set(SEARCH_SPACES) == set(ESTIMATORS)

    def test_every_space_is_a_non_empty_list_of_values_per_parameter(self):
        for model, space in SEARCH_SPACES.items():
            assert space and all(isinstance(values, list) and values for values in space.values()), model

    @pytest.mark.parametrize("model", sorted(ESTIMATORS))
    def test_every_parameter_value_is_accepted_by_the_estimator(self, model):
        if not installed(model):
            pytest.skip("package not installed")
        module = importlib.import_module(ESTIMATORS[model]["module"])
        cls = getattr(module, ESTIMATORS[model]["cls"])
        for name, values in SEARCH_SPACES[model].items():
            for value in values:
                cls(**{**ESTIMATORS[model]["fixed"], name: value})

    def test_a_listed_value_is_never_the_fixed_argument_of_the_protocol(self):
        for model, space in SEARCH_SPACES.items():
            assert not set(space) & {"random_state", "random_seed", "probability", "eval_metric", "verbose"}, model

    def test_the_grid_size_is_the_product_of_the_value_counts(self):
        assert grid_size("QDA") == 5
        assert grid_size("RandomForest") == 3 * 4 * 3
        assert grid_size("SVM") == 4 * 4 * 2

    def test_a_forest_and_extra_trees_share_their_space(self):
        assert SEARCH_SPACES["RandomForest"] == SEARCH_SPACES["ExtraTrees"]

    def test_the_constants_are_the_documented_ones(self):
        assert (tuning.MIN_ITERATIONS, tuning.MAX_ITERATIONS, DEFAULT_ITERATIONS) == (4, 40, 12)
        assert (tuning.MIN_FOLDS, tuning.MAX_FOLDS, DEFAULT_FOLDS) == (3, 5, 3)
        assert tuning.TUNING_SHARE == 0.2


class TestValidation:
    MODELS = ["RandomForest", "MLP"]

    @pytest.mark.parametrize("raw", [None, False, {}])
    def test_no_tuning_gives_an_empty_setting(self, raw):
        assert validate_tuning(raw, self.MODELS) == {}

    def test_defaults_fill_the_missing_fields(self):
        assert validate_tuning({"iterations": 8}, self.MODELS) == {"iterations": 8, "folds": DEFAULT_FOLDS}
        assert validate_tuning({"folds": 5}, self.MODELS) == {"iterations": DEFAULT_ITERATIONS, "folds": 5}

    def test_the_bounds_are_inclusive(self):
        assert validate_tuning({"iterations": 4, "folds": 3}, self.MODELS) == {"iterations": 4, "folds": 3}
        assert validate_tuning({"iterations": 40, "folds": 5}, self.MODELS) == {"iterations": 40, "folds": 5}

    @pytest.mark.parametrize("raw", [{"iterations": 3}, {"iterations": 41}, {"folds": 2}, {"folds": 6}, {"iterations": 1.5}, {"iterations": "8"}, {"iterations": True}, {"folds": None}])
    def test_values_outside_the_bounds_are_refused(self, raw):
        with pytest.raises(TuningError, match="whole number from"):
            validate_tuning(raw, self.MODELS)

    @pytest.mark.parametrize("raw", ["yes", 5, [1, 2], True])
    def test_a_non_object_is_refused(self, raw):
        with pytest.raises(TuningError, match="must be an object"):
            validate_tuning(raw, self.MODELS)

    def test_unknown_fields_are_refused(self):
        with pytest.raises(TuningError, match="unknown fields: budget, seed"):
            validate_tuning({"iterations": 8, "seed": 1, "budget": 3}, self.MODELS)

    def test_a_model_without_a_space_is_refused(self, monkeypatch):
        monkeypatch.setitem(tuning.SEARCH_SPACES, "Fancy", {"x": [1]})
        monkeypatch.delitem(tuning.SEARCH_SPACES, "MLP")
        with pytest.raises(TuningError, match="no search space: MLP"):
            validate_tuning({"iterations": 8}, self.MODELS)


class TestCode:
    CODE = tuning_code(["RandomForest", "LogisticRegression"], 6, 3, ESTIMATORS)

    def test_it_is_plain_python_without_comments(self):
        ast.parse(self.CODE)
        assert "#" not in self.CODE

    def test_it_is_deterministic(self):
        assert tuning_code(["RandomForest", "LogisticRegression"], 6, 3, ESTIMATORS) == self.CODE

    def test_the_tuning_set_is_a_fixed_stratified_share(self):
        assert "train_test_split(X, y, train_size=0.2, random_state=0, stratify=y)" in self.CODE

    def test_the_folds_and_the_scorer_are_in_the_search(self):
        assert "cv=3" in self.CODE and "scoring='roc_auc'" in self.CODE and "random_state=0" in self.CODE
        assert "cv=5" in tuning_code(["KNN"], 6, 5, ESTIMATORS)

    def test_the_search_is_seeded_and_a_failed_fit_does_not_stop_it(self):
        code = tuning_code(["KNN"], 6, 3, ESTIMATORS)
        assert "random_state=0)" in code and "error_score=float('nan')" in code

    def test_a_small_grid_caps_the_number_of_configurations(self):
        code = tuning_code(["QDA", "RandomForest"], 40, 3, ESTIMATORS)
        sizes = ast.literal_eval(next(line for line in code.splitlines() if line.startswith("sizes = ")).split(" = ", 1)[1])
        assert sizes == {"QDA": 5, "RandomForest": 36}

    def test_only_the_requested_models_are_searched(self):
        spaces = ast.literal_eval(next(line for line in self.CODE.splitlines() if line.startswith("spaces = ")).split(" = ", 1)[1])
        assert set(spaces) == {"RandomForest", "LogisticRegression"}
        assert spaces["RandomForest"] == SEARCH_SPACES["RandomForest"]

    def test_the_classes_are_looked_up_by_name(self):
        assert "classes = {'RandomForest': RandomForestClassifier, 'LogisticRegression': LogisticRegression}" in self.CODE

    def run(self, rows=400, seed=0):
        rng = np.random.default_rng(seed)
        X = pd.DataFrame(rng.normal(size=(rows, 4)), columns=list("abcd"))
        y = (X["a"] + 0.5 * X["b"] + rng.normal(scale=0.5, size=rows) > 0).astype(int).to_numpy()
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression

        namespace = {
            "X": X,
            "y": y,
            "train_test_split": train_test_split,
            "with_preprocessing": lambda estimator: estimator,
            "RandomForestClassifier": RandomForestClassifier,
            "LogisticRegression": LogisticRegression,
        }
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(self.CODE, "t", "exec"), namespace)
        return namespace, out.getvalue()

    def test_running_it_splits_the_data_and_prints_what_the_parser_reads(self):
        namespace, output = self.run()
        parsed = parse_tuning(output)
        assert parsed["rows_tune"] == 80 and parsed["rows_eval"] == 320
        assert len(namespace["y"]) == 320 and len(namespace["X"]) == 320 and len(namespace["y_tune"]) == 80
        assert set(parsed["models"]) == {"RandomForest", "LogisticRegression"}
        for model, record in parsed["models"].items():
            assert 0.5 < record["cv_roc_auc"] <= 1.0
            assert set(record["params"]) == set(SEARCH_SPACES[model]) and all(value in [list(item) if isinstance(item, tuple) else item for item in SEARCH_SPACES[model][name]] for name, value in record["params"].items())

    def test_the_tuned_dictionary_matches_the_printed_parameters(self):
        namespace, output = self.run()
        parsed = parse_tuning(output)
        assert namespace["tuned"]["LogisticRegression"]["C"] == parsed["models"]["LogisticRegression"]["params"]["C"]

    def test_the_search_is_reproducible(self):
        assert self.run()[1] == self.run()[1]

    def test_the_evaluation_part_is_what_the_split_loop_will_see(self):
        namespace, _ = self.run()
        assert namespace["X"].shape == (320, 4) and abs(namespace["y"].mean() - namespace["y_tune"].mean()) < 0.05


class TestParse:
    OUTPUT = (
        "dataset=x samples=6000\n"
        "tuning rows_tune=1200 rows_eval=4800\n"
        'tuned model=RandomForest cv_roc_auc=0.8123 params={"n_estimators": 200, "max_depth": null, "min_samples_leaf": 2}\n'
        'tuned model=MLP cv_roc_auc=0.7001 params={"hidden_layer_sizes": [100, 50], "alpha": 0.001}\n'
        "model=RandomForest accuracy=0.9\n"
    )

    def test_the_split_and_each_model_are_read(self):
        assert parse_tuning(self.OUTPUT) == {
            "rows_tune": 1200,
            "rows_eval": 4800,
            "models": {
                "RandomForest": {"cv_roc_auc": 0.8123, "params": {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 2}},
                "MLP": {"cv_roc_auc": 0.7001, "params": {"hidden_layer_sizes": [100, 50], "alpha": 0.001}},
            },
        }

    def test_output_without_tuning_gives_nothing(self):
        assert parse_tuning("dataset=x samples=6000\nmodel=RandomForest accuracy=0.9") == {}
        assert parse_tuning("") == {}

    def test_a_split_without_models_is_still_a_record(self):
        assert parse_tuning("tuning rows_tune=10 rows_eval=40") == {"rows_tune": 10, "rows_eval": 40, "models": {}}

    def test_models_without_a_split_line_get_zero_rows(self):
        parsed = parse_tuning('tuned model=KNN cv_roc_auc=0.5 params={"n_neighbors": 3}')
        assert parsed["rows_tune"] == 0 and parsed["models"]["KNN"]["params"] == {"n_neighbors": 3}

    def test_a_line_with_broken_json_is_skipped(self):
        parsed = parse_tuning("tuning rows_tune=1 rows_eval=2\ntuned model=KNN cv_roc_auc=0.5 params={bad}\ntuned model=GaussianNB cv_roc_auc=0.6 params={}")
        assert set(parsed["models"]) == {"GaussianNB"}

    def test_a_nan_score_line_is_skipped_not_a_crash(self):
        parsed = parse_tuning('tuning rows_tune=1 rows_eval=2\ntuned model=KNN cv_roc_auc=abc params={"n_neighbors": 3}')
        assert parsed["models"] == {}

    def test_lines_must_start_the_line(self):
        assert parse_tuning('x tuned model=KNN cv_roc_auc=0.5 params={"n_neighbors": 3}') == {}
