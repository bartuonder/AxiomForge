import pytest

from app.graph.verifier import (
    VERIFICATION_SEEDS,
    conclusion_sentence,
    has_split_loop,
    instability_finding,
    instability_text,
    metric_summary,
    models_dropped,
    performance_comparisons,
    performance_dropped,
    rewrite_seeds,
    seeded_rows,
    stability_decision,
    summarize_seed_runs,
)

ROC = {
    "A": [0.95, 0.60, 0.97, 0.70, 0.99],
    "B": [0.90, 0.91, 0.89, 0.92, 0.90],
}


def row(model, roc_auc, f1=0.8, **extra):
    base = {
        "model": model,
        "accuracy": 0.9,
        "f1": f1,
        "roc_auc": roc_auc,
        "pr_auc": 0.8,
        "train_seconds": 1.0,
        "tn": 50.0,
        "fp": 5.0,
        "fn": 5.0,
        "tp": 40.0,
    }
    base.update(extra)
    return base


def per_seed_runs(series):
    names = list(series)
    return [[row(name, series[name][index]) for name in names] for index in range(5)]


def loop_run(series):
    return [[row(name, value) for name, values in series.items() for value in values]]


def test_summary_uses_sample_std_and_variance_is_its_square():
    summary = summarize_seed_runs(per_seed_runs(ROC))
    record = summary["B"]
    values = ROC["B"]
    mean = sum(values) / 5
    std = (sum((value - mean) ** 2 for value in values) / 4) ** 0.5
    assert record["roc_auc_mean"] == pytest.approx(mean)
    assert record["roc_auc_std"] == pytest.approx(std)
    assert record["roc_auc_variance"] == pytest.approx(std ** 2)


def test_summary_covers_every_metric_for_every_model():
    summary = summarize_seed_runs(per_seed_runs(ROC))
    for model in ("A", "B"):
        for metric in ("accuracy", "f1", "roc_auc", "pr_auc", "train_seconds"):
            for suffix in ("mean", "std", "variance"):
                assert f"{metric}_{suffix}" in summary[model]


def test_a_single_split_has_zero_spread():
    summary = summarize_seed_runs([[row("A", 0.9)]])
    assert summary["A"]["roc_auc_std"] == 0.0


def test_summary_carries_the_conclusion_sentence():
    summary = summarize_seed_runs(per_seed_runs(ROC))
    assert summary["statistical_conclusion"].startswith("B is statistically significantly more stable")


def test_loop_and_per_seed_runs_give_the_same_summary():
    assert summarize_seed_runs(loop_run(ROC)) == summarize_seed_runs(per_seed_runs(ROC))


def test_clear_variance_gap_makes_the_steady_model_the_winner():
    decision = stability_decision(per_seed_runs(ROC))
    assert decision["outcome"] == "winner"
    assert decision["winner"] == "B"
    assert decision["n_splits"] == 5
    assert decision["comparisons"][0]["adjusted_p_value"] < 0.05


def test_equal_spread_is_a_tie():
    series = {"A": [0.90, 0.92, 0.91, 0.93, 0.90], "B": [0.91, 0.93, 0.92, 0.94, 0.91]}
    decision = stability_decision(per_seed_runs(series))
    assert decision["outcome"] == "tie"
    assert decision["winner"] == ""


def test_one_model_gives_no_decision():
    decision = stability_decision(per_seed_runs({"A": ROC["A"]}))
    assert decision["outcome"] == "none"


def test_too_few_splits_give_no_decision():
    runs = per_seed_runs(ROC)[:2]
    assert stability_decision(runs)["outcome"] == "none"


def test_uneven_series_give_no_decision():
    runs = per_seed_runs(ROC) + [[row("A", 0.9)]]
    assert stability_decision(runs)["outcome"] == "none"


def three_model_runs(series):
    return [[row(name, series[name][index]) for name in series] for index in range(6)]


def test_the_steadiest_of_three_wins_when_it_beats_both_rivals():
    series = {
        "A": [0.900, 0.901, 0.899, 0.9005, 0.8995, 0.9002],
        "B": [0.5, 0.95, 0.6, 0.99, 0.55, 0.97],
        "C": [0.89, 0.92, 0.88, 0.93, 0.87, 0.94],
    }
    decision = stability_decision(three_model_runs(series))
    assert decision["outcome"] == "winner"
    assert decision["winner"] == "A"
    assert len(decision["comparisons"]) == 3


def test_no_winner_when_a_rival_is_not_significantly_worse():
    series = {
        "A": [0.900, 0.901, 0.899, 0.9005, 0.8995, 0.9002],
        "B": [0.5, 0.95, 0.6, 0.99, 0.55, 0.97],
        "C": [0.901, 0.9012, 0.8988, 0.9008, 0.8992, 0.9004],
    }
    decision = stability_decision(three_model_runs(series))
    assert decision["outcome"] == "tie"
    assert decision["winner"] == ""


def test_conclusion_sentences():
    assert conclusion_sentence({"outcome": "none"}) == ""
    tie = conclusion_sentence(
        {"outcome": "tie", "alpha": 0.05, "n_splits": 5, "min_adjusted_p": 0.2}
    )
    assert "No statistically significant difference" in tie
    assert "does not establish equivalence" in tie
    winner = conclusion_sentence(
        {"outcome": "winner", "winner": "B", "alpha": 0.05, "n_splits": 5, "min_adjusted_p": 0.01}
    )
    assert winner.startswith("B is statistically significantly more stable")


def test_instability_flags_only_roc_auc_and_f1_above_the_threshold():
    summary = summarize_seed_runs(per_seed_runs(ROC))
    finding = instability_finding(summary)
    assert finding["unstable"] is True
    assert finding["std_threshold"] == 0.05
    assert [(item["model"], item["metric"]) for item in finding["flagged"]] == [("A", "roc_auc")]


def test_instability_is_quiet_for_steady_models():
    steady = {"A": ROC["B"], "B": [0.91, 0.92, 0.90, 0.93, 0.91]}
    finding = instability_finding(summarize_seed_runs(per_seed_runs(steady)))
    assert finding == {"unstable": False, "std_threshold": 0.05, "flagged": []}


def test_train_time_spread_never_counts_as_instability():
    runs = [[row("A", 0.9, train_seconds=float(index * 50))] for index in range(5)]
    assert instability_finding(summarize_seed_runs(runs))["unstable"] is False


def test_instability_text():
    assert instability_text({"unstable": False}) == ""
    text = instability_text(
        {"unstable": True, "std_threshold": 0.05, "flagged": [{"model": "A", "metric": "roc_auc", "std": 0.1794}]}
    )
    assert "0.05" in text
    assert "A roc_auc std=0.1794" in text


def test_metric_summary_lists_each_model_with_mean_and_std():
    text = metric_summary(summarize_seed_runs(per_seed_runs(ROC)))
    assert text.startswith("A accuracy=0.9000")
    assert "; B " in text
    assert "statistical_conclusion" not in text


def test_seeds_follow_the_split_order_in_a_script_loop():
    rows = seeded_rows(loop_run(ROC))
    seeds_of_a = [item["seed"] for item in rows if item["model"] == "A"]
    assert seeds_of_a == list(VERIFICATION_SEEDS)
    assert [item["split_index"] for item in rows if item["model"] == "B"] == [0, 1, 2, 3, 4]


def test_seeds_follow_the_run_order_when_the_verifier_reruns():
    rows = seeded_rows(per_seed_runs(ROC))
    assert [item["seed"] for item in rows if item["model"] == "B"] == list(VERIFICATION_SEEDS)


def test_rows_beyond_the_known_seeds_have_no_seed():
    runs = [[row("A", 0.9)] for _ in range(7)]
    rows = seeded_rows(runs)
    assert [item["seed"] for item in rows][5:] == [None, None]


def test_has_split_loop_needs_five_rows_for_every_model():
    assert has_split_loop(loop_run(ROC)[0]) is True
    assert has_split_loop([row("A", 0.9)] * 4) is False
    assert has_split_loop([row("A", 0.9)] * 5 + [row("B", 0.9)] * 4) is False
    assert has_split_loop([]) is False


SPLIT_CODE = """
from sklearn.model_selection import train_test_split
a = train_test_split(X, y, test_size=0.2, random_state=1)
b = sklearn.model_selection.train_test_split(X, y, random_state=2)
c = train_test_split(X, y, random_state=seed)
d = other_function(random_state=3)
model = RandomForestClassifier(random_state=7)
"""


def test_only_literal_split_seeds_are_rewritten():
    rewritten = rewrite_seeds(SPLIT_CODE, 300)
    assert rewritten.count("random_state=300") == 2
    assert "random_state=seed" in rewritten
    assert "other_function(random_state=3)" in rewritten
    assert "RandomForestClassifier(random_state=7)" in rewritten


def test_performance_comparisons_cover_each_metric_and_pair():
    comparisons = performance_comparisons(per_seed_runs(ROC), 500.0)
    assert {item["metric"] for item in comparisons} == {"roc_auc", "pr_auc", "f1"}
    assert len(comparisons) == 3
    assert all("effect_size_dz" in item and "significant" in item for item in comparisons)


def test_a_large_consistent_gap_is_significant():
    series = {"A": [0.95, 0.96, 0.94, 0.95, 0.96], "B": [0.70, 0.72, 0.69, 0.71, 0.70]}
    comparisons = performance_comparisons(per_seed_runs(series), 500.0)
    roc = next(item for item in comparisons if item["metric"] == "roc_auc")
    assert roc["mean_difference"] > 0.2
    assert roc["significant"] is True


def test_identical_models_have_no_significant_performance_difference():
    comparisons = performance_comparisons(per_seed_runs({"A": ROC["B"], "B": ROC["B"]}), 500.0)
    assert all(item["significant"] is False for item in comparisons)


def test_performance_comparisons_need_confusion_counts_and_sizes():
    without_counts = [[{k: v for k, v in row("A", 0.9).items() if k != "tn"}] for _ in range(5)]
    assert performance_comparisons(without_counts, 500.0) == []
    assert performance_comparisons(per_seed_runs(ROC), 100.0) == []
    assert performance_comparisons([], 500.0) == []


def test_performance_dropped_uses_a_relative_limit():
    assert performance_dropped({"f1": 0.9}, {"f1": 0.7}) is True
    assert performance_dropped({"f1": 0.9}, {"f1": 0.85}) is False
    assert performance_dropped({"f1": 0.0}, {"f1": 0.0}) is False
    assert performance_dropped({"f1": 0.9}, {}) is False


def test_models_dropped_notices_a_missing_model_or_a_collapse():
    original = [row("A", 0.9), row("B", 0.9)]
    assert models_dropped(original, [row("A", 0.9)]) is True
    assert models_dropped(original, [row("A", 0.9), row("B", 0.5)]) is True
    assert models_dropped(original, [row("A", 0.9), row("B", 0.89)]) is False
    assert models_dropped([], []) is False
