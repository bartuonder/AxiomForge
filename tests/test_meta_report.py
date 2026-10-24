import json
import re

import pytest

import app.agents.meta_report as meta_report
import app.campaign.store as store
import app.graph.campaign_nodes as campaign_nodes
from app.campaign.analysis import analyze_campaign
from app.campaign.ledger import build_ledger
from app.campaign.report import render_report, report_issues
from app.seeds import SPLIT_SEEDS

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Tree-based models beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"],
     "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"],
     "subject": ["MLP"], "other": ["LogisticRegression"]},
]
SOURCE = {"title": "Why do tree-based models still outperform deep learning on tabular data?", "citation": "Grinsztajn et al., 2022", "url": "https://arxiv.org/abs/2207.08815", "deviations": ["no search", "6000 rows"]}
SPEC = {"title": "Trees against networks", "models": MODELS, "params": {}, "claims": CLAIMS, "source": SOURCE}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h", "tb_pol", "tb_eye"]
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}
SOURCES = [{"title": "Why do tree-based models still outperform deep learning on tabular data?", "abstract": "Trees remain state of the art.", "url": "https://arxiv.org/abs/2207.08815"}]
PROSE = {"introduction": "Tabular data is common. The source asks whether trees win.", "discussion": "The pattern may reflect dataset size; we speculate that categorical features matter."}


def outcome(keys=KEYS, overrides=None):
    def summary(shift, extra):
        record = {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}
        for (model, metric), value in (extra or {}).items():
            record[model][f"{metric}_mean"] = value
        return record

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


def world(keys=KEYS, overrides=None, spec=SPEC):
    data = outcome(keys, overrides)
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    return analysis, ledger, markdown


@pytest.fixture(autouse=True)
def key(monkeypatch, tmp_path):
    monkeypatch.setattr(meta_report, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(meta_report, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")


@pytest.fixture
def llm(monkeypatch):
    replies, prompts = [], []

    def complete(user):
        prompts.append(user)
        return replies.pop(0)

    monkeypatch.setattr(meta_report, "_complete", complete)
    return replies, prompts


def prose_reply(**changes):
    return json.dumps({**PROSE, **changes})


class TestSections:
    def test_the_headings_split_a_report_into_sections(self):
        text = "# Title\n\nintro\n\n## Summary\n\nalpha\n\n## Protocol\n\nbeta\n\ngamma\n\n## Limitations\n\n- one\n"
        assert meta_report.split_sections(text) == {"Summary": "alpha", "Protocol": "beta\n\ngamma", "Limitations": "- one"}

    def test_a_text_without_sections_gives_none(self):
        assert meta_report.split_sections("# Only a title\n\ntext") == {}

    def test_a_sub_heading_does_not_split(self):
        assert list(meta_report.split_sections("## A\n\n### B\n\ntext")) == ["A"]

    def test_the_real_campaign_report_has_the_expected_sections(self):
        _, _, markdown = world()
        assert list(meta_report.split_sections(markdown)) == ["Summary", "Protocol", "Results", "Limitations", "Evidence ledger"]


class TestAbstract:
    def test_it_states_the_source_the_datasets_the_models_and_the_protocol(self):
        analysis, ledger, _ = world()
        text = meta_report.abstract(SPEC, analysis, ledger)
        refs = " ".join(f"[{entry['id']}]" for entry in ledger if entry["kind"] == "dataset")
        first = text.split("\n\n")[0]
        assert first.startswith('This report replicates the claims of "Why do tree-based models still outperform deep learning on tabular data?" on 9 tabular classification datasets ' + refs)
        assert "It compares RandomForest, HistGradientBoosting, MLP and LogisticRegression with 10 repeated stratified splits per dataset" in first
        assert "exact signed-rank and Friedman tests" in first

    def test_the_split_count_follows_the_protocol(self):
        analysis, ledger, _ = world()
        assert f"with {len(SPLIT_SEEDS)} repeated stratified splits" in meta_report.abstract(SPEC, analysis, ledger)

    def test_it_ends_with_the_verdicts_and_the_overall_leader(self):
        analysis, ledger, _ = world()
        paragraphs = meta_report.abstract(SPEC, analysis, ledger).split("\n\n")
        assert "was **Replicated** on ROC-AUC, PR-AUC and F1" in paragraphs[-2]
        assert paragraphs[-1].startswith("Averaged over the metrics, the mean ranks (1 = best) were HistGradientBoosting")

    def test_documented_deviations_are_pointed_to_without_numbers(self):
        analysis, ledger, _ = world()
        text = meta_report.abstract(SPEC, analysis, ledger)
        assert "The protocol differs from the original study in documented ways, listed in the Methodology." in text

    def test_without_deviations_the_pointer_is_left_out(self):
        spec = {**SPEC, "source": {"title": SOURCE["title"]}}
        analysis, ledger, _ = world(spec=spec)
        assert "differs from" not in meta_report.abstract(spec, analysis, ledger)

    def test_without_a_source_the_claims_are_just_the_stated_ones(self):
        spec = {**SPEC, "source": {}}
        analysis, ledger, _ = world(spec=spec)
        assert meta_report.abstract(spec, analysis, ledger).startswith("This report replicates the stated claims on 9")

    def test_a_single_model_campaign_is_not_possible_but_the_list_is_still_joined_safely(self):
        analysis, ledger, _ = world()
        spec = {**SPEC, "models": ["RandomForest"]}
        assert "It compares RandomForest with" in meta_report.abstract(spec, analysis, ledger)

    def test_a_campaign_where_nothing_finished_says_so(self):
        failed = {key: {"error": "boom", "attempts": 2} for key in KEYS[:2]}
        data = {"order": list(failed), "datasets": {}, "failed": failed}
        analysis = analyze_campaign(SPEC, data)
        ledger = build_ledger(SPEC, data, analysis)
        assert meta_report.abstract(SPEC, analysis, ledger) == (
            'This report tried to replicate the claims of "Why do tree-based models still outperform deep learning on tabular data?" across 2 datasets, '
            "but no dataset finished, so no claim could be assessed."
        )


class TestConclusionAndResults:
    def test_the_conclusion_restates_each_verdict_and_limits_it_to_the_datasets_tested(self):
        analysis, ledger, _ = world()
        assert meta_report.conclusion(analysis, ledger) == (
            "Under this protocol, **C1** was Replicated and **C2** was Replicated. "
            "These verdicts concern only the datasets tested and the estimators named in the Methodology."
        )

    def test_the_conclusion_of_an_empty_campaign_draws_nothing(self):
        assert meta_report.conclusion({"error": "x", "coverage": {}}, []) == "No claim could be assessed, so this report draws no conclusion about the source."
        assert meta_report.conclusion({"claims": []}, []) == "No claim could be assessed, so this report draws no conclusion about the source."

    def test_the_results_join_the_summary_the_tables_and_the_exceptions(self):
        analysis, ledger, markdown = world(overrides={"tb_eye": {("MLP", "roc_auc"): 0.95}})
        sections = meta_report.split_sections(markdown)
        text = meta_report.results(sections, analysis, ledger)
        assert text.startswith(sections["Summary"]) and sections["Results"] in text
        assert "### Where the claims did not hold, and where they held most clearly" in text
        assert "did not score higher than MLP on 1 of 9 datasets: tb_eye" in text and "The largest advantage of" in text

    def test_an_empty_campaign_has_no_exception_block(self):
        failed = {key: {"error": "boom", "attempts": 2} for key in KEYS[:2]}
        data = {"order": list(failed), "datasets": {}, "failed": failed}
        analysis = analyze_campaign(SPEC, data)
        ledger = build_ledger(SPEC, data, analysis)
        markdown = render_report(SPEC, data, analysis)[0]
        assert "Where the claims did not hold" not in meta_report.results(meta_report.split_sections(markdown), analysis, ledger)

    def test_missing_sections_are_simply_left_out(self):
        analysis, ledger, _ = world()
        assert meta_report.results({}, analysis, ledger).startswith("### Where the claims did not hold")


class TestCompose:
    def paper(self, prose=PROSE):
        analysis, ledger, markdown = world()
        return meta_report.compose(SPEC, analysis, ledger, markdown, prose), ledger

    def test_the_sections_come_in_the_academic_order(self):
        paper, _ = self.paper()
        headings = [line for line in paper.splitlines() if line.startswith("#") and not line.startswith("###")]
        assert headings == ["# Trees against networks", "## Abstract", "## Introduction", "## Methodology", "## Results", "## Discussion", "## Limitations", "## Conclusion", "## Evidence ledger"]

    def test_the_llm_sections_are_inserted_verbatim(self):
        paper, _ = self.paper()
        assert "## Introduction\n\nTabular data is common. The source asks whether trees win.\n\n## Methodology" in paper
        assert "## Discussion\n\nThe pattern may reflect dataset size; we speculate that categorical features matter.\n\n## Limitations" in paper

    def test_the_methodology_is_the_campaign_protocol(self):
        paper, _ = self.paper()
        assert "Source: Why do tree-based models still outperform deep learning on tabular data?; Grinsztajn et al., 2022; https://arxiv.org/abs/2207.08815." in paper.split("## Methodology")[1].split("## Results")[0]
        assert "- no search" in paper and "- 6000 rows" in paper

    def test_an_empty_discussion_leaves_out_its_heading(self):
        paper, _ = self.paper({"introduction": "Intro.", "discussion": ""})
        assert "## Discussion" not in paper

    def test_the_ledger_table_of_the_campaign_report_is_kept_so_that_references_resolve(self):
        paper, ledger = self.paper()
        assert "| E1 |" in paper.split("## Evidence ledger")[1]
        unresolved = [issue for issue in report_issues(paper, ledger) if "is cited but not in the ledger" in issue]
        assert unresolved == []

    def test_the_paper_is_deterministic_apart_from_the_prose(self):
        assert self.paper()[0] == self.paper()[0]
        other = self.paper({"introduction": "Different intro.", "discussion": PROSE["discussion"]})[0]
        assert other.replace("Different intro.", PROSE["introduction"]) == self.paper()[0]

    def test_the_deterministic_sections_cite_the_ledger_on_every_numeric_line(self):
        paper, ledger = self.paper()
        for name in ("Abstract", "Results"):
            body = paper.split(f"## {name}\n\n")[1].split("\n## ")[0]
            for line in body.splitlines():
                stripped = re.sub(r"\bF1\b", "", re.sub(r"^\*\*[A-Za-z][\w-]*\*\*", "", line))
                if re.search(r"\d", stripped):
                    assert re.search(r"\[E\d+\]", line), line

    def test_a_paper_without_a_protocol_section_still_composes(self):
        analysis, ledger, _ = world()
        paper = meta_report.compose(SPEC, analysis, ledger, "# T\n\n## Summary\n\nsummary only\n", PROSE)
        assert "## Methodology\n\n\n\n## Results" in paper


class TestProse:
    def test_the_prose_comes_from_the_model_as_two_sections(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        analysis, ledger, _ = world()
        prose = meta_report.write_prose("Replicate it", SOURCES, SPEC, analysis, ledger)
        assert prose == PROSE and len(prompts) == 1

    def test_the_brief_holds_the_query_the_sources_the_claims_and_the_facts(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        analysis, ledger, _ = world()
        meta_report.write_prose("Replicate it", SOURCES, SPEC, analysis, ledger)
        brief = prompts[0]
        assert "User query:\nReplicate it" in brief
        assert f'"{SOURCES[0]["title"]}": Trees remain state of the art.' in brief
        assert "- C1: Tree-based models beat the MLP" in brief and "- C2: The MLP beats logistic regression" in brief
        assert "Facts for the discussion:\n- **C1** (Tree-based models beat the MLP) was **Replicated**" in brief
        assert "rejected" not in brief

    def test_a_rewrite_carries_the_feedback(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        analysis, ledger, _ = world()
        meta_report.write_prose("q", SOURCES, SPEC, analysis, ledger, "The discussion contains digits.")
        assert "Your previous text was rejected for these reasons, rewrite both sections and fix them: The discussion contains digits." in prompts[0]

    def test_without_sources_the_brief_says_so(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        analysis, ledger, _ = world()
        meta_report.write_prose("q", [], SPEC, analysis, ledger)
        assert "No source paper states these claims; they come from the user query." in prompts[0]

    def test_a_missing_key_stops_before_any_call(self, monkeypatch):
        monkeypatch.setattr(meta_report, "OPENAI_API_KEY", "")
        monkeypatch.setattr(meta_report, "_complete", lambda user: pytest.fail("called"))
        analysis, ledger, _ = world()
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is missing"):
            meta_report.write_prose("q", SOURCES, SPEC, analysis, ledger)

    @pytest.mark.parametrize(
        ("reply", "message"),
        [
            ("not json", "invalid JSON"),
            (json.dumps([1]), "did not return an object"),
            (json.dumps({"introduction": "x"}), "did not return discussion"),
            (json.dumps({"discussion": "x"}), "did not return introduction"),
            (json.dumps({"introduction": 5, "discussion": "x"}), "did not return introduction"),
            (json.dumps({"introduction": "  ", "discussion": "x"}), "empty introduction"),
        ],
    )
    def test_a_bad_answer_is_reported(self, llm, reply, message):
        replies, _ = llm
        replies.append(reply)
        analysis, ledger, _ = world()
        with pytest.raises(RuntimeError, match=message):
            meta_report.write_prose("q", SOURCES, SPEC, analysis, ledger)

    def test_nothing_to_discuss_means_no_discussion_even_if_the_model_wrote_one(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        failed = {key: {"error": "boom", "attempts": 2} for key in KEYS[:2]}
        data = {"order": list(failed), "datasets": {}, "failed": failed}
        analysis = analyze_campaign(SPEC, data)
        ledger = build_ledger(SPEC, data, analysis)
        prose = meta_report.write_prose("q", SOURCES, SPEC, analysis, ledger)
        assert prose["discussion"] == "" and "Facts for the discussion:\n(none)" in prompts[0]

    def test_the_text_is_stripped(self, llm):
        replies, _ = llm
        replies.append(prose_reply(introduction="  Intro.  \n", discussion="\nDiscussion may differ.\n"))
        analysis, ledger, _ = world()
        assert meta_report.write_prose("q", SOURCES, SPEC, analysis, ledger) == {"introduction": "Intro.", "discussion": "Discussion may differ."}

    def test_the_model_is_asked_deterministically_for_json(self, monkeypatch):
        seen = {}

        class Completions:
            def create(self, **kwargs):
                seen.update(kwargs)
                message = type("Message", (), {"content": "{}"})()
                return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

        class Client:
            def __init__(self, api_key):
                seen["key"] = api_key
                self.chat = type("Chat", (), {"completions": Completions()})()

        monkeypatch.setattr(meta_report, "OpenAI", Client)
        assert meta_report._complete("hello") == "{}"
        assert seen["temperature"] == 0 and seen["response_format"] == {"type": "json_object"} and seen["model"] == meta_report.MODEL
        assert seen["messages"] == [{"role": "system", "content": meta_report.SYSTEM_PROMPT}, {"role": "user", "content": "hello"}]

    def test_the_model_name_is_fixed(self):
        assert meta_report.MODEL == "gpt-4o"

    def test_each_section_has_its_own_rules(self):
        assert "use no digits at all; " in meta_report.INTRODUCTION_RULES
        assert "never use the words replicated, contradicted, confirmed, supported or refuted" in meta_report.INTRODUCTION_RULES
        assert "use no digits at all, so write no numbers, p-values or scores" in meta_report.DISCUSSION_RULES
        assert "mention only models and datasets that appear in the facts" in meta_report.DISCUSSION_RULES
        assert "do not introduce a verdict that the facts do not state" in meta_report.DISCUSSION_RULES
        assert "return an empty discussion" in meta_report.DISCUSSION_RULES
        assert "return only JSON with the keys introduction and discussion" in meta_report.SYSTEM_PROMPT

    def test_the_prompt_forbids_numbers_verdict_words_and_unhedged_causes(self):
        prompt = meta_report.SYSTEM_PROMPT
        assert "use no digits at all" in prompt and "never use the words replicated, contradicted, confirmed, supported or refuted" in prompt
        assert "hedged wording" in prompt and "never present a cause as a fact" in prompt
        assert "never generalise beyond the datasets named in the facts" in prompt and "mention a source only by its exact title" in prompt


class TestWriteMetaPaper:
    def state(self, campaign_id="g-1", **changes):
        analysis, ledger, _ = world()
        return {
            "query": "Replicate the claim",
            "literature_sources": SOURCES,
            "campaign_id": campaign_id,
            "campaign_spec": SPEC,
            "campaign_analysis": analysis,
            "campaign_ledger": ledger,
            **changes,
        }

    def stored(self, campaign_id="g-1"):
        analysis, ledger, markdown = world()
        store.save_artifacts(campaign_id, markdown, ledger, analysis, {})

    def test_the_paper_is_written_next_to_the_other_papers(self, llm):
        replies, _ = llm
        replies.append(prose_reply())
        self.stored()
        path = meta_report.write_meta_paper(self.state(), "thread-1")
        assert path.endswith("thread-1_paper.md")
        text = open(path, encoding="utf-8").read()
        assert text.startswith("# Trees against networks") and "## Discussion" in text and text.endswith("\n")

    def test_the_query_and_the_sources_of_the_run_reach_the_model(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        self.stored()
        meta_report.write_meta_paper(self.state(), "thread-1")
        assert "User query:\nReplicate the claim" in prompts[0]
        assert f'"{SOURCES[0]["title"]}": Trees remain state of the art.' in prompts[0]

    def test_the_feedback_of_the_gate_reaches_the_model(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        self.stored()
        meta_report.write_meta_paper(self.state(consistency_feedback="No digits in the discussion."), "thread-1")
        assert "No digits in the discussion." in prompts[0]

    def test_a_missing_campaign_report_stops_the_paper(self, llm):
        with pytest.raises(RuntimeError, match="the campaign report is missing"):
            meta_report.write_meta_paper(self.state(), "thread-1")
        with pytest.raises(RuntimeError, match="the campaign report is missing"):
            meta_report.write_meta_paper(self.state(campaign_id=""), "thread-1")

    def test_missing_sources_are_tolerated(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        self.stored()
        state = self.state()
        del state["literature_sources"]
        meta_report.write_meta_paper(state, "thread-1")
        assert "No source paper states these claims; they come from the user query." in prompts[0]


class TestNode:
    def test_the_node_returns_the_paper_text_and_clears_the_rewrite_flag(self, monkeypatch, tmp_path):
        path = tmp_path / "paper.md"
        path.write_text("# paper\n", encoding="utf-8")
        seen = []
        monkeypatch.setattr(campaign_nodes, "write_meta_paper", lambda state, run_id: seen.append(run_id) or str(path))
        update = campaign_nodes.meta_report_node({"query": "q"}, {"configurable": {"thread_id": "thread-9"}})
        assert update == {"paper_markdown": "# paper\n", "consistency_continue": False} and seen == ["thread-9"]

    def test_a_missing_thread_id_falls_back_to_run(self, monkeypatch, tmp_path):
        path = tmp_path / "paper.md"
        path.write_text("x", encoding="utf-8")
        seen = []
        monkeypatch.setattr(campaign_nodes, "write_meta_paper", lambda state, run_id: seen.append(run_id) or str(path))
        campaign_nodes.meta_report_node({}, {})
        campaign_nodes.meta_report_node({}, None)
        assert seen == ["run", "run"]


class TestClaimSources:
    OTHER = {"title": "An unrelated paper about fairness", "abstract": "Fairness of language models.", "url": ""}

    def test_only_the_paper_the_claims_come_from_is_kept(self):
        assert meta_report.claim_sources(SPEC, [self.OTHER, *SOURCES]) == SOURCES

    def test_claims_from_the_query_have_no_source_paper(self):
        assert meta_report.claim_sources({**SPEC, "source": {}}, [self.OTHER, *SOURCES]) == []
        assert meta_report.claim_sources({**SPEC, "source": {"deviations": ["x"]}}, SOURCES) == []
        assert meta_report.claim_sources({}, SOURCES) == []

    def test_a_title_that_matches_no_paper_keeps_nothing(self):
        assert meta_report.claim_sources({**SPEC, "source": {"title": "Another title"}}, SOURCES) == []

    def test_the_introduction_brief_never_shows_an_unrelated_abstract(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        analysis, ledger, _ = world()
        meta_report.write_prose("q", [self.OTHER, *SOURCES], SPEC, analysis, ledger)
        assert "Fairness of language models." not in prompts[0] and "Trees remain state of the art." in prompts[0]

    def test_a_claim_from_the_query_shows_no_abstract_at_all(self, llm):
        replies, prompts = llm
        replies.append(prose_reply())
        analysis, ledger, _ = world()
        meta_report.write_prose("q", [self.OTHER, *SOURCES], {**SPEC, "source": {}}, analysis, ledger)
        assert "Fairness of language models." not in prompts[0] and "Trees remain state of the art." not in prompts[0]
        assert "they come from the user query" in prompts[0]
