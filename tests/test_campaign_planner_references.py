import json

import pytest

import app.agents.campaign_planner as planner
from app.agents.campaign_planner import run_campaign_planner
from app.campaign.spec import CampaignSpecError, validate_campaign

pytestmark = pytest.mark.usefixtures("approve_judge")

ABSTRACT = "We show that tree-based models remain state-of-the-art on medium-sized data."
PASSAGES = "Our conclusion is that gradient boosted trees clearly beat neural networks on every medium-sized benchmark we studied."
CITATION = "Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022)"
SOURCE = {"title": "Why do trees win", "abstract": ABSTRACT, "url": "https://arxiv.org/abs/2207.08815", "citation": CITATION, "passages": PASSAGES}
QUERY = "Replicate arXiv:2207.08815 on tabular data."
QUOTE_ABSTRACT = "tree-based models remain state-of-the-art on medium-sized data"
QUOTE_PASSAGE = "gradient boosted trees clearly beat neural networks on every medium-sized benchmark"
QUOTE_QUERY = "Random forests beat the MLP on every dataset in my experience."


def claim(quote=QUOTE_ABSTRACT, **changes):
    base = {"statement": "Trees beat nets", "metrics": ["roc_auc"], "subject": ["RandomForest"], "other": ["MLP"], "source_quote": quote}
    return {**base, **changes}


def candidate(*claims, index=1, title="T"):
    return {"title": title, "source_index": index, "pool": "benchmark", "claims": list(claims) or [claim()]}


def answer(*candidates):
    return json.dumps({"unsupported": "", "candidates": list(candidates)})


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


def plan(llm, *candidates, query=QUERY, sources=(SOURCE,)):
    replies, _ = llm
    replies.append(answer(*candidates))
    return run_campaign_planner(query, list(sources))


def test_the_prompt_shows_the_conclusion_of_the_paper(llm):
    plan(llm, candidate())
    prompt = llm[1][0]
    assert f"[1] {SOURCE['title']}: {ABSTRACT}\nConclusion: {PASSAGES}" in prompt


def test_a_source_without_passages_is_listed_as_before(llm):
    plan(llm, candidate(), sources=({"title": "Why do trees win", "abstract": ABSTRACT, "url": ""},))
    prompt = llm[1][0]
    assert f"[1] Why do trees win: {ABSTRACT}" in prompt and "Conclusion:" not in prompt


def test_a_quote_from_the_conclusion_is_accepted(llm):
    result = plan(llm, candidate(claim(QUOTE_PASSAGE)))
    assert result[0]["evidence"] == [{"claim": "C1", "quote": QUOTE_PASSAGE, "source": SOURCE["title"]}]


def test_a_quote_that_is_in_neither_text_is_still_rejected(llm):
    replies, _ = llm
    bad = candidate(claim("Trees beat nets by a very large margin on all data"))
    replies.append(answer(bad, bad, bad))
    replies.append(answer(candidate(claim(QUOTE_ABSTRACT))))
    result = run_campaign_planner(QUERY, [SOURCE])
    assert len(result) == 1 and result[0]["evidence"][0]["quote"] == QUOTE_ABSTRACT


def test_the_citation_of_the_paper_reaches_the_specification(llm):
    spec = plan(llm, candidate())[0]["spec"]
    assert spec["source"]["citation"] == CITATION and spec["source"]["title"] == SOURCE["title"]


def test_a_source_without_a_citation_adds_none(llm):
    spec = plan(llm, candidate(), sources=({"title": "Why do trees win", "abstract": ABSTRACT, "url": ""},))[0]["spec"]
    assert "citation" not in spec["source"]


def test_a_claim_from_the_paper_keeps_its_quote(llm):
    spec = plan(llm, candidate(claim(QUOTE_PASSAGE)))[0]["spec"]
    assert spec["claims"][0]["quote"] == QUOTE_PASSAGE


def test_the_stripped_quote_is_what_is_kept(llm):
    spec = plan(llm, candidate(claim(f'  "{QUOTE_ABSTRACT}."  ')))[0]["spec"]
    assert spec["claims"][0]["quote"] == QUOTE_ABSTRACT


def test_a_claim_from_the_query_keeps_no_quote_and_no_source(llm):
    spec = plan(llm, candidate(claim(QUOTE_QUERY), index=0), query=QUERY + " " + QUOTE_QUERY)[0]["spec"]
    assert "quote" not in spec["claims"][0] and "title" not in spec["source"] and "citation" not in spec["source"]


def test_a_query_quote_under_a_source_index_drops_the_source(llm):
    spec = plan(llm, candidate(claim(QUOTE_QUERY), index=1), query=QUERY + " " + QUOTE_QUERY)[0]["spec"]
    assert "quote" not in spec["claims"][0] and "citation" not in spec["source"] and "title" not in spec["source"]


def test_the_system_prompt_allows_the_conclusion_as_a_quote_source():
    assert "conclusion" in planner.SYSTEM_PROMPT


RAW = {
    "title": "T",
    "models": ["RandomForest", "MLP"],
    "datasets": ["tb_credit", "tb_electricity"],
    "claims": [{"statement": "Trees beat nets", "metric": "roc_auc", "subject": ["RandomForest"], "other": ["MLP"]}],
}


def test_a_claim_quote_is_kept_by_the_specification():
    raw = {**RAW, "claims": [{**RAW["claims"][0], "quote": "  Trees  beat nets. "}]}
    assert validate_campaign(raw)["claims"][0]["quote"] == "Trees beat nets."


def test_a_claim_without_a_quote_has_no_quote_field():
    assert "quote" not in validate_campaign(RAW)["claims"][0]


def test_an_overlong_quote_is_refused():
    raw = {**RAW, "claims": [{**RAW["claims"][0], "quote": "x" * 501}]}
    with pytest.raises(CampaignSpecError, match="quote"):
        validate_campaign(raw)


def test_a_blank_quote_is_the_same_as_no_quote():
    raw = {**RAW, "claims": [{**RAW["claims"][0], "quote": "   "}]}
    assert "quote" not in validate_campaign(raw)["claims"][0]
