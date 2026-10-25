import numpy as np
import pytest

from app.campaign.descriptors import DESCRIPTORS
from app.campaign.moderators import MIN_MODERATOR_DATASETS, effects, family_score, moderator_rows

CLAIM = {"id": "C1", "metrics": ["roc_auc"], "subject": ["A", "B"], "other": ["C"]}
KEYS = [f"d{index}" for index in range(9)]


def summary(a, b, c):
    return {
        "A": {"roc_auc_mean": a, "f1_mean": a},
        "B": {"roc_auc_mean": b, "f1_mean": b},
        "C": {"roc_auc_mean": c, "f1_mean": c},
    }


def world(gaps, values, count=9):
    summaries = {KEYS[index]: summary(0.5 + gaps[index], 0.4, 0.5) for index in range(count)}
    descriptors = {KEYS[index]: {name: values[name][index] if name in values else 0.0 for name in DESCRIPTORS} for index in range(count)}
    return summaries, descriptors, KEYS[:count]


def rows_for(gaps, values, count=9, claims=None):
    summaries, descriptors, datasets = world(gaps, values, count)
    return moderator_rows(claims or [CLAIM], summaries, descriptors, datasets)


def row(rows, descriptor, claim="C1", metric="roc_auc"):
    return next(item for item in rows if item["descriptor"] == descriptor and item["claim"] == claim and item["metric"] == metric)


GAPS = [0.01 * index for index in range(1, 10)]


class TestFamilyScore:
    def test_the_best_member_scores_the_family(self):
        assert family_score(summary(0.7, 0.9, 0.5), ["A", "B"], "roc_auc") == 0.9
        assert family_score(summary(0.7, 0.9, 0.5), ["A"], "roc_auc") == 0.7

    def test_the_metric_picks_the_column(self):
        assert family_score({"A": {"roc_auc_mean": 0.9, "f1_mean": 0.1}}, ["A"], "f1") == 0.1

    def test_effects_are_the_subject_minus_the_other_family(self):
        summaries = {"x": summary(0.8, 0.4, 0.5), "y": summary(0.3, 0.4, 0.5)}
        assert effects(CLAIM, "roc_auc", summaries, ["x", "y"]) == pytest.approx([0.3, -0.1])


class TestRows:
    def test_every_descriptor_gets_a_row_per_claim_and_metric(self):
        claims = [CLAIM, {"id": "C2", "metrics": ["roc_auc", "f1"], "subject": ["C"], "other": ["A"]}]
        rows = rows_for(GAPS, {"features": list(range(9))}, claims=claims)
        assert len(rows) == 3 * len(DESCRIPTORS)
        assert {item["claim"] for item in rows} == {"C1", "C2"} and {item["metric"] for item in rows if item["claim"] == "C2"} == {"roc_auc", "f1"}

    def test_a_perfect_monotone_relation_is_found(self):
        rows = rows_for(GAPS, {"features": list(range(9))})
        found = row(rows, "features")
        assert found["testable"] and found["rho"] == pytest.approx(1.0) and found["datasets"] == 9
        assert found["p_value"] < 0.001 and found["significant"]

    def test_a_reversed_relation_has_a_negative_rho(self):
        found = row(rows_for(GAPS, {"features": list(range(9, 0, -1))}), "features")
        assert found["rho"] == pytest.approx(-1.0) and found["significant"]

    def test_noise_is_not_significant(self):
        rng = np.random.default_rng(3)
        values = {name: list(rng.normal(size=9)) for name in DESCRIPTORS}
        rows = rows_for(list(rng.normal(size=9)), values)
        assert not any(item["significant"] for item in rows)

    def test_a_descriptor_that_never_varies_is_not_testable(self):
        found = row(rows_for(GAPS, {"features": [5.0] * 9}), "features")
        assert not found["testable"] and found["adjusted_p_value"] is None and found["rho"] == 0.0 and found["p_value"] == 1.0

    def test_effects_that_never_vary_are_not_testable(self):
        found = row(rows_for([0.05] * 9, {"features": list(range(9))}), "features")
        assert not found["testable"]

    def test_too_few_datasets_are_not_testable(self):
        found = row(rows_for(GAPS, {"features": list(range(9))}, count=MIN_MODERATOR_DATASETS - 1), "features")
        assert not found["testable"] and found["datasets"] == MIN_MODERATOR_DATASETS - 1

    def test_exactly_the_minimum_is_testable(self):
        found = row(rows_for(GAPS, {"features": list(range(9))}, count=MIN_MODERATOR_DATASETS), "features")
        assert found["testable"] and found["datasets"] == MIN_MODERATOR_DATASETS

    def test_the_minimum_is_six(self):
        assert MIN_MODERATOR_DATASETS == 6

    def test_missing_values_are_left_out_of_the_correlation(self):
        values = {"features": list(range(9))}
        summaries, descriptors, datasets = world(GAPS, values)
        descriptors["d4"]["features"] = float("nan")
        found = row(moderator_rows([CLAIM], summaries, descriptors, datasets), "features")
        assert found["testable"] and found["datasets"] == 8

    def test_so_many_missing_values_make_it_untestable(self):
        summaries, descriptors, datasets = world(GAPS, {"features": list(range(9))})
        for key in datasets[:4]:
            descriptors[key]["features"] = float("nan")
        assert not row(moderator_rows([CLAIM], summaries, descriptors, datasets), "features")["testable"]

    def test_a_dataset_without_descriptors_is_skipped(self):
        summaries, descriptors, datasets = world(GAPS, {"features": list(range(9))})
        del descriptors["d8"]
        found = row(moderator_rows([CLAIM], summaries, descriptors, datasets), "features")
        assert found["datasets"] == 8

    def test_no_datasets_give_untestable_rows(self):
        rows = moderator_rows([CLAIM], {}, {}, [])
        assert len(rows) == len(DESCRIPTORS) and not any(item["testable"] for item in rows)

    def test_the_holm_adjustment_covers_the_descriptors_of_one_claim_and_metric(self):
        values = {name: [0, 1, 2, 3, 4, 5, 6, 8, 7] for name in DESCRIPTORS}
        rows = [item for item in rows_for(GAPS, values) if item["testable"]]
        assert len(rows) == len(DESCRIPTORS)
        raw = sorted(item["p_value"] for item in rows)
        adjusted = sorted(item["adjusted_p_value"] for item in rows)
        assert raw[0] > 0 and adjusted[0] == pytest.approx(min(1.0, raw[0] * len(rows)))
        assert all(item["adjusted_p_value"] >= item["p_value"] for item in rows)

    def test_the_adjustment_is_not_shared_between_metrics(self):
        claim = {"id": "C1", "metrics": ["roc_auc", "f1"], "subject": ["A", "B"], "other": ["C"]}
        values = {"features": list(range(9))}
        rows = rows_for(GAPS, values, claims=[claim])
        first = row(rows, "features", metric="roc_auc")
        second = row(rows, "features", metric="f1")
        assert first["adjusted_p_value"] == pytest.approx(second["adjusted_p_value"])

    def test_significance_needs_the_adjusted_p_below_alpha(self):
        values = {"features": [0, 5, 1, 6, 2, 7, 3, 8, 4]}
        found = row(rows_for(GAPS, values), "features")
        assert found["significant"] == (found["adjusted_p_value"] < 0.05)

    def test_rows_keep_the_descriptor_order(self):
        rows = rows_for(GAPS, {"features": list(range(9))})
        assert [item["descriptor"] for item in rows] == list(DESCRIPTORS)
