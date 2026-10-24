import pytest

import app.graph.campaign_nodes as campaign_nodes
from app.agents.meta_report import compose
from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report
from app.graph.campaign_nodes import MAX_META_ROUNDS, meta_consistency_node, route_after_meta_consistency

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Tree-based models beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"],
     "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
]
TITLE = "A paper about trees and tables"
SPEC = {"title": "T", "models": MODELS, "params": {}, "claims": CLAIMS, "source": {"title": TITLE, "deviations": ["no search"]}}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h", "tb_pol", "tb_eye"]
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}
SOURCES = [{"title": TITLE, "abstract": "Trees win.", "url": ""}]


def world():
    def summary(shift):
        return {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}

    data = {
        "order": KEYS,
        "datasets": {
            key: {
                "summary": summary(0.001 * index),
                "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
                "seconds": 10.0,
                "attempts": 1,
                "script": "s",
            }
            for index, key in enumerate(KEYS)
        },
        "failed": {},
    }
    analysis = analyze_campaign(SPEC, data)
    markdown, ledger = render_report(SPEC, data, analysis)
    return {**SPEC, "datasets": KEYS}, analysis, ledger, markdown


def state(prose, **changes):
    spec, analysis, ledger, markdown = world()
    paper = compose(spec, analysis, ledger, markdown, prose)
    base = {
        "paper_markdown": paper,
        "campaign_spec": spec,
        "campaign_analysis": analysis,
        "campaign_ledger": ledger,
        "literature_sources": SOURCES,
        "campaign_issues": [],
        "campaign_status": "completed",
        "consistency_rounds": 0,
    }
    return {**base, **changes}


CLEAN = {"introduction": f'The paper "{TITLE}" compares trees with networks on tables.', "discussion": "The trees held up on most datasets and the pattern is specific to them."}
DIRTY = {"introduction": CLEAN["introduction"], "discussion": "The trees won 9 of the datasets."}


def test_a_clean_paper_completes_the_research():
    update = meta_consistency_node(state(CLEAN))
    assert update == {"consistency_feedback": "", "consistency_continue": False, "research_status": "Completed", "referee_notes": []}


def test_a_dirty_paper_goes_back_to_the_writer_with_the_issues():
    update = meta_consistency_node(state(DIRTY))
    assert update["consistency_continue"] is True and update["consistency_rounds"] == 1
    assert "The Discussion must contain no digits, but it contains: 9." in update["consistency_feedback"]
    assert "research_status" not in update


def test_the_second_rewrite_is_still_allowed():
    update = meta_consistency_node(state(DIRTY, consistency_rounds=MAX_META_ROUNDS - 1))
    assert update["consistency_continue"] is True and update["consistency_rounds"] == MAX_META_ROUNDS


def test_after_the_last_rewrite_the_paper_needs_review_with_the_remaining_issues():
    update = meta_consistency_node(state(DIRTY, consistency_rounds=MAX_META_ROUNDS))
    assert update["research_status"] == "NeedsReview" and update["consistency_continue"] is False
    assert "must contain no digits" in update["consistency_feedback"] and update["referee_notes"] == []
    assert "consistency_rounds" not in update


def test_the_round_limit_is_two():
    assert MAX_META_ROUNDS == 2


def test_a_clean_paper_of_a_campaign_with_issues_needs_review_and_names_them():
    update = meta_consistency_node(state(CLEAN, campaign_issues=["E9 is cited but not in the ledger"]))
    assert update["research_status"] == "NeedsReview" and update["consistency_continue"] is False
    assert update["consistency_feedback"] == "Campaign check: E9 is cited but not in the ledger"


def test_a_campaign_marked_for_review_keeps_the_research_in_review_even_without_listed_issues():
    update = meta_consistency_node(state(CLEAN, campaign_status="needs_review"))
    assert update["research_status"] == "NeedsReview" and update["consistency_feedback"] == ""


def test_paper_issues_and_campaign_issues_are_reported_together_at_the_end():
    update = meta_consistency_node(state(DIRTY, consistency_rounds=MAX_META_ROUNDS, campaign_issues=["E9 is cited but not in the ledger"]))
    assert "must contain no digits" in update["consistency_feedback"] and update["consistency_feedback"].endswith("Campaign check: E9 is cited but not in the ledger")


def test_campaign_issues_never_trigger_a_rewrite():
    update = meta_consistency_node(state(CLEAN, campaign_issues=["E9 is cited but not in the ledger"], consistency_rounds=0))
    assert update["consistency_continue"] is False and "consistency_rounds" not in update


def test_the_gate_receives_the_paper_the_spec_the_analysis_the_ledger_and_the_sources(monkeypatch):
    seen = []
    monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: seen.append(args) or [])
    current = state(CLEAN)
    meta_consistency_node(current)
    paper, spec, analysis, ledger, sources = seen[0]
    assert paper == current["paper_markdown"] and spec == current["campaign_spec"]
    assert analysis == current["campaign_analysis"] and ledger == current["campaign_ledger"] and sources == SOURCES


def test_missing_state_fields_do_not_crash_the_node(monkeypatch):
    monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: [])
    assert meta_consistency_node({})["research_status"] == "Completed"


@pytest.mark.parametrize(("flag", "expected"), [(True, "meta_report_node"), (False, "end"), (None, "end")])
def test_the_route_follows_the_continue_flag(flag, expected):
    assert route_after_meta_consistency({"consistency_continue": flag}) == expected
    assert route_after_meta_consistency({}) == "end"


def test_the_gate_only_gets_the_source_paper_of_the_claims(monkeypatch):
    seen = []
    monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: seen.append(args[-1]) or [])
    other = {"title": "An unrelated paper", "abstract": "x", "url": ""}
    meta_consistency_node(state(CLEAN, literature_sources=[other, *SOURCES]))
    assert seen == [SOURCES]
    meta_consistency_node(state(CLEAN, literature_sources=[other], campaign_spec={**SPEC, "source": {}}))
    assert seen[1] == []
