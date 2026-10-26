import json

import pytest

import app.agents.campaign_planner as planner
from app.agents.campaign_planner import CampaignUnsupported, run_campaign_planner

pytestmark = pytest.mark.usefixtures("approve_judge")

ABSTRACT = "We show that tree-based models remain state-of-the-art on medium-sized data."
SOURCE = {"title": "Why do trees win", "abstract": ABSTRACT, "url": "https://arxiv.org/abs/2207.08815"}
QUOTE = "tree-based models remain state-of-the-art on medium-sized data"
QUERY = "Replicate the central claim of arXiv:2207.08815 on tabular data."
PAST = [
    {
        "title": "Earlier run",
        "spec": {"claims": [{"statement": "Trees beat nets", "subject": ["RandomForest"], "other": ["MLP"], "metrics": ["roc_auc", "pr_auc", "f1"]}]},
        "verdicts": "C1 replicated",
    }
]


def good():
    claim = {"statement": "Trees beat nets", "metrics": ["roc_auc", "pr_auc", "f1"], "subject": ["RandomForest"], "other": ["MLP"], "source_quote": QUOTE}
    return json.dumps({"unsupported": "", "candidates": [{"title": "Trees against nets", "source_index": 1, "pool": "benchmark", "claims": [claim]}]})


def refusal(reason="no new claims"):
    return json.dumps({"unsupported": reason, "candidates": []})


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")


@pytest.fixture
def llm(monkeypatch):
    replies, prompts = [], []

    def complete(user):
        prompts.append(user)
        return replies.pop(0)

    monkeypatch.setattr(planner, "_complete", complete)
    return replies, prompts


class TestPrompt:
    def test_the_past_is_given_for_information_and_never_a_reason_to_refuse(self, llm):
        replies, prompts = llm
        replies.append(good())
        run_campaign_planner(QUERY, [SOURCE], PAST)
        assert "Campaigns that were already run on similar questions, for your information." in prompts[0]
        assert "The system marks repeated claims itself" in prompts[0]
        assert "never answer unsupported because a claim was run before. Prefer new variations when the sources allow:" in prompts[0]
        assert "- Earlier run: Trees beat nets (C1 replicated)" in prompts[0]

    def test_no_past_no_section(self, llm):
        replies, prompts = llm
        replies.append(good())
        run_campaign_planner(QUERY, [SOURCE], None)
        assert "already run" not in prompts[0]


class TestFallback:
    def test_a_refusal_with_a_past_is_asked_again_without_the_past(self, llm):
        replies, prompts = llm
        replies.extend([refusal(), good()])
        result = run_campaign_planner(QUERY, [SOURCE], PAST)
        assert len(result) == 1 and result[0]["spec"]["title"] == "Trees against nets"
        assert "already run" in prompts[0] and "already run" not in prompts[1]

    def test_the_repeat_marks_still_use_the_past(self, llm):
        replies, _ = llm
        replies.extend([refusal(), good()])
        assert run_campaign_planner(QUERY, [SOURCE], PAST)[0]["repeats"] == ["Earlier run"]

    def test_a_refusal_without_a_past_is_final(self, llm):
        replies, prompts = llm
        replies.append(refusal("not about models"))
        with pytest.raises(CampaignUnsupported, match="not about models"):
            run_campaign_planner(QUERY, [SOURCE], None)
        assert len(prompts) == 1

    def test_an_empty_past_is_the_same_as_none(self, llm):
        replies, prompts = llm
        replies.append(refusal())
        with pytest.raises(CampaignUnsupported):
            run_campaign_planner(QUERY, [SOURCE], [])
        assert len(prompts) == 1

    def test_a_second_refusal_is_final_and_keeps_its_reason(self, llm):
        replies, prompts = llm
        replies.extend([refusal("first reason"), refusal("second reason")])
        with pytest.raises(CampaignUnsupported, match="second reason"):
            run_campaign_planner(QUERY, [SOURCE], PAST)
        assert len(prompts) == 2

    def test_a_good_first_answer_is_not_repeated(self, llm):
        replies, prompts = llm
        replies.append(good())
        run_campaign_planner(QUERY, [SOURCE], PAST)
        assert len(prompts) == 1

    def test_other_failures_are_not_retried(self, llm):
        replies, prompts = llm
        replies.extend(["not json"])
        with pytest.raises(RuntimeError, match="invalid JSON"):
            run_campaign_planner(QUERY, [SOURCE], PAST)
        assert len(prompts) == 1

    def test_the_fallback_keeps_the_filled_variants_switch(self, llm, monkeypatch):
        monkeypatch.setattr(planner, "FILL_VARIANTS", True)
        replies, _ = llm
        replies.extend([refusal(), good()])
        assert len(run_campaign_planner(QUERY, [SOURCE], PAST)) == 3
