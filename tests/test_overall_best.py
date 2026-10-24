import re

import mlflow
import pytest

import app.graph.nodes as nodes
import app.tracking.mlflow_logger as logger_module
from app.agents.consistency import SIMILARITY_LIMIT, repetition_issues, summary_completeness_issues
from app.agents.report import SYSTEM_PROMPT
from app.graph.evidence import evidence_sentences, overall_variants, summary_sentences
from app.graph.verifier import leader_summary, leaders_summary, overall_summary

RF, LR, KNN, HGB = "RandomForest", "LogisticRegression", "KNN", "HistGradientBoosting"

SUMMARY = {
    RF: {"roc_auc_mean": 0.8953, "pr_auc_mean": 0.7366, "f1_mean": 0.6482},
    LR: {"roc_auc_mean": 0.9046, "pr_auc_mean": 0.7599, "f1_mean": 0.6581},
    KNN: {"roc_auc_mean": 0.8696, "pr_auc_mean": 0.6587, "f1_mean": 0.6113},
    HGB: {"roc_auc_mean": 0.9121, "pr_auc_mean": 0.7937, "f1_mean": 0.6763},
    "statistical_conclusion": "text",
}


def row(metric, a, b, difference, significant):
    return {"metric": metric, "a": a, "b": b, "mean_difference": difference, "significant": significant}


PERFORMANCE = [
    row("roc_auc", HGB, RF, 0.0168, True),
    row("roc_auc", HGB, LR, 0.0075, False),
    row("roc_auc", HGB, KNN, 0.0425, True),
    row("roc_auc", LR, RF, 0.0093, False),
    row("pr_auc", HGB, RF, 0.0571, True),
    row("pr_auc", HGB, LR, 0.0338, True),
    row("pr_auc", HGB, KNN, 0.1350, True),
    row("f1", HGB, RF, 0.0281, True),
    row("f1", HGB, LR, 0.0182, False),
    row("f1", HGB, KNN, 0.0649, True),
]


class TestLeaders:
    def test_every_metric_gets_its_own_leader_and_unproven_rivals(self):
        leaders = leaders_summary(SUMMARY, PERFORMANCE)
        assert [leader["metric"] for leader in leaders] == ["roc_auc", "pr_auc", "f1"]
        assert [leader["model"] for leader in leaders] == [HGB, HGB, HGB]
        assert leaders[0]["not_significant_against"] == [LR]
        assert leaders[1]["not_significant_against"] == []
        assert leaders[2]["not_significant_against"] == [LR]
        assert leaders[1]["mean"] == pytest.approx(0.7937)

    def test_different_metrics_may_have_different_leaders(self):
        summary = {"A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.5, "f1_mean": 0.5}, "B": {"roc_auc_mean": 0.8, "pr_auc_mean": 0.6, "f1_mean": 0.4}}
        assert [leader["model"] for leader in leaders_summary(summary, [])] == ["A", "B", "A"]

    def test_the_default_metric_of_leader_summary_is_unchanged(self):
        assert leader_summary(SUMMARY, PERFORMANCE)["metric"] == "roc_auc"
        assert leader_summary(SUMMARY, PERFORMANCE, "f1")["metric"] == "f1"

    def test_a_significant_row_that_points_the_other_way_does_not_count_as_a_lead(self):
        summary = {"A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.9, "f1_mean": 0.9}, "B": {"roc_auc_mean": 0.8, "pr_auc_mean": 0.8, "f1_mean": 0.8}}
        wrong = [row("roc_auc", "A", "B", -0.1, True)]
        assert leaders_summary(summary, wrong)[0]["not_significant_against"] == ["B"]
        assert overall_summary(summary, wrong)["not_significant"]["roc_auc"] == ["B"]
        right = [row("roc_auc", "A", "B", 0.1, True)]
        assert leaders_summary(summary, right)[0]["not_significant_against"] == []

    def test_a_single_model_or_missing_means_give_no_leaders(self):
        assert leaders_summary({"A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.5, "f1_mean": 0.5}}, []) == []
        assert leaders_summary({}, []) == []


class TestOverall:
    def test_the_run_thirteen_pattern(self):
        overall = overall_summary(SUMMARY, PERFORMANCE)
        assert overall["model"] == HGB
        assert overall["average_rank"] == pytest.approx(1.0)
        assert overall["models"] == 4
        assert overall["metrics"] == ["roc_auc", "pr_auc", "f1"]
        assert overall["not_significant"] == {"roc_auc": [LR], "pr_auc": [], "f1": [LR]}
        assert overall["leaders"] == {"roc_auc": HGB, "pr_auc": HGB, "f1": HGB}

    def test_the_best_overall_model_need_not_lead_every_metric(self):
        summary = {
            "A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.9, "f1_mean": 0.5},
            "B": {"roc_auc_mean": 0.8, "pr_auc_mean": 0.7, "f1_mean": 0.9},
            "C": {"roc_auc_mean": 0.7, "pr_auc_mean": 0.8, "f1_mean": 0.6},
        }
        rows = [row("roc_auc", "A", "B", 0.1, True), row("roc_auc", "A", "C", 0.2, True)]
        overall = overall_summary(summary, rows)
        assert overall["model"] == "A"
        assert overall["average_rank"] == pytest.approx((1 + 1 + 3) / 3)
        assert overall["leaders"]["f1"] == "B"
        assert overall["not_significant"]["roc_auc"] == []
        assert overall["not_significant"]["f1"] == ["B", "C"]

    def test_a_tie_in_the_average_rank_leaves_no_single_model(self):
        summary = {
            "A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.8, "f1_mean": 0.7},
            "B": {"roc_auc_mean": 0.8, "pr_auc_mean": 0.7, "f1_mean": 0.9},
            "C": {"roc_auc_mean": 0.7, "pr_auc_mean": 0.9, "f1_mean": 0.8},
        }
        overall = overall_summary(summary, [])
        assert overall["model"] is None
        assert overall["leaders"] == {"roc_auc": "A", "pr_auc": "C", "f1": "B"}
        assert overall["models"] == 3

    def test_equal_means_share_the_average_rank(self):
        summary = {
            "A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.9, "f1_mean": 0.9},
            "B": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.9, "f1_mean": 0.9},
        }
        assert overall_summary(summary, [])["model"] is None

    def test_controls_and_text_entries_are_ignored(self):
        summary = {**SUMMARY, "KNN__default": {"roc_auc_mean": 0.99, "pr_auc_mean": 0.99, "f1_mean": 0.99}}
        assert overall_summary(summary, PERFORMANCE)["model"] == HGB
        assert overall_summary(summary, PERFORMANCE)["models"] == 4

    def test_missing_metrics_or_one_model_give_nothing(self):
        assert overall_summary({"A": {"roc_auc_mean": 0.9}, "B": {"roc_auc_mean": 0.8}}, []) is None
        assert overall_summary({"A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.5, "f1_mean": 0.5}}, []) is None
        assert overall_summary({}, []) is None

    def test_models_missing_one_metric_make_the_composite_impossible(self):
        summary = {
            "A": {"roc_auc_mean": 0.9, "pr_auc_mean": 0.5, "f1_mean": 0.5},
            "B": {"roc_auc_mean": 0.8, "pr_auc_mean": 0.6},
        }
        assert overall_summary(summary, []) is None


RUN_THIRTEEN = overall_summary(SUMMARY, PERFORMANCE)
ALL_CLEAR = {
    "model": "A", "average_rank": 1.0, "models": 3, "metrics": ["roc_auc", "pr_auc", "f1"], "leaders": {},
    "not_significant": {"roc_auc": [], "pr_auc": [], "f1": []},
}
NONE_CLEAR = {
    "model": "A", "average_rank": 1.33, "models": 3, "metrics": ["roc_auc", "pr_auc", "f1"], "leaders": {},
    "not_significant": {"roc_auc": ["B"], "pr_auc": ["B", "C"], "f1": ["B"]},
}
UNDECIDED = {"model": None, "leaders": {"roc_auc": "A", "pr_auc": "B", "f1": "C"}, "models": 3}


class TestSentences:
    def test_the_run_thirteen_pattern_reads_naturally(self):
        abstract, conclusion = overall_variants(RUN_THIRTEEN)
        assert abstract == [
            "Overall, HistGradientBoosting was the best-performing model across ROC-AUC, PR-AUC and F1 (average rank 1.00 of 4).",
            "It held a clear lead over every other model on PR-AUC, but no established lead over LogisticRegression on ROC-AUC and F1.",
        ]
        assert conclusion == [
            "Taking ROC-AUC, PR-AUC and F1 together, HistGradientBoosting came out ahead of the field (average rank 1.00 of 4).",
            "Its advantage was clear against every rival on PR-AUC, but not established against LogisticRegression on ROC-AUC and F1.",
        ]

    def test_a_model_that_leads_everywhere_gets_the_plain_wording(self):
        abstract, conclusion = overall_variants(ALL_CLEAR)
        assert abstract[1] == "It held a clear lead over every other model on ROC-AUC, PR-AUC and F1."
        assert conclusion[1] == "Its advantage was clear against every rival on ROC-AUC, PR-AUC and F1."

    def test_a_model_without_a_proven_lead_says_so_per_rival_group(self):
        abstract, conclusion = overall_variants(NONE_CLEAR)
        assert abstract[1] == "It held no established lead over B on ROC-AUC and F1 and no established lead over B and C on PR-AUC."
        assert conclusion[1].startswith("Its advantage was not established against B on ROC-AUC and F1")

    def test_an_undecided_composite_names_each_leader(self):
        abstract, conclusion = overall_variants(UNDECIDED)
        assert abstract == ["No single model led overall: ROC-AUC to A, PR-AUC to B and F1 to C."]
        assert conclusion == [
            "The three metrics did not agree on one best model: A had the highest mean ROC-AUC, "
            "B had the highest mean PR-AUC and C had the highest mean F1."
        ]

    def test_nothing_is_written_without_an_overall_result(self):
        assert overall_variants(None) == ([], [])
        assert overall_variants({}) == ([], [])

    @staticmethod
    def similarity(first, second):
        one, two = set(re.findall(r"[a-z0-9]+", first.lower())), set(re.findall(r"[a-z0-9]+", second.lower()))
        return len(one & two) / len(one | two)

    @pytest.mark.parametrize("overall", [RUN_THIRTEEN, ALL_CLEAR, NONE_CLEAR, UNDECIDED])
    def test_the_two_variants_never_come_close_to_each_other(self, overall):
        abstract, conclusion = overall_variants(overall)
        assert len(abstract) == len(conclusion)
        for first, second in zip(abstract, conclusion):
            assert first != second
            assert self.similarity(first, second) < SIMILARITY_LIMIT - 0.2

    def test_the_results_evidence_lists_every_leader_and_the_overall_sentences(self):
        decision = {"leaders": leaders_summary(SUMMARY, PERFORMANCE), "overall": RUN_THIRTEEN}
        sentences = evidence_sentences(decision)
        assert sum("had the highest mean" in sentence for sentence in sentences) == 3
        assert sentences[2] == (
            "HistGradientBoosting had the highest mean F1 (0.6763), but its lead over LogisticRegression is not statistically significant."
        )
        assert sentences[3].startswith("Overall, HistGradientBoosting was the best-performing model")
        assert len(sentences) == 5

    def test_the_summary_prefers_the_overall_result_over_the_roc_auc_leader(self):
        decision = {"leader": leader_summary(SUMMARY, PERFORMANCE), "overall": RUN_THIRTEEN, "parameter_effects": []}
        summary = summary_sentences(decision)
        assert summary["Abstract"][0].startswith("Overall, HistGradientBoosting")
        assert not any("had the highest mean ROC-AUC" in sentence for sentence in summary["Abstract"])
        assert summary["Conclusion"][0].startswith("Taking ROC-AUC")

    def test_without_an_overall_result_the_roc_auc_leader_is_still_used(self):
        decision = {"leader": leader_summary(SUMMARY, PERFORMANCE), "parameter_effects": []}
        assert summary_sentences(decision)["Abstract"][0].startswith("HistGradientBoosting had the highest mean ROC-AUC")

    def test_a_legacy_decision_without_leaders_keeps_its_old_evidence(self):
        decision = {"leader": leader_summary(SUMMARY, PERFORMANCE)}
        assert sum("had the highest mean" in sentence for sentence in evidence_sentences(decision)) == 1


def paper(abstract="A.", conclusion="C."):
    return f"# Abstract\n{abstract}\n# Conclusion\n{conclusion}\n"


class TestCompleteness:
    def test_the_prepared_sentences_satisfy_both_sections(self):
        abstract, conclusion = overall_variants(RUN_THIRTEEN)
        text = paper(" ".join(abstract), " ".join(conclusion))
        assert summary_completeness_issues(text, None, None, RUN_THIRTEEN) == []
        assert repetition_issues(text) == []

    def test_a_section_without_the_overall_model_is_flagged_and_named(self):
        issues = summary_completeness_issues(paper(), None, None, RUN_THIRTEEN)
        assert len(issues) == 2
        assert all("HistGradientBoosting" in issue and "genel olarak en iyi modeli" in issue for issue in issues)
        assert {"Abstract bölümü" in issues[0], "Conclusion bölümü" in issues[1]} == {True}

    @pytest.mark.parametrize(
        "sentence",
        [
            "HistGradientBoosting was strong.",
            "Overall, the models were comparable.",
            "RandomForest was the best-performing model overall.",
            "HistGradientBoosting was evaluated across three metrics.",
            "The best model was HistGradientBoosting.",
        ],
    )
    def test_the_model_a_scope_word_and_a_best_cue_are_all_needed(self, sentence):
        assert len(summary_completeness_issues(paper(abstract=sentence, conclusion=sentence + " x"), None, None, RUN_THIRTEEN)) == 2

    def test_an_undecided_composite_must_be_reported_as_undecided(self):
        issues = summary_completeness_issues(paper(abstract="A was good."), None, None, UNDECIDED)
        assert len(issues) == 2 and all("tek bir genel en iyi modelde birleşmediğini" in issue for issue in issues)
        abstract, conclusion = overall_variants(UNDECIDED)
        assert summary_completeness_issues(paper(" ".join(abstract), " ".join(conclusion)), None, None, UNDECIDED) == []

    def test_the_overall_rule_replaces_the_roc_auc_leader_rule(self):
        leader = leader_summary(SUMMARY, PERFORMANCE)
        abstract, conclusion = overall_variants(RUN_THIRTEEN)
        text = paper(" ".join(abstract), " ".join(conclusion))
        assert summary_completeness_issues(text, leader, None, RUN_THIRTEEN) == []
        old_rule = summary_completeness_issues(text, leader, None, None)
        assert len(old_rule) == 1 and "Conclusion bölümü" in old_rule[0] and "ROC-AUC'ye sahip" in old_rule[0]

    def test_nothing_is_demanded_when_there_is_nothing_to_report(self):
        assert summary_completeness_issues(paper(), None, None, None) == []


def test_the_whole_pipeline_for_a_copying_writer_ends_without_issues():
    decision = {
        "n_splits": 10,
        "leaders": leaders_summary(SUMMARY, PERFORMANCE),
        "leader": leader_summary(SUMMARY, PERFORMANCE),
        "overall": RUN_THIRTEEN,
        "parameter_effects": [],
        "performance": [],
        "instability": {"unstable": False, "flagged": []},
    }
    sentences = summary_sentences(decision)
    text = (
        "# Abstract\nWe compare four models. " + " ".join(sentences["Abstract"])
        + "\n# Methodology\nThe models were evaluated on 10 repeated stratified train/test splits.\n"
        "# Results\n" + "\n".join(evidence_sentences(decision)) + "\n# Conclusion\nThe picture is clear. "
        + " ".join(sentences["Conclusion"]) + "\n"
    )
    state = {
        "paper_markdown": text,
        "statistical_results": {},
        "statistical_decision": decision,
        "verification_status": "Passed",
        "hypotheses": ["h"],
        "experiment_specs": [{"statement": "h", "dataset": "adult_income", "models": [RF, LR, KNN, HGB], "params": {}}],
    }
    assert nodes._gate_issues(state) == []


def test_the_verifier_stores_the_leaders_and_the_overall_result(monkeypatch):
    output = "\n".join(
        f"model={name} accuracy=0.9 f1={f1 + 0.001 * (index % 3):.4f} roc_auc={roc + 0.001 * (index % 3):.4f} "
        f"pr_auc={pr + 0.001 * (index % 3):.4f} train_seconds=1.0 tn=50 fp=5 fn=5 tp=40"
        for index in range(10)
        for name, roc, pr, f1 in (("A", 0.80, 0.50, 0.50), ("B", 0.90, 0.70, 0.60))
    )
    monkeypatch.setattr(nodes, "save_experiment", lambda **kwargs: "id")
    monkeypatch.setattr(nodes, "run_classification", lambda code, schema: output)
    monkeypatch.setattr(nodes, "judge_data_leakage", lambda code: (False, ""))
    monkeypatch.setattr(nodes, "log_verified_comparison", lambda *args, **kwargs: "run")
    state = {
        "query": "q",
        "hypotheses": ["stmt"],
        "experiment_specs": [{"statement": "stmt", "dataset": "adult_income", "models": ["A", "B"], "params": {}}],
        "current_experiment_code": "x = 1",
        "experiment_metrics": {"accuracy": 0.9, "f1": 0.8},
        "dataset_profile": {"dataset": "d", "samples": 500.0, "features": 20.0, "negative_ratio": 0.9, "positive_ratio": 0.1},
        "critic_rounds": 0,
    }
    decision = nodes.verifier_node(state)["statistical_decision"]
    assert [leader["model"] for leader in decision["leaders"]] == ["B", "B", "B"]
    assert decision["leader"]["metric"] == "roc_auc"
    assert decision["overall"]["model"] == "B"
    assert decision["overall"]["not_significant"] == {"roc_auc": [], "pr_auc": [], "f1": []}


def test_the_overall_best_and_the_leaders_become_mlflow_tags(tmp_path, monkeypatch):
    uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(logger_module, "MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    rows = [
        {"model": name, "split_index": index, "seed": 42 + index, "accuracy": 0.9, "f1": 0.5, "roc_auc": 0.8, "pr_auc": 0.6,
         "train_seconds": 0.1, "tn": 1.0, "fp": 1.0, "fn": 1.0, "tp": 1.0}
        for index in range(2)
        for name in ("A", "B")
    ]
    summary = {"A": {"roc_auc_mean": 0.8}, "B": {"roc_auc_mean": 0.9}}
    decision = {"overall": {"model": "B", "leaders": {"roc_auc": "B", "pr_auc": "A", "f1": "B"}}}
    run_id = logger_module.log_verified_comparison(rows, summary, decision, prompt_version="v", model="m", critic_rounds=0, hypothesis="h")
    tags = mlflow.get_run(run_id).data.tags
    assert tags["overall_best"] == "B"
    assert tags["leader_pr_auc"] == "A"
    assert tags["leader_roc_auc"] == "B"
    run_id = logger_module.log_verified_comparison(rows, summary, {}, prompt_version="v", model="m", critic_rounds=0, hypothesis="h")
    assert mlflow.get_run(run_id).data.tags["overall_best"] == "none"


def test_the_writer_is_told_about_the_composite():
    assert "Genel olarak en iyi modeli (ROC-AUC, PR-AUC ve F1 sıralamalarının bileşkesi" in SYSTEM_PROMPT
