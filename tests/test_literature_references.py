import pytest

import app.agents.literature as literature

PAPER = {
    "title": "Why do trees win",
    "abstract": "Trees beat nets.",
    "url": "https://arxiv.org/abs/2207.08815",
    "authors": ["Léo Grinsztajn", "Edouard Oyallon", "Gaël Varoquaux"],
    "year": "2022",
    "arxiv_id": "2207.08815",
}


@pytest.fixture
def arxiv(monkeypatch):
    calls = {"fetch": [], "passages": []}

    def fetch(ids):
        calls["fetch"].append(list(ids))
        return [{**PAPER, "arxiv_id": identifier, "url": f"https://arxiv.org/abs/{identifier}"} for identifier in ids]

    def passages(identifier):
        calls["passages"].append(identifier)
        return f"Conclusion text of {identifier}."

    monkeypatch.setattr(literature, "fetch_arxiv_papers", fetch)
    monkeypatch.setattr(literature, "fetch_passages", passages)
    monkeypatch.setattr(literature, "OpenAI", lambda **kwargs: pytest.fail("the model must not be called for a referenced paper"))
    monkeypatch.setattr(literature, "OPENAI_API_KEY", "")
    return calls


def test_a_referenced_paper_is_used_as_the_only_source_without_any_model_call(arxiv):
    sources = literature.run_literature_search("Replicate the claim of https://arxiv.org/abs/2207.08815 on tabular data")
    assert sources == [
        {
            "title": "Why do trees win",
            "abstract": "Trees beat nets.",
            "url": "https://arxiv.org/abs/2207.08815",
            "citation": "Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022)",
            "passages": "Conclusion text of 2207.08815.",
        }
    ]
    assert arxiv["fetch"] == [["2207.08815"]] and arxiv["passages"] == ["2207.08815"]


def test_several_references_keep_their_order(arxiv):
    sources = literature.run_literature_search("arXiv:1706.03762 and arxiv.org/abs/2207.08815v2")
    assert [source["url"] for source in sources] == ["https://arxiv.org/abs/1706.03762", "https://arxiv.org/abs/2207.08815"]
    assert arxiv["fetch"] == [["1706.03762", "2207.08815"]]
    assert arxiv["passages"] == ["1706.03762", "2207.08815"]


def test_a_paper_without_passages_has_an_empty_passage_text(arxiv, monkeypatch):
    monkeypatch.setattr(literature, "fetch_passages", lambda identifier: "")
    assert literature.run_literature_search("arXiv:2207.08815")[0]["passages"] == ""


def test_an_unknown_reference_stops_the_search(monkeypatch):
    def fetch(ids):
        raise RuntimeError("arxiv paper not found: 9999.99999")

    monkeypatch.setattr(literature, "fetch_arxiv_papers", fetch)
    with pytest.raises(RuntimeError, match="9999.99999"):
        literature.run_literature_search("arXiv:9999.99999")


def test_the_context_text_adds_the_passages(arxiv):
    sources = literature.run_literature_search("arXiv:2207.08815")
    assert literature.format_papers(sources) == ["Why do trees win: Trees beat nets. Conclusion: Conclusion text of 2207.08815."]


def test_the_context_text_is_unchanged_without_passages():
    assert literature.format_papers([{"title": "T", "abstract": "A", "url": "u"}]) == ["T: A"]
    assert literature.format_papers([{"title": "T", "abstract": "A", "passages": ""}]) == ["T: A"]


def test_a_query_without_a_reference_still_needs_the_key(monkeypatch):
    monkeypatch.setattr(literature, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        literature.run_literature_search("Compare RandomForest and MLP on tabular data")
