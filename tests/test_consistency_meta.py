import pytest

import app.agents.consistency_meta as gate
from app.agents.consistency_meta import meta_issues
from app.agents.meta_report import compose
from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Tree-based models beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"],
     "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"],
     "subject": ["MLP"], "other": ["LogisticRegression"]},
]
TITLE = "Why do tree-based models still outperform deep learning on tabular data?"
SOURCE = {"title": TITLE, "citation": "Grinsztajn et al., 2022", "url": "https://arxiv.org/abs/2207.08815", "deviations": ["no search", "6000 rows"]}
SPEC = {"title": "Trees against networks", "models": MODELS, "params": {}, "claims": CLAIMS, "source": SOURCE}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h", "tb_pol", "tb_eye"]
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}
SOURCES = [{"title": TITLE, "abstract": "Trees remain state of the art.", "url": "https://arxiv.org/abs/2207.08815"}]
INTRO = f'Tabular data is common in practice. The paper "{TITLE}" asks whether trees still win. We test its claims on many datasets.'
DISCUSSION = (
    "The trees held up on most datasets. The weakest showing of the network may reflect small sample sizes, and we speculate "
    "that noisy features could matter on tb_eye. The pattern is specific to the datasets tested."
)
PROSE = {"introduction": INTRO, "discussion": DISCUSSION}


def outcome(keys=KEYS, failed=None, overrides=None):
    def summary(shift, extra):
        record = {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}
        for (model, metric), value in (extra or {}).items():
            record[model][f"{metric}_mean"] = value
        return record

    return {
        "order": list(keys) + list(failed or {}),
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
        "failed": failed or {},
    }


def paper(prose=None, spec=SPEC, **kwargs):
    data = outcome(**kwargs)
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    return compose(spec, analysis, ledger, markdown, prose or PROSE), analysis, ledger


def issues(prose=None, spec=SPEC, sources=SOURCES, mutate=None, **kwargs):
    text, analysis, ledger = paper(prose, spec, **kwargs)
    spec = {**spec, "datasets": analysis["coverage"]["requested"]}
    if mutate:
        text = mutate(text)
    return meta_issues(text, spec, analysis, ledger, sources)


def test_a_clean_paper_has_no_issue():
    assert issues() == []


def test_a_clean_paper_with_failed_datasets_and_an_exception_has_no_issue():
    other = {**PROSE, "discussion": DISCUSSION.replace("tb_eye", "tb_pol")}
    assert issues(other, failed={"tb_extra": {"error": "OutOfMemory", "attempts": 2}}, keys=KEYS[:8]) == []
    assert issues(overrides={"tb_eye": {("MLP", "roc_auc"): 0.95}}) == []


class TestTraceability:
    def test_an_unknown_reference_in_the_prose_is_reported(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " See [E999]."})
        assert "E999 is cited but not in the ledger" in found

    def test_a_numeric_line_in_the_abstract_without_a_reference_is_reported(self):
        found = issues(mutate=lambda text: text.replace("## Introduction", "RandomForest won 9 of 9 datasets.\n\n## Introduction", 1))
        assert any("a numeric line in Abstract has no evidence reference" in issue for issue in found)

    def test_a_numeric_line_in_the_results_without_a_reference_is_reported(self):
        found = issues(mutate=lambda text: text.replace("## Discussion", "RandomForest won 9 of 9 datasets.\n\n## Discussion", 1).replace("\n## Discussion\n\nRandomForest", "\nRandomForest") if False else text.replace("### Where the claims did not hold", "RandomForest won 9 of 9 datasets.\n\n### Where the claims did not hold", 1))
        assert any("a numeric line in Results has no evidence reference" in issue for issue in found)

    def test_a_number_in_the_conclusion_without_a_reference_is_reported(self):
        found = issues(mutate=lambda text: text.replace("## Evidence ledger", "It won 9 times.\n\n## Evidence ledger", 1) if False else text.replace("These verdicts concern", "It won 9 times. These verdicts concern", 1))
        assert any("a numeric line in Conclusion" in issue for issue in found)

    def test_the_methodology_may_contain_numbers_without_references(self):
        assert issues(mutate=lambda text: text.replace("## Results", "Ten splits of 6000 rows.\n\n## Results", 1)) == []


class TestDigits:
    @pytest.mark.parametrize("section", ["introduction", "discussion"])
    def test_a_digit_in_a_prose_section_is_reported_with_examples(self, section):
        found = issues({**PROSE, section: PROSE[section] + " It scored 0.9346 on 9 datasets."})
        name = section.capitalize()
        assert f"The {name} must contain no digits, but it contains: 0.9346, 9." in found

    def test_only_the_first_three_examples_are_shown(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " 1 2 3 4 5"})
        assert "but it contains: 1, 2, 3." in " ".join(found)

    def test_digits_in_the_deterministic_sections_are_fine(self):
        assert not any("must contain no digits" in issue for issue in issues())


class TestCertaintyWords:
    @pytest.mark.parametrize("word", ["confirmed", "refutes", "proven", "disproved", "demonstrates", "Confirm"])
    def test_overclaiming_verbs_are_reported(self, word):
        found = issues({**PROSE, "discussion": f"The result {word} the pattern."})
        assert any(f"The Discussion uses the word {word!r}" in issue for issue in found)

    def test_the_introduction_is_checked_too(self):
        found = issues({**PROSE, "introduction": INTRO + " Earlier work proved it."})
        assert any("The Introduction uses the word 'proved'" in issue for issue in found)

    def test_ordinary_words_are_fine(self):
        assert issues({**PROSE, "discussion": "The improvement is approved by nobody and the movement is proven nowhere."}) != []
        assert not any("uses the word" in issue for issue in issues({**PROSE, "discussion": "The approach improved the improvement."}))


class TestVerdictWords:
    def test_the_introduction_may_not_state_a_verdict(self):
        found = issues({**PROSE, "introduction": INTRO + " The claim was replicated."})
        assert "The Introduction must not state verdicts, but it uses 'replicated'." in found

    @pytest.mark.parametrize("word", ["contradicted", "inconclusive", "replication"])
    def test_every_verdict_word_is_barred_from_the_introduction(self, word):
        assert any("The Introduction must not state verdicts" in issue for issue in issues({**PROSE, "introduction": f"{INTRO} It was {word}."}))

    def test_the_discussion_may_restate_a_verdict_that_holds(self):
        assert issues({**PROSE, "discussion": DISCUSSION + " Both claims were replicated."}) == []

    def test_the_discussion_may_not_invent_a_contradiction(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " The first claim was contradicted."})
        assert any("says 'contradicted' although no claim was contradicted" in issue for issue in found)

    def test_a_contradiction_is_fine_when_a_claim_was_contradicted(self):
        spec = {**SPEC, "claims": [{**CLAIMS[0], "subject": ["MLP"], "other": ["RandomForest", "HistGradientBoosting"], "metrics": ["roc_auc"]}]}
        assert not any("although no claim was contradicted" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " The claim was contradicted."}, spec=spec))

    def test_the_discussion_may_not_claim_a_replication_nobody_achieved(self):
        spec = {**SPEC, "claims": [{**CLAIMS[0], "subject": ["MLP"], "other": ["RandomForest", "HistGradientBoosting"], "metrics": ["roc_auc"]}]}
        found = issues({**PROSE, "discussion": DISCUSSION + " The claim was replicated."}, spec=spec)
        assert any("says 'replicated' although no claim was replicated" in issue for issue in found)

    def test_a_negated_replication_is_allowed_when_nothing_replicated(self):
        spec = {**SPEC, "claims": [{**CLAIMS[0], "subject": ["MLP"], "other": ["RandomForest", "HistGradientBoosting"], "metrics": ["roc_auc"]}]}
        found = issues({**PROSE, "discussion": DISCUSSION + " The claim was not replicated."}, spec=spec)
        assert not any("although no claim was replicated" in issue for issue in found)

    def test_inconclusive_needs_an_inconclusive_claim(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " The picture is inconclusive."})
        assert any("says 'inconclusive' although no claim was inconclusive" in issue for issue in found)

    def test_inconclusive_is_fine_when_a_claim_is_inconclusive(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " The picture is inconclusive."}, keys=KEYS[:6])
        assert not any("although no claim was inconclusive" in issue for issue in found)


class TestSpeculation:
    def test_a_cause_stated_as_a_fact_is_reported(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " The network lost because of categorical features."})
        assert any(issue.startswith("A cause is stated as a fact in the Discussion") and "categorical features" in issue for issue in found)

    @pytest.mark.parametrize("connector", ["due to", "owing to", "caused by", "explained by", "driven by", "as a result of", "thanks to"])
    def test_every_causal_connector_needs_a_hedge(self, connector):
        found = issues({**PROSE, "discussion": f"The network lost {connector} noise."})
        assert any("A cause is stated as a fact" in issue for issue in found)

    @pytest.mark.parametrize("hedge", ["may", "might", "could", "possibly", "perhaps", "plausibly", "potentially", "probably", "we speculate that it", "it is possible that it", "a possible reason is that it"])
    def test_a_hedged_cause_is_fine(self, hedge):
        assert not any("A cause is stated" in issue for issue in issues({**PROSE, "discussion": f"The network lost, and {hedge} was due to noise."}))

    def test_a_sentence_without_a_cause_needs_no_hedge(self):
        assert not any("A cause is stated" in issue for issue in issues({**PROSE, "discussion": "The network lost on one dataset."}))

    def test_the_hedge_must_be_in_the_same_sentence(self):
        found = issues({**PROSE, "discussion": "The network may struggle. It lost because of noise."})
        assert any("A cause is stated as a fact" in issue for issue in found)


class TestGeneralisation:
    @pytest.mark.parametrize(
        ("phrase", "matched"),
        [
            ("always", "always"),
            ("never", "never"),
            ("universally", "universally"),
            ("in general", "in general"),
            ("on all tabular data", "all tabular"),
            ("on every tabular problem", "every tabular"),
            ("on every dataset", "every dataset"),
            ("on all datasets", "all datasets"),
            ("on any dataset", "any dataset"),
        ],
    )
    def test_absolute_statements_are_reported_in_both_prose_sections(self, phrase, matched):
        for section in ("introduction", "discussion"):
            found = issues({**PROSE, section: f"{PROSE[section]} Trees win {phrase}."})
            assert any(f"The {section.capitalize()} generalises beyond the datasets tested with {matched!r}" in issue for issue in found)

    def test_the_deterministic_sections_may_say_every_one_of_the_datasets(self):
        assert not any("generalises" in issue for issue in issues())


class TestScope:
    def test_a_model_that_was_not_run_is_reported(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " XGBoost might do better."})
        assert "The Discussion mentions XGBoost, which was not run in this campaign." in found

    def test_spacing_and_case_do_not_hide_a_model(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " A support vector SVM and a decision tree and extra trees might help."})
        assert "The Discussion mentions SVM, which was not run in this campaign." in found
        assert "The Discussion mentions DecisionTree, which was not run in this campaign." in found
        assert "The Discussion mentions ExtraTrees, which was not run in this campaign." in found

    def test_the_introduction_is_checked_too(self):
        assert "The Introduction mentions KNN, which was not run in this campaign." in issues({**PROSE, "introduction": INTRO + " KNN is a classic."})

    def test_models_that_were_run_are_fine_in_any_spelling(self):
        text = DISCUSSION + " Random forest, random-forest and hist gradient boosting did well; gradient boosting is fast; logistic regression and MLP lagged."
        assert not any("which was not run" in issue for issue in issues({**PROSE, "discussion": text}))

    def test_a_family_name_inside_a_run_model_is_not_a_new_model(self):
        assert not any("GradientBoosting" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " Gradient boosting helps."}))

    def test_a_dataset_outside_the_campaign_is_reported(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " On breast_cancer the picture may differ."})
        assert "The Discussion mentions the dataset breast_cancer, which was not part of this campaign." in found

    def test_a_benchmark_dataset_that_was_not_run_is_reported(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " The tb_unknown set may differ."}, keys=KEYS)
        assert "The Discussion mentions the dataset tb_unknown, which was not part of this campaign." in found

    def test_a_dataset_that_failed_is_not_part_of_the_campaign_text_unless_requested(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " The tb_eye set may differ."}, keys=KEYS[:8])
        assert "The Discussion mentions the dataset tb_eye, which was not part of this campaign." in found

    def test_a_dataset_that_was_run_is_fine(self):
        assert not any("which was not part" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " On tb_pol the gap was small."}))

    def test_each_mention_is_reported_once(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " XGBoost helps. XGBoost may win. On breast_cancer and breast_cancer."})
        assert found.count("The Discussion mentions XGBoost, which was not run in this campaign.") == 1
        assert found.count("The Discussion mentions the dataset breast_cancer, which was not part of this campaign.") == 1


class TestCitations:
    def test_a_quoted_source_title_is_fine(self):
        assert not any("not one of the provided sources" in issue for issue in issues())

    def test_a_title_in_another_case_is_fine(self):
        assert not any("not one of the provided" in issue for issue in issues({**PROSE, "introduction": INTRO.replace(TITLE, TITLE.upper())}))

    def test_an_invented_source_is_reported(self):
        found = issues({**PROSE, "introduction": INTRO + ' Earlier, "A Study of Imaginary Boosting Methods" showed it.'})
        assert any("cites 'A Study of Imaginary Boosting Methods', which is not one of the provided sources" in issue for issue in found)

    def test_a_literature_source_is_fine(self):
        other = [{"title": "Another paper about tables", "abstract": "x", "url": ""}]
        assert not any("not one of the provided" in issue for issue in issues({**PROSE, "introduction": INTRO + ' See "Another paper about tables".'}, sources=other))

    def test_short_quotations_are_not_sources(self):
        assert not any("not one of the provided" in issue for issue in issues({**PROSE, "introduction": INTRO + ' The so-called "state of the art" varies a lot.'}))

    def test_without_sources_only_the_spec_title_is_known(self):
        assert issues(sources=None) == []

    def test_the_discussion_is_not_checked_for_quotations(self):
        assert not any("not one of the provided" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + ' It echoes "an unknown quoted source title".'}))


class TestStructure:
    def test_a_wrong_verdict_in_the_abstract_is_reported(self):
        found = issues(mutate=lambda text: text.replace("was **Replicated** on ROC-AUC", "was **Contradicted** on ROC-AUC", 1))
        assert any("The Abstract does not state the verdict of C1: Replicated." in issue for issue in found)

    def test_a_missing_claim_in_the_abstract_is_reported(self):
        found = issues(mutate=lambda text: text.replace("**C2** (The MLP beats logistic regression)", "The second claim"))
        assert any("The Abstract does not state the verdict of C2" in issue for issue in found)

    def test_a_lost_source_title_is_reported(self):
        found = issues(mutate=lambda text: text.replace(TITLE, "an anonymous paper").replace('"an anonymous paper"', "an anonymous paper"))
        assert "The source title appears neither in the Abstract nor in the Methodology." in found

    def test_no_source_means_no_title_check(self):
        spec = {**SPEC, "source": {}}
        assert not any("source title" in issue for issue in issues({**PROSE, "introduction": "Tabular data is common."}, spec=spec, sources=[]))

    def test_a_dropped_deviation_is_reported(self):
        found = issues(mutate=lambda text: text.replace("- 6000 rows\n", ""))
        assert "The Methodology omits the deviation: 6000 rows" in found

    def test_a_failed_dataset_missing_from_the_limitations_is_reported(self):
        found = issues(failed={"tb_extra": {"error": "OutOfMemory", "attempts": 2}}, keys=KEYS[:8], mutate=lambda text: text.replace("tb_extra", "an unnamed set"))
        assert "The Limitations do not mention the failed dataset tb_extra." in found

    def test_a_failed_dataset_named_in_the_limitations_is_fine(self):
        assert not any("do not mention the failed dataset" in issue for issue in issues(failed={"tb_extra": {"error": "OutOfMemory", "attempts": 2}}, keys=KEYS[:8]))


def test_the_issue_lists_are_empty_for_missing_inputs():
    assert gate.meta_issues("", {}, {}, []) == []


def test_several_problems_are_all_reported_together():
    found = issues({"introduction": INTRO + " It scored 0.9 and was replicated.", "discussion": DISCUSSION + " XGBoost proved it because of noise."})
    assert len(found) >= 5


class TestSecondPass:
    def test_one_possible_is_a_hedge(self):
        assert not any("A cause is stated" in issue for issue in issues({**PROSE, "discussion": "One possible reading is that the loss was due to noise."}))

    @pytest.mark.parametrize(
        "negation",
        ["The claim was not replicated", "The claim wasn't replicated", "The claim failed to be replicated", "We were unable to see it replicated", "It cannot be replicated"],
    )
    def test_a_negated_replication_is_not_a_false_claim(self, negation):
        spec = {**SPEC, "claims": [{**CLAIMS[0], "subject": ["MLP"], "other": ["RandomForest", "HistGradientBoosting"], "metrics": ["roc_auc"]}]}
        found = issues({**PROSE, "discussion": DISCUSSION + f" {negation}."}, spec=spec)
        assert not any("although no claim was replicated" in issue for issue in found)

    def test_an_unnegated_replication_is_a_false_claim_when_nothing_replicated(self):
        spec = {**SPEC, "claims": [{**CLAIMS[0], "subject": ["MLP"], "other": ["RandomForest", "HistGradientBoosting"], "metrics": ["roc_auc"]}]}
        found = issues({**PROSE, "discussion": DISCUSSION + " Elsewhere the claim is described as replicated."}, spec=spec)
        assert any("although no claim was replicated" in issue for issue in found)

    def test_a_question_mark_ends_a_sentence(self):
        found = issues({**PROSE, "discussion": "Might noise be the reason? The network lost because of noise."})
        assert any("A cause is stated as a fact" in issue and "because of noise" in issue for issue in found)

    def test_an_exclamation_mark_ends_a_sentence(self):
        found = issues({**PROSE, "discussion": "It may be noise! The network lost because of noise."})
        assert any("A cause is stated as a fact" in issue for issue in found)

    def test_a_word_inside_another_word_is_not_a_model(self):
        assert not any("which was not run" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " The dissvmtool and the subknnlike part are unrelated."}))

    def test_one_certainty_issue_is_reported_per_section(self):
        found = issues({**PROSE, "discussion": "The result confirmed it and proved it and demonstrated it."})
        assert len([issue for issue in found if "uses the word" in issue]) == 1

    def test_a_partially_replicated_claim_allows_the_word_replicated(self):
        text, analysis, ledger = paper({**PROSE, "discussion": DISCUSSION + " Parts of the first claim were replicated."})
        for claim in analysis["claims"]:
            claim["verdict"] = "partially_replicated"
        found = meta_issues(text, {**SPEC, "datasets": KEYS}, analysis, ledger, SOURCES)
        assert not any("although no claim was replicated" in issue for issue in found)

    def test_a_non_testable_claim_allows_the_word_inconclusive(self):
        text, analysis, ledger = paper({**PROSE, "discussion": DISCUSSION + " The picture is inconclusive."})
        for claim in analysis["claims"]:
            claim["verdict"] = "not_testable"
        found = meta_issues(text, {**SPEC, "datasets": KEYS}, analysis, ledger, SOURCES)
        assert not any("although no claim was inconclusive" in issue for issue in found)

    def test_the_source_title_may_appear_only_in_the_abstract(self):
        def only_abstract(text):
            head, rest = text.split("## Methodology", 1)
            body, tail = rest.split("## Results", 1)
            return head + "## Methodology" + body.replace(TITLE, "the source") + "## Results" + tail

        assert not any("source title" in issue for issue in issues(mutate=only_abstract))

    def test_the_source_title_may_appear_only_in_the_methodology(self):
        def only_methodology(text):
            head, rest = text.split("## Introduction", 1)
            return head.replace(f'"{TITLE}"', "the source") + "## Introduction" + rest

        assert not any("source title" in issue for issue in issues(mutate=only_methodology))


class TestLiveRunLessons:
    @pytest.mark.parametrize("text", ["The F1 score of MLP differed.", "Claim C1 held while C12 is unknown.", "On tb_house16h the gap was small.", "ROC-AUC and PR-AUC are fine."])
    def test_names_that_contain_digits_are_not_numbers(self, text):
        assert not any("must contain no digits" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " " + text}))

    @pytest.mark.parametrize("text", ["The gap was 12 points.", "It scored 0.91.", "F10 is not a metric.", "C is a letter but 2 is not.", "The tb_pol set had 4 features."])
    def test_real_numbers_are_still_reported(self, text):
        assert any("must contain no digits" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " " + text}))

    def test_the_digit_examples_do_not_include_the_exempt_names(self):
        found = issues({**PROSE, "discussion": "F1 and C1 and tb_house16h and 7 and 3.5."})
        assert "The Discussion must contain no digits, but it contains: 7, 3.5." in found

    @pytest.mark.parametrize("word", ["significantly", "significant", "Significance", "significance"])
    def test_significance_wording_is_reserved_for_the_results(self, word):
        for section in ("introduction", "discussion"):
            found = issues({**PROSE, section: f"{PROSE[section]} It {word} differs."})
            assert any(f"The {section.capitalize()} uses statistical wording" in issue for issue in found)

    def test_insignificant_is_a_different_word_and_the_results_may_use_significance(self):
        assert not any("statistical wording" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " The gap looks insignificant here."}))
        assert not any("statistical wording" in issue for issue in issues())


class TestSupportWords:
    @pytest.mark.parametrize("word", ["supported", "supports", "Supported"])
    def test_supported_is_a_verdict_word_the_prose_may_not_borrow(self, word):
        for section in ("introduction", "discussion"):
            found = issues({**PROSE, section: f"{PROSE[section]} The claim was {word} by the data."})
            assert any(f"The {section.capitalize()} uses the word {word!r}" in issue for issue in found)

    def test_a_noun_or_other_form_is_not_flagged(self):
        assert not any("uses the word" in issue for issue in issues({**PROSE, "discussion": DISCUSSION + " Supporting facts and a supporter exist."}))

    def test_the_significance_message_tells_the_writer_what_to_say_instead(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " It differs significantly."})
        assert any("compare with plain words such as larger, smaller, ahead or behind" in issue for issue in found)


class TestYears:
    @pytest.mark.parametrize("year", ["1999", "2022", "2030"])
    def test_a_publication_year_is_fine_in_the_introduction(self, year):
        assert not any("must contain no digits" in issue for issue in issues({**PROSE, "introduction": f"{INTRO} The claim comes from Grinsztajn et al. {year}."}))

    def test_a_year_is_not_a_free_pass_in_the_discussion(self):
        found = issues({**PROSE, "discussion": DISCUSSION + " It resembles a 2022 result."})
        assert "The Discussion must contain no digits, but it contains: 2022." in found

    @pytest.mark.parametrize("number", ["1850", "3000", "20225", "12"])
    def test_other_numbers_are_still_reported_in_the_introduction(self, number):
        found = issues({**PROSE, "introduction": f"{INTRO} It used {number} rows."})
        assert any("The Introduction must contain no digits" in issue for issue in found)

    def test_the_numbers_beside_a_year_are_still_reported(self):
        found = issues({**PROSE, "introduction": f"{INTRO} In 2022 it used 6000 rows."})
        assert "The Introduction must contain no digits, but it contains: 6000." in found
