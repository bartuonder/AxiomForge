import re

import pytest

import app.campaign.meta_evidence as meta
from app.campaign.analysis import analyze_campaign
from app.campaign.ledger import build_ledger
from app.campaign.report import report_issues

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Tree-based models beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"],
     "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"],
     "subject": ["MLP"], "other": ["LogisticRegression"]},
]
SPEC = {"title": "T", "models": MODELS, "params": {}, "claims": CLAIMS, "source": {}}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h", "tb_pol", "tb_eye"]
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}


def summary(shift, overrides=None):
    record = {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}
    for (model, metric), value in (overrides or {}).items():
        record[model][f"{metric}_mean"] = value
    return record


def outcome(keys=KEYS, overrides=None):
    return {
        "order": list(keys),
        "datasets": {
            key: {
                "summary": summary(0.001 * index, (overrides or {}).get(key)),
                "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
                "seconds": 10.0,
                "attempts": 1,
                "script": f"script of {key}",
            }
            for index, key in enumerate(keys)
        },
        "failed": {},
    }


def build(overrides=None, spec=SPEC, keys=KEYS):
    data = outcome(keys, overrides)
    analysis = analyze_campaign(spec, data)
    return analysis, build_ledger(spec, data, analysis)


class TestLeaders:
    ANALYSIS = {"friedman": {"roc_auc": {"mean_ranks": {"A": 2.0, "B": 1.0}}, "f1": {"mean_ranks": {"A": 1.0, "B": 2.0}}, "pr_auc": {"mean_ranks": {"A": 1.0, "B": 2.0}}}}

    def test_each_metric_has_its_best_ranked_model(self):
        assert meta.metric_leaders(self.ANALYSIS) == {"roc_auc": "B", "f1": "A", "pr_auc": "A"}

    def test_the_overall_leader_has_the_best_average_rank(self):
        assert meta.overall_leader(self.ANALYSIS) == "A"
        assert meta.average_ranks(self.ANALYSIS) == {"A": pytest.approx(4 / 3), "B": pytest.approx(5 / 3)}

    def test_ties_go_to_the_first_name_alphabetically(self):
        analysis = {"friedman": {"roc_auc": {"mean_ranks": {"B": 1.5, "A": 1.5}}}}
        assert meta.metric_leaders(analysis) == {"roc_auc": "A"} and meta.overall_leader(analysis) == "A"

    def test_a_metric_without_ranks_is_skipped_in_the_average(self):
        analysis = {"friedman": {"f1": {"mean_ranks": {}}, "roc_auc": {"mean_ranks": {"A": 1.0, "B": 2.0}}}}
        assert meta.average_ranks(analysis) == {"A": 1.0, "B": 2.0}
        assert meta.overall_leader(analysis) == "A"

    def test_nothing_to_rank_gives_nothing(self):
        assert meta.metric_leaders({}) == {} and meta.overall_leader({}) is None and meta.average_ranks({}) == {}
        assert meta.metric_leaders({"friedman": {"f1": {"mean_ranks": {}}}}) == {}
        assert meta.average_ranks({"friedman": {"f1": {"mean_ranks": {}}}}) == {}


class TestVerdicts:
    def test_a_fully_replicated_claim_names_every_metric_once(self):
        analysis, ledger = build()
        sentences = meta.verdict_sentences(analysis, ledger)
        refs = " ".join(f"[{entry['id']}]" for entry in ledger if entry["kind"] == "claim" and entry["claim"] == "C1")
        assert sentences[0] == f"**C1** (Tree-based models beat the MLP) was **Replicated** on ROC-AUC, PR-AUC and F1 {refs}."

    def test_a_single_metric_claim_reads_naturally(self):
        analysis, ledger = build()
        claim = next(entry for entry in ledger if entry["kind"] == "claim" and entry["key"] == "C2:f1")
        assert meta.verdict_sentences(analysis, ledger)[1] == f"**C2** (The MLP beats logistic regression) was **Replicated** on F1 [{claim['id']}]."

    def test_a_mixed_claim_lists_the_verdict_of_each_group_of_metrics(self):
        analysis, ledger = build()
        analysis["claims"][0]["rows"][2]["verdict"] = "inconclusive"
        analysis["claims"][0]["verdict"] = "partially_replicated"
        sentence = meta.verdict_sentences(analysis, ledger)[0]
        assert "was **Partially replicated**: Replicated on ROC-AUC and PR-AUC; Inconclusive on F1 [" in sentence

    @pytest.mark.parametrize(
        ("verdict", "title"),
        [
            ("replicated", "Replicated"),
            ("partially_replicated", "Partially replicated"),
            ("contradicted", "Contradicted"),
            ("inconclusive", "Inconclusive"),
            ("not_testable", "Not testable"),
        ],
    )
    def test_every_verdict_has_its_title(self, verdict, title):
        analysis, ledger = build()
        for row in analysis["claims"][1]["rows"]:
            row["verdict"] = verdict
        analysis["claims"][1]["verdict"] = verdict
        assert f"was **{title}** on F1" in meta.verdict_sentences(analysis, ledger)[1]

    def test_the_titles_use_the_requested_words(self):
        assert meta.VERDICT_TITLES["replicated"] == "Replicated" and meta.VERDICT_TITLES["contradicted"] == "Contradicted"
        assert set(meta.VERDICT_TITLES) == {"replicated", "partially_replicated", "contradicted", "inconclusive", "not_testable"}

    def test_no_claims_give_no_sentences(self):
        assert meta.verdict_sentences({}, []) == []


class TestExceptions:
    def test_a_claim_that_held_everywhere_says_so_with_the_dataset_count(self):
        analysis, ledger = build()
        sentence = meta.exception_sentences(analysis, ledger)[0]
        claim = next(entry for entry in ledger if entry["kind"] == "claim" and entry["key"] == "C1:roc_auc")
        assert sentence == f"On ROC-AUC, the best of RandomForest and HistGradientBoosting scored higher than MLP on every dataset tested (9 of 9) [{claim['id']}]."

    def test_a_dataset_where_the_other_family_won_is_named_with_both_scores_and_its_reference(self):
        analysis, ledger = build({"tb_eye": {("MLP", "roc_auc"): 0.95}})
        sentence = meta.exception_sentences(analysis, ledger)[0]
        entry = next(item for item in ledger if item["kind"] == "dataset" and item["key"] == "tb_eye")
        expected_forest = max(0.90 + 0.008, 0.92 + 0.008)
        claim = next(item for item in ledger if item["kind"] == "claim" and item["key"] == "C1:roc_auc")
        assert sentence.endswith(f"[{claim['id']}].")
        assert "did not score higher than MLP on 1 of 9 datasets: tb_eye (MLP 0.9500 against the best of RandomForest and HistGradientBoosting " in sentence
        assert f"{expected_forest:.4f}) [{entry['id']}]" in sentence

    def test_a_tie_is_reported_as_a_tie(self):
        analysis, ledger = build({"tb_pol": {("MLP", "roc_auc"): 0.92 + 0.007}})
        sentence = meta.exception_sentences(analysis, ledger)[0]
        entry = next(item for item in ledger if item["kind"] == "dataset" and item["key"] == "tb_pol")
        assert f"on 1 of 9 datasets: tb_pol (tied at 0.9270) [{entry['id']}]" in sentence

    def test_several_exceptions_are_listed_in_dataset_order(self):
        analysis, ledger = build({"tb_pol": {("MLP", "roc_auc"): 0.99}, "tb_eye": {("MLP", "roc_auc"): 0.99}})
        sentence = meta.exception_sentences(analysis, ledger)[0]
        assert "on 2 of 9 datasets: tb_pol" in sentence and sentence.index("tb_pol") < sentence.index("tb_eye")

    def test_one_sentence_per_claim_and_metric(self):
        analysis, ledger = build()
        assert len(meta.exception_sentences(analysis, ledger)) == 4

    def test_a_single_model_family_reads_without_the_best_of(self):
        analysis, ledger = build()
        assert any(sentence.startswith("On F1, MLP scored higher than LogisticRegression on every dataset tested") for sentence in meta.exception_sentences(analysis, ledger))

    def test_only_the_metric_of_the_failure_changes(self):
        analysis, ledger = build({"tb_eye": {("MLP", "pr_auc"): 0.99}})
        sentences = meta.exception_sentences(analysis, ledger)
        assert "every dataset tested (9 of 9)" in sentences[0] and "1 of 9 datasets: tb_eye" in sentences[1] and "every dataset tested (9 of 9)" in sentences[2]


class TestMargins:
    def test_the_largest_advantage_names_the_dataset_and_the_gap(self):
        analysis, ledger = build({"tb_eye": {("HistGradientBoosting", "roc_auc"): 0.99, ("RandomForest", "roc_auc"): 0.5}})
        sentence = meta.margin_sentences(analysis, ledger)[0]
        entry = next(item for item in ledger if item["kind"] == "dataset" and item["key"] == "tb_eye")
        assert sentence == f"The largest advantage of the best of RandomForest and HistGradientBoosting over MLP on ROC-AUC was on tb_eye (+{0.99 - (0.85 + 0.008):.4f}) [{entry['id']}]."

    def test_equal_gaps_go_to_the_last_dataset_name(self):
        equal = {key: {("HistGradientBoosting", "roc_auc"): 0.9, ("RandomForest", "roc_auc"): 0.5, ("MLP", "roc_auc"): 0.8} for key in KEYS}
        analysis, ledger = build(equal)
        assert "was on tb_pol (+0.1000)" in meta.margin_sentences(analysis, ledger)[0]

    def test_a_gap_of_exactly_zero_is_no_advantage(self):
        tied = {key: {("HistGradientBoosting", "roc_auc"): 0.8, ("RandomForest", "roc_auc"): 0.7, ("MLP", "roc_auc"): 0.8} for key in KEYS}
        analysis, ledger = build(tied)
        sentences = meta.margin_sentences(analysis, ledger)
        assert not any("on ROC-AUC" in sentence and "over MLP" in sentence for sentence in sentences)

    def test_a_metric_without_any_advantage_has_no_sentence(self):
        losing = {key: {("MLP", "roc_auc"): 0.99} for key in KEYS}
        analysis, ledger = build(losing)
        sentences = meta.margin_sentences(analysis, ledger)
        assert not any("on ROC-AUC" in sentence and "over MLP" in sentence for sentence in sentences)
        assert len(sentences) == 3


class TestLeader:
    def test_the_average_ranks_and_the_first_model_are_stated_with_every_friedman_reference(self):
        analysis, ledger = build()
        sentence = meta.leader_sentence(analysis, ledger)[0]
        refs = " ".join(f"[{entry['id']}]" for entry in ledger if entry["kind"] == "friedman")
        assert sentence == f"Averaged over the metrics, the mean ranks (1 = best) were HistGradientBoosting 1.00, RandomForest 2.00, MLP 3.00, LogisticRegression 4.00; HistGradientBoosting ranked first overall {refs}."

    def test_without_a_friedman_result_there_is_no_sentence(self):
        assert meta.leader_sentence({}, []) == []


class TestFacts:
    def test_the_facts_are_ordered_verdicts_leader_exceptions_margins(self):
        analysis, ledger = build()
        facts = meta.discussion_facts(analysis, ledger)
        assert len(facts) == 2 + 1 + 4 + 4
        assert facts[0].startswith("**C1**") and facts[1].startswith("**C2**") and facts[2].startswith("Averaged over the metrics")
        assert facts[3].startswith("On ROC-AUC") and facts[7].startswith("The largest advantage")

    def test_an_analysis_with_an_error_has_no_facts(self):
        assert meta.discussion_facts({"coverage": {}, "error": "no dataset finished"}, []) == []

    def test_every_numeric_fact_cites_the_ledger(self):
        analysis, ledger = build({"tb_eye": {("MLP", "roc_auc"): 0.95}})
        for fact in meta.discussion_facts(analysis, ledger):
            digits = re.sub(r"\bF1\b", "", re.sub(r"^\*\*[A-Za-z][\w-]*\*\*", "", fact))
            assert not re.search(r"\d", digits) or re.search(r"\[E\d+\]", fact), fact

    def test_the_facts_pass_the_report_traceability_check_when_placed_in_a_summary(self):
        analysis, ledger = build({"tb_eye": {("MLP", "roc_auc"): 0.95}})
        facts = meta.discussion_facts(analysis, ledger)
        markdown = "## Summary\n\n" + "\n\n".join(facts) + "\n\n## Evidence ledger\n"
        issues = [issue for issue in report_issues(markdown, ledger) if "numeric line" in issue or "cited but not" in issue]
        assert issues == []
