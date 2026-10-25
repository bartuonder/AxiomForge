import ast
import contextlib
import io

import numpy as np
import pandas as pd
import pytest

from app.campaign.descriptors import DESCRIPTORS, SANDBOX_DESCRIPTORS, dataset_descriptors, descriptors_code, parse_descriptors


def run(frame):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(descriptors_code(), "d", "exec"), {"X": frame})
    return parse_descriptors(out.getvalue())


class TestCode:
    def test_it_is_plain_python_without_comments(self):
        ast.parse(descriptors_code())
        assert "#" not in descriptors_code()

    def test_the_four_sandbox_descriptors_are_printed(self):
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [4.0, 3.0, 2.0, 1.0]})
        assert set(run(frame)) == set(SANDBOX_DESCRIPTORS)

    def test_the_categorical_share_counts_the_non_numeric_columns(self):
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": ["x", "y", "x", "y"], "c": [True, False, True, False], "d": [1, 2, 3, 4]})
        assert run(frame)["categorical_share"] == pytest.approx(0.5)

    def test_perfectly_correlated_columns_have_mean_absolute_correlation_one(self):
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 6.0, 8.0], "c": [4.0, 3.0, 2.0, 1.0]})
        assert run(frame)["mean_abs_correlation"] == pytest.approx(1.0)

    def test_independent_columns_have_a_small_correlation(self):
        rng = np.random.default_rng(0)
        frame = pd.DataFrame(rng.normal(size=(4000, 5)), columns=list("abcde"))
        assert run(frame)["mean_abs_correlation"] < 0.05

    def test_a_single_numeric_column_has_no_correlation(self):
        assert run(pd.DataFrame({"a": [1.0, 2.0, 3.0]}))["mean_abs_correlation"] == 0.0

    def test_constant_columns_do_not_break_the_correlation(self):
        frame = pd.DataFrame({"a": [1.0, 1.0, 1.0, 1.0], "b": [1.0, 2.0, 3.0, 4.0]})
        assert run(frame)["mean_abs_correlation"] == 0.0

    def test_the_skew_is_the_mean_absolute_skewness(self):
        frame = pd.DataFrame({"a": [1.0, 1.0, 1.0, 1.0, 10.0], "b": [1.0, 2.0, 3.0, 4.0, 5.0]})
        expected = (abs(frame["a"].skew()) + abs(frame["b"].skew())) / 2
        assert run(frame)["mean_abs_skew"] == pytest.approx(expected, abs=1e-3)

    def test_a_negative_skew_counts_as_much_as_a_positive_one(self):
        frame = pd.DataFrame({"a": [1.0, 1.0, 1.0, 1.0, 10.0], "b": [10.0, 10.0, 10.0, 10.0, 1.0]})
        assert run(frame)["mean_abs_skew"] == pytest.approx(abs(frame["a"].skew()), abs=1e-3) and run(frame)["mean_abs_skew"] > 1.0

    def test_the_missing_share_is_the_share_of_empty_cells(self):
        frame = pd.DataFrame({"a": [1.0, np.nan, 3.0, 4.0], "b": [1.0, 2.0, 3.0, np.nan]})
        assert run(frame)["missing_share"] == pytest.approx(0.25)

    def test_missing_values_are_filled_before_the_correlation(self):
        frame = pd.DataFrame({"a": [1.0, 2.0, np.nan, 4.0, 5.0], "b": [2.0, 4.0, 6.0, 8.0, 10.0]})
        assert 0.9 < run(frame)["mean_abs_correlation"] <= 1.0

    def test_a_frame_without_numeric_columns_is_handled(self):
        result = run(pd.DataFrame({"a": ["x", "y"], "b": ["p", "q"]}))
        assert result["categorical_share"] == 1.0 and result["mean_abs_skew"] == 0.0 and result["mean_abs_correlation"] == 0.0


class TestParse:
    def test_values_are_read_by_name(self):
        line = "descriptors categorical_share=0.2500 mean_abs_correlation=0.3100 mean_abs_skew=1.2000 missing_share=0.0000"
        assert parse_descriptors(line) == {"categorical_share": 0.25, "mean_abs_correlation": 0.31, "mean_abs_skew": 1.2, "missing_share": 0.0}

    def test_the_line_may_sit_between_other_output(self):
        output = "dataset=x samples=1\ndescriptors categorical_share=0.5 mean_abs_correlation=0.1 mean_abs_skew=2 missing_share=0\nmodel=A"
        assert parse_descriptors(output)["categorical_share"] == 0.5 and parse_descriptors(output)["mean_abs_skew"] == 2.0

    def test_a_missing_line_gives_nothing(self):
        assert parse_descriptors("dataset=x samples=1") == {} and parse_descriptors("") == {}

    def test_the_line_must_start_the_line(self):
        assert parse_descriptors("x descriptors categorical_share=0.5") == {}

    def test_unknown_names_are_dropped_and_scientific_notation_is_read(self):
        assert parse_descriptors("descriptors missing_share=1e-05 colour=0.5") == {"missing_share": 1e-05}

    def test_a_negative_value_is_read(self):
        assert parse_descriptors("descriptors mean_abs_skew=-0.5") == {"mean_abs_skew": -0.5}


class TestLabels:
    def test_every_descriptor_is_described_in_words(self):
        from app.campaign.descriptors import DESCRIPTOR_LABELS

        assert DESCRIPTOR_LABELS == {
            "features": "the number of features",
            "minority_ratio": "the share of the minority class",
            "categorical_share": "the share of categorical features",
            "mean_abs_correlation": "the mean absolute correlation between features",
            "mean_abs_skew": "the mean absolute skewness of the features",
            "missing_share": "the share of missing values",
        }


class TestMerge:
    PROFILE = {"dataset": "d", "samples": 100.0, "features": 12.0, "negative_ratio": 0.9, "positive_ratio": 0.1}

    def test_the_profile_adds_the_feature_count_and_the_minority_ratio(self):
        merged = dataset_descriptors(self.PROFILE, {"missing_share": 0.0})
        assert merged == {"features": 12.0, "minority_ratio": pytest.approx(0.1), "missing_share": 0.0}

    def test_the_minority_is_the_smaller_class_in_both_directions(self):
        assert dataset_descriptors({**self.PROFILE, "positive_ratio": 0.8}, {})["minority_ratio"] == pytest.approx(0.2)
        assert dataset_descriptors({**self.PROFILE, "positive_ratio": 0.5}, {})["minority_ratio"] == 0.5

    def test_the_list_of_descriptors_is_the_union(self):
        assert set(DESCRIPTORS) == {"features", "minority_ratio", *SANDBOX_DESCRIPTORS}
