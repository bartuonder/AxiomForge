import pytest

import app.graph.nodes as nodes
from app.agents.consistency import (
    collective_claim_issues,
    direction_conflict,
    method_issues,
    performance_issues,
    repetition_issues,
    summary_completeness_issues,
    unsupported_difference_issues,
)
from app.agents.report import SYSTEM_PROMPT
from app.graph.evidence import evidence_sentences, leader_sentences
from app.graph.verifier import leader_summary

LEADER = {
    "model": "HistGradientBoosting",
    "metric": "roc_auc",
    "mean": 0.9121,
    "not_significant_against": ["LogisticRegression"],
}


def effect(model, metric, significant):
    return {
        "model": model,
        "params": {"x": 1},
        "metric": metric,
        "mean_difference": 0.02,
        "effect_size_dz": 3.0,
        "p_value": 0.001,
        "adjusted_p_value": 0.001,
        "significant": significant,
    }


EFFECTS = [
    effect("KNN", "roc_auc", True),
    effect("KNN", "pr_auc", True),
    effect("KNN", "f1", False),
    effect("HistGradientBoosting", "roc_auc", False),
]

REAL_METHODOLOGY = (
    "The dataset used for this study is the adult_income dataset from Hugging Face. "
    "The models were evaluated using a 10-fold cross-validation approach. "
    "The parameters tuned were: KNN with 10 neighbors."
)
GOOD_METHODOLOGY = (
    "The dataset used for this study is the adult_income dataset from Hugging Face. "
    "The models were evaluated on 10 repeated stratified train/test splits."
)
REAL_ABSTRACT = (
    "This study evaluates four models on the adult income prediction task. "
    "The hypothesis that KNN with 10 neighbors would outperform Hist Gradient Boosting in PR-AUC was contradicted. "
    "The results showed no significant difference in ROC-AUC stability across models. "
    "The hypothesis was contradicted."
)


def paper(abstract="A.", methodology=GOOD_METHODOLOGY, conclusion="C."):
    return f"# Abstract\n{abstract}\n# Introduction\nI.\n# Methodology\n{methodology}\n# Results\nR.\n# Conclusion\n{conclusion}\n"


class TestMethod:
    def test_the_real_cross_validation_claim_is_flagged(self):
        issues = method_issues(paper(methodology=REAL_METHODOLOGY), 10)
        assert any("10-fold cross-validation approach" in issue for issue in issues)
        assert any("10 repeated stratified train/test splits" in issue for issue in issues)

    def test_a_correct_description_passes(self):
        assert method_issues(paper(), 10) == []

    @pytest.mark.parametrize(
        "sentence",
        [
            "The models were scored with 5-fold cross validation.",
            "We used k-fold evaluation.",
            "Stratified K Fold was applied.",
            "Results were bootstrapped 1000 times.",
            "Bootstrap resampling gave the intervals.",
            "A leave-one-out scheme was used.",
            "Cross-validated scores are reported.",
            "The CV scores were averaged.",
            "Nested CV picked the parameters.",
        ],
    )
    def test_every_other_evaluation_scheme_is_flagged(self, sentence):
        issues = method_issues(paper(methodology=GOOD_METHODOLOGY + " " + sentence), 10)
        assert len(issues) == 1
        assert sentence[:25] in issues[0]

    @pytest.mark.parametrize(
        "sentence",
        [
            "This is not cross-validation.",
            "Prior work used 10-fold cross-validation.",
            "Smith et al. relied on bootstrap intervals.",
            "The literature favours k-fold schemes.",
            "The cv column holds an identifier.",
        ],
    )
    def test_negated_cited_and_unrelated_mentions_pass(self, sentence):
        assert method_issues(paper(methodology=GOOD_METHODOLOGY + " " + sentence), 10) == []

    @pytest.mark.parametrize(
        "sentence",
        [
            "Each model ran on 10 stratified train/test splits.",
            "Ten random train-test splits were used.",
            "The models were evaluated on repeated stratified splits.",
            "We trained on 10 stratified splits of the data.",
            "The models were run on repeated random splits.",
        ],
    )
    def test_the_repeated_split_wording_is_accepted(self, sentence):
        assert method_issues(paper(methodology=sentence), 10) == []

    def test_a_methodology_without_the_splits_is_flagged(self):
        issues = method_issues(paper(methodology="The dataset has 6000 rows."), 10)
        assert issues == [issues[0]]
        assert "repeated stratified" in issues[0]

    def test_a_paper_without_a_methodology_is_flagged(self):
        assert len(method_issues("# Abstract\nA.\n# Results\nR.\n", 10)) == 1

    def test_without_splits_nothing_is_demanded(self):
        assert method_issues(paper(methodology="The dataset has 6000 rows. 10-fold cross-validation."), 0) == []

    def test_a_table_row_is_not_prose(self):
        table = "| Model | note |\n| --- | --- |\n| KNN | 10-fold cross-validation |\n"
        assert method_issues(paper() + table, 10) == []

    def test_at_most_three_sentences_are_reported_besides_the_missing_description(self):
        text = " ".join(f"Scheme {n} used {n}-fold validation." for n in range(2, 8))
        assert len(method_issues(paper(methodology=text), 10)) == 4


GOOD_ABSTRACT = (
    "HistGradientBoosting had the highest mean ROC-AUC (0.9121). "
    "KNN with 10 neighbors reached a higher ROC-AUC and PR-AUC than KNN with default parameters."
)
GOOD_CONCLUSION = (
    "The best mean ROC-AUC belonged to HistGradientBoosting at 0.9121. "
    "Changing the KNN parameters from their defaults improved its ROC-AUC and PR-AUC."
)


class TestCompleteness:
    def test_the_real_run_eight_summary_misses_the_leader_and_the_effect_in_both_sections(self):
        issues = summary_completeness_issues(paper(abstract=REAL_ABSTRACT, conclusion=REAL_ABSTRACT), LEADER, EFFECTS)
        assert len(issues) == 4
        assert sum("HistGradientBoosting" in issue for issue in issues) == 2
        assert sum("KNN" in issue for issue in issues) == 2
        assert any("Abstract bölümü" in issue for issue in issues)
        assert any("Conclusion bölümü" in issue for issue in issues)

    def test_a_complete_summary_passes(self):
        assert summary_completeness_issues(paper(abstract=GOOD_ABSTRACT, conclusion=GOOD_CONCLUSION), LEADER, EFFECTS) == []

    def test_one_section_alone_is_not_enough(self):
        issues = summary_completeness_issues(paper(abstract=GOOD_ABSTRACT, conclusion="Nothing."), LEADER, EFFECTS)
        assert len(issues) == 2
        assert all("Conclusion bölümü" in issue for issue in issues)

    def test_the_leader_needs_a_best_cue_and_the_metric(self):
        for sentence in (
            "HistGradientBoosting was evaluated on ROC-AUC.",
            "HistGradientBoosting had the highest mean PR-AUC.",
            "LogisticRegression had the highest mean ROC-AUC.",
        ):
            issues = summary_completeness_issues(paper(abstract=sentence, conclusion=GOOD_CONCLUSION), LEADER, None)
            assert len(issues) == 1 and "Abstract bölümü" in issues[0]

    def test_the_leader_clause_is_what_counts_not_the_whole_sentence(self):
        sentence = "HistGradientBoosting was strong, and LogisticRegression had the highest mean ROC-AUC."
        assert len(summary_completeness_issues(paper(abstract=sentence, conclusion=GOOD_CONCLUSION), LEADER, None)) == 1

    def test_an_effect_sentence_needs_the_model_a_parameter_word_and_the_metric(self):
        for sentence in (
            "KNN improved.",
            "KNN with new parameters improved its F1.",
            "Tuning helped ROC-AUC.",
            "No significant effect of the parameters on ROC-AUC was found for KNN.",
        ):
            issues = summary_completeness_issues(paper(abstract=sentence, conclusion=GOOD_CONCLUSION), None, EFFECTS)
            assert len(issues) == 1, sentence

    def test_only_significant_effects_are_demanded(self):
        quiet = [effect("KNN", "roc_auc", False)]
        assert summary_completeness_issues(paper(), None, quiet) == []

    def test_without_a_leader_and_effects_nothing_is_demanded(self):
        assert summary_completeness_issues(paper(), None, None) == []
        assert summary_completeness_issues(paper(), None, []) == []

    def test_a_missing_section_counts_as_missing(self):
        issues = summary_completeness_issues("# Results\nR.\n", LEADER, None)
        assert len(issues) == 2


class TestRepetition:
    def test_the_real_abstract_states_the_verdict_twice(self):
        issues = repetition_issues(paper(abstract=REAL_ABSTRACT))
        assert len(issues) == 1
        assert "The hypothesis was contradicted" in issues[0]

    def test_the_verdict_may_appear_once_in_each_section(self):
        text = paper(
            abstract="We compared four models. The hypothesis was supported.",
            conclusion="Overall the evidence is mixed. The hypothesis was supported.",
        )
        assert repetition_issues(text) == []

    def test_the_same_long_verdict_sentence_in_both_sections_is_allowed(self):
        verdict = "The hypothesis that KNN beats HistGradientBoosting on PR-AUC was contradicted."
        assert repetition_issues(paper(abstract=verdict, conclusion=verdict)) == []

    def test_an_identical_sentence_in_both_sections_is_flagged(self):
        sentence = "HistGradientBoosting reached the highest mean ROC-AUC across all splits."
        issues = repetition_issues(paper(abstract=sentence, conclusion=sentence))
        assert len(issues) == 1

    def test_a_near_copy_is_flagged(self):
        first = "HistGradientBoosting reached the highest mean ROC-AUC of 0.9121 across all ten splits."
        second = "HistGradientBoosting reached the highest mean ROC-AUC of 0.9121 across all ten splits here."
        assert len(repetition_issues(paper(abstract=first, conclusion=second))) == 1

    def test_a_real_paraphrase_passes(self):
        first = "HistGradientBoosting had the highest mean ROC-AUC (0.9121)."
        second = "Averaged over the splits, the strongest discrimination came from HistGradientBoosting."
        assert repetition_issues(paper(abstract=first, conclusion=second)) == []

    def test_a_sentence_repeated_inside_one_section_is_flagged(self):
        sentence = "The tuned KNN improved its ROC-AUC over the default configuration."
        assert len(repetition_issues(paper(abstract=sentence + " " + sentence))) == 1

    def test_short_sentences_are_ignored(self):
        assert repetition_issues(paper(abstract="Results vary. Results vary.", conclusion="Results vary.")) == []

    def test_at_most_three_are_reported(self):
        many = " ".join(f"Sentence number {n} is repeated here. Sentence number {n} is repeated here." for n in range(6))
        assert len(repetition_issues(paper(abstract=many))) == 3

    def test_missing_sections_are_skipped(self):
        assert repetition_issues("# Results\nSame sentence repeated twice here. Same sentence repeated twice here.\n") == []


PERFORMANCE = [
    {"metric": "roc_auc", "a": "HistGradientBoosting", "b": "LogisticRegression", "mean_difference": 0.0075, "significant": False},
    {"metric": "roc_auc", "a": "HistGradientBoosting", "b": "RandomForest", "mean_difference": 0.0168, "significant": True},
    {"metric": "roc_auc", "a": "HistGradientBoosting", "b": "KNN", "mean_difference": 0.0425, "significant": True},
]


def summary(**means):
    return {name: {"roc_auc_mean": value} for name, value in means.items()}


class TestLeaderSummary:
    def test_the_leader_is_the_best_mean_and_lists_the_rivals_it_does_not_beat_significantly(self):
        result = leader_summary(
            summary(RandomForest=0.8953, LogisticRegression=0.9046, KNN=0.8696, HistGradientBoosting=0.9121),
            PERFORMANCE,
        )
        assert result == {
            "model": "HistGradientBoosting",
            "metric": "roc_auc",
            "mean": 0.9121,
            "not_significant_against": ["LogisticRegression"],
        }

    def test_a_clear_leader_has_nothing_behind_it(self):
        rows = [{**row, "significant": True} for row in PERFORMANCE]
        result = leader_summary(summary(RandomForest=0.8, LogisticRegression=0.9, KNN=0.7, HistGradientBoosting=0.95), rows)
        assert result["not_significant_against"] == []

    def test_a_significant_row_that_points_the_other_way_does_not_count(self):
        rows = [{"metric": "roc_auc", "a": "A", "b": "B", "mean_difference": -0.1, "significant": True}]
        assert leader_summary(summary(A=0.9, B=0.8), rows)["not_significant_against"] == ["B"]

    def test_the_rows_may_list_the_pair_in_either_order(self):
        rows = [{"metric": "roc_auc", "a": "B", "b": "A", "mean_difference": -0.1, "significant": True}]
        assert leader_summary(summary(A=0.9, B=0.8), rows)["not_significant_against"] == []

    def test_controls_and_text_entries_are_ignored(self):
        data = {**summary(A=0.9, B=0.8, A__default=0.99), "statistical_conclusion": "text"}
        assert leader_summary(data, [])["model"] == "A"

    def test_one_model_has_no_leader(self):
        assert leader_summary(summary(A=0.9), []) is None
        assert leader_summary({}, []) is None

    def test_missing_performance_rows_leave_every_rival_unproven(self):
        assert leader_summary(summary(A=0.9, B=0.8, C=0.7), None)["not_significant_against"] == ["B", "C"]


class TestLeaderSentences:
    def test_a_leader_with_unproven_rivals_says_so(self):
        assert leader_sentences(LEADER) == [
            "HistGradientBoosting had the highest mean ROC-AUC (0.9121), but its lead over LogisticRegression "
            "is not statistically significant."
        ]

    def test_several_rivals_are_joined(self):
        leader = {**LEADER, "not_significant_against": ["A", "B", "C"]}
        assert "over A, B and C is not" in leader_sentences(leader)[0]
        assert "over A and B is not" in leader_sentences({**LEADER, "not_significant_against": ["A", "B"]})[0]

    def test_a_clear_leader_gets_a_plain_sentence(self):
        assert leader_sentences({**LEADER, "not_significant_against": []}) == [
            "HistGradientBoosting had the highest mean ROC-AUC (0.9121)."
        ]

    def test_nothing_is_written_without_a_leader(self):
        assert leader_sentences(None) == []
        assert leader_sentences({**LEADER, "metric": "accuracy"}) == []

    def test_the_sentence_comes_right_after_the_hypothesis(self):
        decision = {
            "hypothesis": {"claim": {"subject": "A", "other": "B", "kind": "performance", "metric": "roc_auc"}, "verdict": "untested"},
            "leader": LEADER,
        }
        sentences = evidence_sentences(decision)
        assert sentences[0].startswith("The hypothesis")
        assert sentences[1].startswith("HistGradientBoosting had the highest")

    def test_the_leader_sentence_triggers_no_other_check(self):
        rows = [
            {"metric": "roc_auc", "a": "HistGradientBoosting", "b": "LogisticRegression", "mean_difference": 0.0075, "effect_size_dz": 0.5, "adjusted_p_value": 0.08, "significant": False},
            {"metric": "roc_auc", "a": "HistGradientBoosting", "b": "KNN", "mean_difference": 0.04, "effect_size_dz": 8.0, "adjusted_p_value": 0.001, "significant": True},
            {"metric": "roc_auc", "a": "LogisticRegression", "b": "KNN", "mean_difference": 0.03, "effect_size_dz": 6.0, "adjusted_p_value": 0.001, "significant": True},
        ]
        text = leader_sentences(LEADER)[0] + "\n"
        assert collective_claim_issues(text, rows) == []
        assert unsupported_difference_issues(text, rows) == []
        assert direction_conflict(text, {"outcome": "tie", "performance": rows}) == ""
        assert len(performance_issues(text, rows)) == 2

    def test_the_leader_sentence_in_abstract_and_conclusion_survives_the_completeness_check(self):
        sentence = leader_sentences(LEADER)[0]
        issues = summary_completeness_issues(paper(abstract=sentence, conclusion=sentence), LEADER, None)
        assert issues == []


STATE = {
    "paper_markdown": "",
    "statistical_results": {},
    "verification_status": "Passed",
    "hypotheses": ["stmt"],
    "experiment_specs": [
        {"statement": "stmt", "dataset": "adult_income", "models": ["KNN", "HistGradientBoosting"], "params": {}}
    ],
}


class TestGate:
    def test_the_gate_sends_back_the_real_run_eight_paper_sections(self):
        decision = {"n_splits": 10, "leader": LEADER, "parameter_effects": EFFECTS}
        text = paper(abstract=REAL_ABSTRACT, methodology=REAL_METHODOLOGY, conclusion=REAL_ABSTRACT)
        issues = nodes._gate_issues({**STATE, "statistical_decision": decision, "paper_markdown": text})
        joined = " ".join(issues)
        assert "tekrarlı eğitim/test bölmesidir" in joined
        assert "en iyi ortalama ROC-AUC'ye sahip modeli" in joined
        assert "anlamlı bulunan parametre etkisini" in joined
        assert "aynı cümleyi tekrar etmemeli" in joined

    def test_the_gate_accepts_a_paper_that_meets_all_three(self):
        decision = {"n_splits": 10, "leader": LEADER, "parameter_effects": EFFECTS}
        text = paper(abstract=GOOD_ABSTRACT, conclusion=GOOD_CONCLUSION)
        issues = nodes._gate_issues({**STATE, "statistical_decision": decision, "paper_markdown": text})
        joined = " ".join(issues)
        assert "tekrarlı eğitim/test bölmesidir" not in joined
        assert "Methodology yöntemi" not in joined
        assert "en iyi ortalama ROC-AUC'ye sahip modeli" not in joined
        assert "anlamlı bulunan parametre etkisini" not in joined
        assert "aynı cümleyi tekrar etmemeli" not in joined


def test_the_verifier_stores_the_leader(monkeypatch):
    lines = (
        "model=A accuracy=0.9 f1=0.8 roc_auc={a} pr_auc=0.8 train_seconds=1.0 tn=50 fp=5 fn=5 tp=40\n"
        "model=B accuracy=0.9 f1=0.8 roc_auc={b} pr_auc=0.8 train_seconds=1.0 tn=50 fp=5 fn=5 tp=40"
    )
    output = "\n".join(lines.format(a=0.80 + 0.01 * (index % 3), b=0.90 + 0.01 * (index % 4)) for index in range(10))
    output = "\n".join(
        part
        for index in range(10)
        for part in (
            f"model=A accuracy=0.9 f1=0.8 roc_auc={0.80 + 0.01 * (index % 3):.4f} pr_auc=0.8 train_seconds=1.0 tn=50 fp=5 fn=5 tp=40",
            f"model=B accuracy=0.9 f1=0.8 roc_auc={0.90 + 0.01 * (index % 4):.4f} pr_auc=0.8 train_seconds=1.0 tn=50 fp=5 fn=5 tp=40",
        )
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
    leader = nodes.verifier_node(state)["statistical_decision"]["leader"]
    assert leader["model"] == "B"
    assert leader["metric"] == "roc_auc"
    assert leader["not_significant_against"] == []


def test_the_writer_is_told_the_three_rules():
    assert "10 repeated stratified train/test splits" in SYSTEM_PROMPT
    assert "k-fold, cross-validation, CV, bootstrap ve leave-one-out sözcüklerini hiçbir yerde kullanma" in SYSTEM_PROMPT
    assert "had the highest mean ROC-AUC" in SYSTEM_PROMPT
    assert "Abstract ve Conclusion aynı cümleyi tekrar etmesin" in SYSTEM_PROMPT
