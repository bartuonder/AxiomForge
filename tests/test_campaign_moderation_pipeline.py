import mlflow
import pytest

import app.campaign.report as report_module
import app.campaign.tracking as tracking
from app.campaign.analysis import analyze_campaign
from app.campaign.descriptors import DESCRIPTOR_LABELS, DESCRIPTORS
from app.campaign.ledger import build_ledger, find
from app.campaign.meta_evidence import discussion_facts, moderator_sentences
from app.campaign.protocol import build_script
from app.campaign.report import render_report, report_issues
from app.campaign.runner import run_dataset
from app.datasets import benchmark_keys
from app.seeds import SPLIT_SEEDS
from app.variants import expected_keys

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Trees beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc"], "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"], "subject": ["MLP"], "other": ["LogisticRegression"]},
]
SPEC = {"title": "T", "models": MODELS, "params": {}, "claims": CLAIMS, "datasets": benchmark_keys(), "source": {}}
KEYS = benchmark_keys()
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}


def descriptors(index, pattern):
    values = {name: 0.5 for name in DESCRIPTORS}
    if pattern == "rising":
        values["features"] = float(10 + index * 3)
        values["mean_abs_correlation"] = 0.2 + 0.05 * index
    elif pattern == "falling":
        values["features"] = float(100 - index * 7)
    elif pattern == "noise":
        for name in DESCRIPTORS:
            values[name] = float([5, 2, 8, 1, 9, 4, 7, 3, 6][index])
    return values


def outcome(pattern="rising", keys=KEYS, with_descriptors=True):
    data = {"order": list(keys), "datasets": {}, "failed": {}}
    for index, key in enumerate(keys):
        gap = 0.02 * index
        summary = {name: {f"{metric}_mean": value for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}
        summary["RandomForest"] = {f"{metric}_mean": 0.85 + gap for metric in ("roc_auc", "pr_auc", "f1")}
        summary["HistGradientBoosting"] = {f"{metric}_mean": 0.5 for metric in ("roc_auc", "pr_auc", "f1")}
        data["datasets"][key] = {
            "summary": summary,
            "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
            "descriptors": descriptors(index, pattern) if with_descriptors else {},
            "provenance": {},
            "seconds": 1.0,
            "attempts": 1,
            "script": f"script {key}",
        }
    return data


def build(pattern="rising", **kwargs):
    data = outcome(pattern, **kwargs)
    analysis = analyze_campaign(SPEC, data)
    markdown, ledger = render_report(SPEC, data, analysis)
    return data, analysis, ledger, markdown


class TestProtocolAndRunner:
    def test_the_campaign_script_prints_the_descriptors_after_the_provenance(self):
        script = build_script("tb_credit", MODELS)
        assert script.index("provenance revision=") < script.index("descriptors categorical_share=")

    def fake_output(self, with_line=True):
        lines = ["dataset=tb_credit samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
        if with_line:
            lines.append("descriptors categorical_share=0.2000 mean_abs_correlation=0.3000 mean_abs_skew=1.5000 missing_share=0.0100")
        for _ in SPLIT_SEEDS:
            for key in expected_keys(MODELS, {"models": MODELS, "params": {}}):
                value = BASE[key]
                lines.append(f"model={key} accuracy={value:.4f} f1={value - 0.05:.4f} roc_auc={value:.4f} pr_auc={value - 0.02:.4f} train_seconds=0.1 tn=1 fp=1 fn=1 tp=1")
        return "\n".join(lines)

    def test_the_result_carries_the_profile_derived_and_the_sandbox_descriptors(self):
        result = run_dataset("tb_credit", SPEC, lambda script, schema: self.fake_output())
        assert result["descriptors"] == {
            "features": 10.0,
            "minority_ratio": 0.5,
            "categorical_share": 0.2,
            "mean_abs_correlation": 0.3,
            "mean_abs_skew": 1.5,
            "missing_share": 0.01,
        }

    def test_without_the_line_only_the_profile_descriptors_remain(self):
        result = run_dataset("tb_credit", SPEC, lambda script, schema: self.fake_output(with_line=False))
        assert result["status"] == "finished" and result["descriptors"] == {"features": 10.0, "minority_ratio": 0.5}


class TestAnalysis:
    def test_every_claim_metric_and_descriptor_has_a_row(self):
        _, analysis, _, _ = build()
        assert len(analysis["moderators"]) == (2 + 1) * len(DESCRIPTORS)

    def test_a_rising_gap_is_tied_to_the_number_of_features(self):
        _, analysis, _, _ = build()
        row = next(item for item in analysis["moderators"] if item["claim"] == "C1" and item["metric"] == "roc_auc" and item["descriptor"] == "features")
        assert row["testable"] and row["rho"] == pytest.approx(1.0) and row["significant"] and row["datasets"] == 9

    def test_a_falling_relation_is_negative(self):
        _, analysis, _, _ = build("falling")
        row = next(item for item in analysis["moderators"] if item["claim"] == "C1" and item["descriptor"] == "features" and item["metric"] == "roc_auc")
        assert row["rho"] == pytest.approx(-1.0)

    def test_descriptors_that_do_not_vary_are_not_testable(self):
        _, analysis, _, _ = build()
        row = next(item for item in analysis["moderators"] if item["descriptor"] == "missing_share")
        assert not row["testable"]

    def test_without_descriptors_nothing_is_testable(self):
        _, analysis, _, _ = build(with_descriptors=False)
        assert not any(item["testable"] for item in analysis["moderators"])

    def test_an_empty_campaign_has_no_moderators(self):
        analysis = analyze_campaign(SPEC, {"order": ["a"], "datasets": {}, "failed": {"a": {"error": "x", "attempts": 1}}})
        assert "moderators" not in analysis


class TestLedger:
    def test_the_dataset_entries_carry_their_descriptors(self):
        _, _, ledger, _ = build()
        assert find(ledger, "dataset", "tb_credit")["descriptors"]["features"] == 10.0
        assert find(ledger, "dataset", KEYS[-1])["descriptors"]["features"] == 34.0

    def test_every_moderator_row_is_a_ledger_entry_with_a_stable_key(self):
        _, analysis, ledger, _ = build()
        entries = [entry for entry in ledger if entry["kind"] == "moderator"]
        assert len(entries) == len(analysis["moderators"])
        entry = find(ledger, "moderator", "C1:roc_auc:features")
        assert entry["significant"] and entry["rho"] == pytest.approx(1.0) and entry["claim"] == "C1"

    def test_the_ledger_table_describes_a_moderator_entry(self):
        _, _, ledger, markdown = build()
        entry = find(ledger, "moderator", "C1:roc_auc:features")
        assert f"| {entry['id']} | moderator | C1:roc_auc:features | features, rho +1.00, n 9 |" in markdown


class TestReport:
    def section(self, markdown):
        return markdown.split("Exploratory moderator analysis")[1].split("## Limitations")[0]

    def test_a_significant_moderator_is_stated_with_its_numbers_and_reference(self):
        _, _, ledger, markdown = build()
        entry = find(ledger, "moderator", "C1:roc_auc:features")
        expected = (
            "The advantage of RandomForest and HistGradientBoosting (best member of the family on each dataset) over MLP on ROC-AUC grew with "
            f"the number of features (Spearman rho = +1.00, Holm-adjusted p = {entry['adjusted_p_value']:.3g}, 9 datasets) [{entry['id']}]."
        )
        assert expected in self.section(markdown)

    def test_a_falling_relation_says_shrank(self):
        _, _, _, markdown = build("falling")
        assert "shrank with the number of features (Spearman rho = -1.00" in self.section(markdown)

    def test_the_heading_says_the_analysis_is_exploratory(self):
        _, _, _, markdown = build()
        assert "Exploratory moderator analysis (Spearman correlation between the per-dataset advantage of a claim and dataset descriptors, exploratory because the number of datasets is small):" in markdown

    def test_no_significant_moderator_gets_one_plain_sentence(self):
        _, _, _, markdown = build("noise")
        text = self.section(markdown)
        assert "No dataset descriptor was significantly related to the size of the advantage after Holm adjustment." in text and "Spearman rho =" not in text

    def test_nothing_testable_leaves_the_section_out(self):
        _, _, _, markdown = build(with_descriptors=False)
        assert "Exploratory moderator analysis" not in markdown

    def test_the_section_follows_the_pairwise_comparisons_and_precedes_the_limitations(self):
        _, _, _, markdown = build()
        assert markdown.index("Pairwise comparisons") < markdown.index("Exploratory moderator analysis") < markdown.index("## Limitations")

    def test_the_traceability_check_is_clean(self):
        _, _, ledger, markdown = build()
        assert report_issues(markdown, ledger) == []

    def test_the_number_of_sentences_is_bounded(self, monkeypatch):
        monkeypatch.setattr(report_module, "MAX_MODERATOR_SENTENCES", 1)
        _, _, _, markdown = build()
        assert self.section(markdown).count("Spearman rho =") == 1
        assert report_module.MAX_MODERATOR_SENTENCES == 1

    def test_the_default_bound_is_twelve(self):
        assert report_module.MAX_MODERATOR_SENTENCES == 12

    def test_every_descriptor_has_a_label(self):
        assert set(DESCRIPTOR_LABELS) == set(DESCRIPTORS)


class TestMetaEvidence:
    def test_a_significant_moderator_becomes_a_cited_fact(self):
        _, analysis, ledger, _ = build()
        sentences = moderator_sentences(analysis, ledger)
        entry = find(ledger, "moderator", "C1:roc_auc:features")
        assert (
            f"The advantage of the best of RandomForest and HistGradientBoosting over MLP on ROC-AUC grew with the number of features across the datasets [{entry['id']}]."
            in sentences
        )

    def test_a_falling_one_says_shrank(self):
        _, analysis, ledger, _ = build("falling")
        assert any("shrank with the number of features across the datasets" in sentence for sentence in moderator_sentences(analysis, ledger))

    def test_nothing_significant_gives_nothing(self):
        _, analysis, ledger, _ = build("noise")
        assert moderator_sentences(analysis, ledger) == []
        assert moderator_sentences({}, []) == []

    def test_the_facts_for_the_discussion_include_them_last(self):
        _, analysis, ledger, _ = build()
        facts = discussion_facts(analysis, ledger)
        assert facts[-1] == moderator_sentences(analysis, ledger)[-1] and len(facts) > len(moderator_sentences(analysis, ledger))


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mlflow_moderators")
    patch = pytest.MonkeyPatch()
    patch.chdir(folder)
    uri = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"
    patch.setattr(tracking, "MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield uri
    patch.undo()


class TestTracking:
    def test_testable_moderators_are_logged_with_rho_and_the_adjusted_p(self, store):
        data, analysis, ledger, markdown = build()
        run = mlflow.get_run(tracking.log_campaign("mod", SPEC, data, analysis, markdown, ledger, "completed"))
        assert run.data.metrics["moderator/C1/roc_auc/features/rho"] == pytest.approx(1.0)
        assert run.data.metrics["moderator/C1/roc_auc/features/adjusted_p_value"] < 0.05
        assert "moderator/C1/roc_auc/missing_share/rho" not in run.data.metrics

    def test_a_campaign_without_descriptors_logs_no_moderator_metric(self, store):
        data, analysis, ledger, markdown = build(with_descriptors=False)
        run = mlflow.get_run(tracking.log_campaign("nomod", SPEC, data, analysis, markdown, ledger, "completed"))
        assert not any(name.startswith("moderator/") for name in run.data.metrics)
