import pytest

import app.agents.literature as literature
import app.tools.arxiv as arxiv


def feed(*entries):
    body = "".join(
        f"<entry><id>{identifier}</id><title>  {title}  </title><summary> {summary} </summary></entry>"
        for identifier, title, summary in entries
    )
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">{body}</feed>'


class Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


@pytest.fixture
def fetch(monkeypatch):
    def install(text):
        monkeypatch.setattr(arxiv.httpx, "get", lambda *args, **kwargs: Response(text))

    return install


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("http://arxiv.org/abs/2207.08815v2", "https://arxiv.org/abs/2207.08815"),
        ("http://arxiv.org/abs/2207.08815", "https://arxiv.org/abs/2207.08815"),
        ("https://arxiv.org/abs/2207.08815v10", "https://arxiv.org/abs/2207.08815"),
        ("http://arxiv.org/abs/cs/0112017v1", "https://arxiv.org/abs/cs/0112017"),
        ("something else", ""),
        ("", ""),
    ],
)
def test_the_entry_id_becomes_a_canonical_abstract_link(identifier, expected):
    assert arxiv._abs_url(identifier) == expected


def test_papers_carry_title_abstract_and_link(fetch):
    fetch(feed(("http://arxiv.org/abs/2207.08815v2", "Why do trees win", "Trees beat nets"), ("http://arxiv.org/abs/1111.22222v1", "Second", "Other")))
    papers = arxiv.search_arxiv_phrases(["tabular data"], limit=5)
    assert papers == [
        {"title": "Why do trees win", "abstract": "Trees beat nets", "url": "https://arxiv.org/abs/2207.08815"},
        {"title": "Second", "abstract": "Other", "url": "https://arxiv.org/abs/1111.22222"},
    ]


def test_an_entry_without_a_title_is_skipped(fetch):
    fetch(feed(("http://arxiv.org/abs/1.1", "", "x"), ("http://arxiv.org/abs/2.2", "Kept", "y")))
    assert [paper["title"] for paper in arxiv.search_arxiv_phrases(["x"])] == ["Kept"]


def test_the_limit_is_respected(fetch):
    fetch(feed(*[(f"http://arxiv.org/abs/{n}.{n}", f"T{n}", "a") for n in range(1, 5)]))
    assert len(arxiv.search_arxiv_phrases(["x"], limit=2)) == 2


def test_the_literature_search_keeps_the_link_and_the_agent_keeps_its_text_format(monkeypatch):
    papers = [
        {"title": "Why do trees win", "abstract": "Trees beat nets.", "url": "https://arxiv.org/abs/2207.08815"},
        {"title": "No link here", "abstract": "Old record."},
    ]
    monkeypatch.setattr(literature, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(literature, "OpenAI", lambda api_key: object())
    monkeypatch.setattr(literature, "_topics", lambda client, query: ["tabular data"])
    monkeypatch.setattr(literature, "search_arxiv_phrases", lambda phrases, limit: papers)
    monkeypatch.setattr(literature, "_relevance", lambda client, query, found: [0.9] * len(found))
    monkeypatch.setattr(literature.time, "sleep", lambda seconds: None)
    found = literature.run_literature_search("Compare RandomForest and MLP on tabular data")
    assert found == [
        {"title": "Why do trees win", "abstract": "Trees beat nets.", "url": "https://arxiv.org/abs/2207.08815"},
        {"title": "No link here", "abstract": "Old record.", "url": ""},
    ]
    assert literature.run_literature_agent("Compare RandomForest and MLP on tabular data") == [
        "Why do trees win: Trees beat nets.",
        "No link here: Old record.",
    ]
