import re

import pytest

import app.campaign.report as report_module
from app.campaign.analysis import analyze_campaign
from app.campaign.report import MAX_PAIR_SENTENCES, VERDICT_LABELS, render_report, report_issues
from app.seeds import SPLIT_SEEDS

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Tree-based models beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc"],
     "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"],
     "subject": ["MLP"], "other": ["LogisticRegression"]},
]
SOURCE = {
    "title": "Why do tree-based models still outperform deep learning on tabular data?",
    "citation": "Grinsztajn et al., NeurIPS 2022",
    "url": "https://arxiv.org/abs/2207.08815",
    "deviations": ["no hyperparameter search", "6000 rows sampled"],
}
SPEC = {"title": "Trees against neural networks", "models": MODELS, "params": {"MLP": {"alpha": 0.01}}, "claims": CLAIMS, "source": SOURCE}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h", "tb_pol", "tb_eye"]
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}


def summary(shift):
    record = {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}
    record["MLP__default"] = {f"{metric}_mean": 0.84 + shift for metric in ("roc_auc", "pr_auc", "f1")}
    return record


def outcome(keys=KEYS, failed=None):
    return {
        "order": list(keys) + list(failed or {}),
        "datasets": {
            key: {
                "summary": summary(0.001 * index),
                "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
                "seconds": 12.5,
                "attempts": 1,
                "script": f"script of {key}",
            }
            for index, key in enumerate(keys)
        },
        "failed": failed or {},
    }


def build(spec=SPEC, **kwargs):
    data = outcome(**kwargs)
    return render_report(spec, data, analyze_campaign(spec, data))


def test_a_full_campaign_gives_a_report_without_any_traceability_issue():
    markdown, ledger = build()
    assert report_issues(markdown, ledger) == []


def test_the_sections_come_in_the_expected_order():
    markdown, _ = build()
    headings = [line for line in markdown.splitlines() if line.startswith("#")]
    assert headings == ["# Trees against neural networks", "## Summary", "## Protocol", "## Results", "## Limitations", "## Evidence ledger"]


def test_the_report_is_deterministic():
    assert build() == build()


def test_the_summary_states_each_claim_with_its_verdict_and_numbers():
    markdown, ledger = build()
    summary_text = markdown.split("## Protocol")[0]
    assert "9 of 9 datasets finished" in summary_text
    assert "**C1** Tree-based models beat the MLP: **REPLICATED**." in summary_text
    assert "On ROC-AUC, RandomForest and HistGradientBoosting (best member of the family on each dataset) scored higher than MLP on 9 of 9 datasets (lower on 0, tied on 0)" in summary_text
    assert "median difference +0.0700" in summary_text
    assert "Holm-adjusted p = 0.0078" in summary_text
    assert "rank-biserial r = +1.00" in summary_text
    assert "**C2** The MLP beats logistic regression: **REPLICATED**." in summary_text
    claim = next(entry for entry in ledger if entry["kind"] == "claim" and entry["key"] == "C1:roc_auc")
    assert f"[{claim['id']}]" in summary_text


def test_every_cited_id_exists_and_matches_the_cited_kind():
    markdown, ledger = build()
    by_id = {entry["id"]: entry for entry in ledger}
    for line in markdown.split("## Evidence ledger")[0].splitlines():
        if line.startswith("**C1**") or line.startswith("On ROC-AUC, RandomForest and"):
            ids = re.findall(r"\[(E\d+)\]", line)
            assert ids == [] or by_id[ids[-1]]["kind"] in {"claim", "dataset"}
    assert {entry["kind"] for entry in ledger} >= {"dataset", "claim", "friedman", "pairwise", "effect"}


def test_the_protocol_names_the_source_the_configuration_the_seeds_and_the_deviations():
    protocol = build()[0].split("## Protocol")[1].split("## Results")[0]
    assert "Grinsztajn et al., NeurIPS 2022" in protocol and "https://arxiv.org/abs/2207.08815" in protocol
    assert "MLP (alpha=0.01) ran with the listed parameters; RandomForest, HistGradientBoosting and LogisticRegression ran with library default parameters." in protocol
    assert ", ".join(str(seed) for seed in SPLIT_SEEDS) in protocol
    assert "- no hyperparameter search" in protocol and "- 6000 rows sampled" in protocol
    assert "Wilcoxon signed-rank" in protocol and "Friedman" in protocol
    assert "- tb_credit: inria-soda/tabular-benchmark (clf_num_credit), 6000 rows, 10 features" in protocol


def test_the_control_is_mentioned_only_when_a_model_is_configured():
    configured = build()[0].split("## Protocol")[1].split("## Results")[0]
    assert "A configured model also runs once with library defaults as its control." in configured
    plain = build({**SPEC, "params": {}})[0].split("## Protocol")[1].split("## Results")[0]
    assert "Every other argument is fixed by the protocol." in plain
    assert "control" not in plain


def test_a_campaign_without_a_source_has_no_source_or_deviation_lines():
    spec = {**SPEC, "source": {}}
    markdown, ledger = build(spec)
    assert "Source:" not in markdown and "Deviations from the source" not in markdown
    assert report_issues(markdown, ledger) == []


def test_the_results_hold_a_table_per_metric_with_the_best_model_in_bold():
    results = build()[0].split("## Results")[1].split("## Limitations")[0]
    assert results.count("Mean ROC-AUC per dataset") == 1 and results.count("Mean PR-AUC per dataset") == 1 and results.count("Mean F1 per dataset") == 1
    first_row = next(line for line in results.splitlines() if line.startswith("| tb_credit"))
    assert "**0.9200**" in first_row and "0.9000" in first_row
    assert first_row.count("**") == 2


def test_the_friedman_rows_list_the_mean_ranks_best_first():
    results = build()[0].split("## Results")[1]
    line = next(item for item in results.splitlines() if item.startswith("ROC-AUC mean ranks"))
    assert "HistGradientBoosting 1.00, RandomForest 2.00, MLP 3.00, LogisticRegression 4.00" in line
    assert "Friedman chi-square = 27.00" in line


def test_significant_pairs_and_parameter_effects_are_written_as_sentences():
    results = build()[0].split("## Results")[1]
    assert "Pairwise comparisons that were significant after Holm adjustment:" in results
    assert "HistGradientBoosting scored higher than RandomForest on ROC-AUC on 9 of 9 datasets" in results
    assert "MLP with the listed parameters scored higher than MLP with default parameters on ROC-AUC on 9 of 9 datasets (median difference 0.0100" in results


def test_the_number_of_pair_sentences_is_bounded(monkeypatch):
    monkeypatch.setattr(report_module, "MAX_PAIR_SENTENCES", 2)
    results = build()[0].split("## Results")[1].split("## Limitations")[0]
    assert len([line for line in results.splitlines() if " scored higher than " in line and "with the listed" not in line]) == 2
    assert MAX_PAIR_SENTENCES == 20


def test_a_non_significant_effect_is_reported_as_such():
    data = outcome()
    for record in data["datasets"].values():
        record["summary"]["MLP__default"] = dict(record["summary"]["MLP"])
    markdown, ledger = render_report(SPEC, data, analyze_campaign(SPEC, data))
    assert "No significant effect of the listed parameters of MLP on ROC-AUC across datasets was found" in markdown
    assert report_issues(markdown, ledger) == []


def test_a_failed_dataset_is_named_in_the_summary_the_limitations_and_the_ledger():
    markdown, ledger = build(failed={"tb_eye": {"error": "OutOfMemory", "attempts": 2}}, keys=KEYS[:8])
    assert "8 of 9 datasets finished" in markdown.split("## Protocol")[0]
    assert "; failed: tb_eye [" in markdown
    assert "Datasets that failed were left out of every test: tb_eye." in markdown
    assert "| failure | tb_eye | 2 attempts: OutOfMemory |" in markdown
    assert report_issues(markdown, ledger) == []


def test_too_few_datasets_say_that_nothing_can_be_called_replicated():
    markdown, ledger = build(keys=KEYS[:4])
    summary_text = markdown.split("## Protocol")[0]
    assert "**NOT TESTABLE**" in summary_text
    assert "so this metric could not be tested" in summary_text
    assert "cannot reach p < 0.05 with fewer than 6 datasets" in summary_text
    assert report_issues(markdown, ledger) == []


def test_a_campaign_where_nothing_finished_still_produces_an_honest_report():
    failed = {"tb_credit": {"error": "boom", "attempts": 2}, "tb_pol": {"error": "boom", "attempts": 2}}
    data = {"order": list(failed), "datasets": {}, "failed": failed}
    markdown, ledger = render_report(SPEC, data, analyze_campaign(SPEC, data))
    assert "0 of 2 datasets finished" in markdown
    assert "No claim could be assessed: no dataset finished, so nothing can be compared." in markdown
    assert "## Results" not in markdown
    assert report_issues(markdown, ledger) == []


def test_the_labels_cover_every_verdict_the_statistics_can_return():
    assert set(VERDICT_LABELS) == {"replicated", "partially_replicated", "contradicted", "inconclusive", "not_testable"}


def test_a_contradicted_claim_is_labelled_so():
    spec = {**SPEC, "claims": [{**CLAIMS[0], "subject": ["MLP"], "other": ["RandomForest", "HistGradientBoosting"], "metrics": ["roc_auc"]}]}
    markdown, _ = build(spec)
    assert "**CONTRADICTED (the opposite held)**" in markdown


class TestTraceabilityCheck:
    def test_an_unknown_reference_is_reported(self):
        markdown, ledger = build()
        issues = report_issues(markdown + "\nSee [E999].\n", ledger)
        assert "E999 is cited but not in the ledger" in issues

    def test_a_numeric_sentence_without_a_reference_is_reported(self):
        markdown, ledger = build()
        broken = markdown.replace("## Protocol", "RandomForest won 9 of 9 datasets.\n\n## Protocol", 1)
        issues = report_issues(broken, ledger)
        assert any("a numeric line in Summary has no evidence reference: RandomForest won 9 of 9" in issue for issue in issues)

    def test_a_numeric_table_row_without_a_reference_is_reported(self):
        markdown, ledger = build()
        broken = markdown.replace("| tb_credit [E1] |", "| tb_credit |", 1)
        assert any("a numeric line in Results" in issue and "tb_credit" in issue for issue in report_issues(broken, ledger))

    def test_a_ledger_entry_that_is_never_cited_is_reported(self):
        markdown, ledger = build()
        broken = markdown.replace("[E1]", "", 1)
        stripped = re.sub(r"\[E1\](?!\d)", "", markdown.split("## Evidence ledger")[0]) + "## Evidence ledger" + markdown.split("## Evidence ledger")[1]
        assert any("E1 (dataset tb_credit) is never cited" in issue for issue in report_issues(stripped, ledger))
        assert broken != markdown

    def test_protocol_and_limitations_may_contain_numbers_without_references(self):
        markdown, ledger = build()
        assert re.search(r"\d", markdown.split("## Protocol")[1].split("## Results")[0])
        assert report_issues(markdown, ledger) == []

    def test_the_claim_id_is_not_a_number_that_needs_a_reference(self):
        assert report_issues("## Summary\n\n**C1** statement without figures: **REPLICATED**.\n", []) == []


def test_a_harmful_configuration_is_reported_as_lower_than_the_default():
    data = outcome()
    for record in data["datasets"].values():
        record["summary"]["MLP__default"] = {key: value + 0.02 for key, value in record["summary"]["MLP"].items()}
    markdown, ledger = render_report(SPEC, data, analyze_campaign(SPEC, data))
    assert "MLP with the listed parameters scored lower than MLP with default parameters on ROC-AUC on 9 of 9 datasets (median difference 0.0200" in markdown
    assert report_issues(markdown, ledger) == []
