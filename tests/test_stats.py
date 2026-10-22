import numpy as np
import pytest
from scipy import stats

from app.graph.stats import MIN_SPLITS, corrected_resampled_t, holm_adjust, pitman_morgan_p


def test_holm_matches_the_textbook_example():
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == pytest.approx([0.03, 0.06, 0.06])


def test_holm_is_monotone_and_capped_at_one():
    adjusted = holm_adjust([0.5, 0.6, 0.9])
    assert adjusted == pytest.approx([1.0, 1.0, 1.0])
    assert all(value <= 1.0 for value in adjusted)


def test_holm_never_lowers_a_p_value():
    raw = [0.001, 0.2, 0.049, 0.5]
    assert all(after >= before for before, after in zip(raw, holm_adjust(raw)))


def test_holm_keeps_the_input_order():
    assert holm_adjust([0.04, 0.01]) == pytest.approx([0.04, 0.02])


def test_holm_of_nothing_is_nothing():
    assert holm_adjust([]) == []


def test_pitman_morgan_equals_the_correlation_test_it_is_built_on():
    first = [0.90, 0.92, 0.91, 0.93, 0.90, 0.94]
    second = [0.80, 0.95, 0.70, 0.99, 0.60, 0.97]
    expected = stats.pearsonr(np.add(first, second), np.subtract(first, second))[1]
    assert pitman_morgan_p(first, second) == pytest.approx(expected)


def test_pitman_morgan_finds_a_clear_variance_gap():
    steady = [0.90, 0.901, 0.899, 0.9005, 0.8995, 0.9002, 0.8998, 0.9001]
    wild = [0.5, 0.95, 0.6, 0.99, 0.55, 0.97, 0.52, 0.93]
    assert pitman_morgan_p(steady, wild) < 0.05


def test_pitman_morgan_does_not_flag_equal_spread():
    rng = np.random.default_rng(3)
    base = rng.normal(0.9, 0.02, 8)
    other = base + rng.normal(0.0, 0.002, 8)
    assert pitman_morgan_p(list(base), list(other)) > 0.05


def test_pitman_morgan_is_symmetric_in_its_arguments():
    first = [0.90, 0.92, 0.91, 0.93, 0.90, 0.94]
    second = [0.80, 0.95, 0.70, 0.99, 0.60, 0.97]
    assert pitman_morgan_p(first, second) == pytest.approx(pitman_morgan_p(second, first))


def test_pitman_morgan_flat_series_gives_no_evidence():
    assert pitman_morgan_p([0.9] * 5, [0.8] * 5) == 1.0


def test_pitman_morgan_rejects_unpaired_and_short_series():
    with pytest.raises(ValueError, match="same length"):
        pitman_morgan_p([0.1, 0.2, 0.3], [0.1, 0.2])
    with pytest.raises(ValueError, match="at least"):
        pitman_morgan_p([0.1] * (MIN_SPLITS - 1), [0.2] * (MIN_SPLITS - 1))


def test_corrected_t_matches_the_formula():
    first = [0.90, 0.92, 0.91, 0.93, 0.95]
    second = [0.85, 0.90, 0.88, 0.91, 0.89]
    train, test = 400.0, 100.0
    difference = np.subtract(first, second)
    mean, spread = difference.mean(), difference.std(ddof=1)
    statistic = mean / np.sqrt((1 / 5 + test / train) * spread ** 2)
    expected_p = 2 * stats.t.sf(abs(statistic), 4)
    got_mean, effect, p_value = corrected_resampled_t(first, second, train, test)
    assert got_mean == pytest.approx(mean)
    assert effect == pytest.approx(mean / spread)
    assert p_value == pytest.approx(expected_p)


def test_corrected_t_is_more_conservative_than_the_plain_paired_t():
    first = [0.90, 0.92, 0.91, 0.93, 0.95]
    second = [0.85, 0.90, 0.88, 0.91, 0.89]
    plain = stats.ttest_rel(first, second).pvalue
    _, _, corrected = corrected_resampled_t(first, second, 400.0, 100.0)
    assert corrected > plain


def test_corrected_t_flips_the_sign_of_the_difference():
    first = [0.90, 0.92, 0.91, 0.93, 0.95]
    second = [0.85, 0.90, 0.88, 0.91, 0.89]
    forward = corrected_resampled_t(first, second, 400.0, 100.0)
    backward = corrected_resampled_t(second, first, 400.0, 100.0)
    assert forward[0] == pytest.approx(-backward[0])
    assert forward[2] == pytest.approx(backward[2])


def test_corrected_t_with_a_constant_gap_is_significant():
    mean, effect, p_value = corrected_resampled_t([0.9] * 5, [0.8] * 5, 400.0, 100.0)
    assert mean == pytest.approx(0.1)
    assert effect == 0.0
    assert p_value == 0.0


def test_corrected_t_with_identical_series_is_not_significant():
    assert corrected_resampled_t([0.9] * 5, [0.9] * 5, 400.0, 100.0) == (0.0, 0.0, 1.0)


def test_corrected_t_rejects_bad_input():
    with pytest.raises(ValueError, match="same length"):
        corrected_resampled_t([0.1, 0.2, 0.3], [0.1, 0.2], 10.0, 5.0)
    with pytest.raises(ValueError, match="at least"):
        corrected_resampled_t([0.1], [0.2], 10.0, 5.0)
    with pytest.raises(ValueError, match="positive"):
        corrected_resampled_t([0.1, 0.2, 0.3], [0.2, 0.3, 0.5], 0.0, 5.0)
