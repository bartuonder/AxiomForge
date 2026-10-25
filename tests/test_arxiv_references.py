import pytest

import app.tools.arxiv as arxiv


def entry(identifier, title, summary, authors=(), published="2022-07-18T17:58:43Z"):
    people = "".join(f"<author><name>{name}</name></author>" for name in authors)
    return f"<entry><id>{identifier}</id><published>{published}</published><title> {title} </title><summary> {summary} </summary>{people}</entry>"


def feed(*entries):
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">{"".join(entries)}</feed>'


class Response:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise arxiv.httpx.HTTPStatusError("bad", request=None, response=self)


class TestIds:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("https://arxiv.org/abs/2207.08815", ["2207.08815"]),
            ("https://arxiv.org/abs/2207.08815v3", ["2207.08815"]),
            ("http://arxiv.org/pdf/2207.08815v2.pdf", ["2207.08815"]),
            ("https://arxiv.org/pdf/2207.08815.pdf", ["2207.08815"]),
            ("https://arxiv.org/html/2207.08815v1", ["2207.08815"]),
            ("see arXiv:2207.08815 for details", ["2207.08815"]),
            ("see ARXIV: 2207.08815v2", ["2207.08815"]),
            ("arxiv.org/abs/cs/0112017v1", ["cs/0112017"]),
            ("arXiv:hep-th/9901001", ["hep-th/9901001"]),
            ("https://arxiv.org/abs/1706.03762 and https://arxiv.org/abs/2207.08815", ["1706.03762", "2207.08815"]),
            ("https://arxiv.org/abs/2207.08815 again https://arxiv.org/pdf/2207.08815v2", ["2207.08815"]),
            ("arXiv:12345.123456", []),
            ("version 2207.08815 without a marker", []),
            ("compare trees and nets", []),
            ("", []),
        ],
    )
    def test_ids_are_found_in_links_and_markers(self, text, expected):
        assert arxiv.arxiv_ids(text) == expected

    def test_the_number_of_references_is_capped(self):
        text = " ".join(f"arXiv:2207.{number:05d}" for number in range(1, 20))
        assert len(arxiv.arxiv_ids(text)) == arxiv.MAX_REFERENCES == 3


class TestFetch:
    def install(self, monkeypatch, text, calls=None):
        def get(url, **kwargs):
            if calls is not None:
                calls.append((url, kwargs))
            return Response(text)

        monkeypatch.setattr(arxiv.httpx, "get", get)

    def test_the_papers_carry_authors_year_and_the_canonical_link(self, monkeypatch):
        calls = []
        self.install(
            monkeypatch,
            feed(entry("http://arxiv.org/abs/2207.08815v2", "Why do trees win", "Trees beat nets", ["Léo Grinsztajn", "Edouard Oyallon", "Gaël Varoquaux"])),
            calls,
        )
        papers = arxiv.fetch_arxiv_papers(["2207.08815"])
        assert papers == [
            {
                "title": "Why do trees win",
                "abstract": "Trees beat nets",
                "url": "https://arxiv.org/abs/2207.08815",
                "authors": ["Léo Grinsztajn", "Edouard Oyallon", "Gaël Varoquaux"],
                "year": "2022",
                "arxiv_id": "2207.08815",
            }
        ]
        assert calls[0][0] == arxiv.API_URL and calls[0][1]["params"]["id_list"] == "2207.08815" and calls[0][1]["params"]["max_results"] == 1

    def test_several_ids_are_requested_together_and_keep_their_order(self, monkeypatch):
        calls = []
        self.install(
            monkeypatch,
            feed(entry("http://arxiv.org/abs/2207.08815v1", "Second", "b"), entry("http://arxiv.org/abs/1706.03762v7", "First", "a")),
            calls,
        )
        papers = arxiv.fetch_arxiv_papers(["1706.03762", "2207.08815"])
        assert [paper["arxiv_id"] for paper in papers] == ["1706.03762", "2207.08815"]
        assert calls[0][1]["params"]["id_list"] == "1706.03762,2207.08815" and calls[0][1]["params"]["max_results"] == 2

    def test_an_unknown_id_is_an_error_that_names_it(self, monkeypatch):
        self.install(monkeypatch, feed(entry("http://arxiv.org/api/errors#incorrect_id_format_for_1234", "Error", "incorrect id format")))
        with pytest.raises(RuntimeError, match="9999.99999"):
            arxiv.fetch_arxiv_papers(["9999.99999"])

    def test_a_missing_paper_among_found_ones_is_an_error(self, monkeypatch):
        self.install(monkeypatch, feed(entry("http://arxiv.org/abs/2207.08815v1", "Found", "a")))
        with pytest.raises(RuntimeError, match="1706.03762"):
            arxiv.fetch_arxiv_papers(["2207.08815", "1706.03762"])

    def test_no_ids_is_an_error(self):
        with pytest.raises(RuntimeError):
            arxiv.fetch_arxiv_papers([])

    def test_a_failed_request_is_a_runtime_error(self, monkeypatch):
        def get(*args, **kwargs):
            raise arxiv.httpx.ConnectError("down")

        monkeypatch.setattr(arxiv.httpx, "get", get)
        with pytest.raises(RuntimeError, match="arxiv request failed"):
            arxiv.fetch_arxiv_papers(["2207.08815"])

    def test_a_paper_without_a_publication_date_has_an_empty_year(self, monkeypatch):
        self.install(monkeypatch, feed("<entry><id>http://arxiv.org/abs/2207.08815v1</id><title>T</title><summary>S</summary></entry>"))
        paper = arxiv.fetch_arxiv_papers(["2207.08815"])[0]
        assert paper["year"] == "" and paper["authors"] == []


class TestCitation:
    def paper(self, *authors, year="2022", identifier="2207.08815"):
        return {"title": "T", "abstract": "a", "url": "u", "authors": list(authors), "year": year, "arxiv_id": identifier}

    def test_one_author(self):
        assert arxiv.citation(self.paper("Ada Lovelace")) == "Lovelace, arXiv:2207.08815 (2022)"

    def test_two_authors(self):
        assert arxiv.citation(self.paper("Ada Lovelace", "Alan Turing")) == "Lovelace and Turing, arXiv:2207.08815 (2022)"

    def test_three_authors(self):
        assert arxiv.citation(self.paper("Léo Grinsztajn", "Edouard Oyallon", "Gaël Varoquaux")) == "Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022)"

    def test_more_than_three_authors_are_abbreviated(self):
        assert arxiv.citation(self.paper("A One", "B Two", "C Three", "D Four")) == "One et al., arXiv:2207.08815 (2022)"

    def test_without_authors_nothing_is_claimed(self):
        assert arxiv.citation(self.paper()) == ""

    def test_without_a_year_only_the_identifier_follows(self):
        assert arxiv.citation(self.paper("Ada Lovelace", year="")) == "Lovelace, arXiv:2207.08815"

    def test_a_single_name_is_its_own_surname(self):
        assert arxiv.citation(self.paper("Plato")) == "Plato, arXiv:2207.08815 (2022)"

    def test_a_paper_from_a_search_has_no_citation(self):
        assert arxiv.citation({"title": "T", "abstract": "a", "url": "u"}) == ""


HTML = """
<html><body>
<h1>Title of the paper</h1>
<p>Opening paragraph of the abstract.</p>
<h2>1 Introduction</h2>
<p>We study trees and nets.</p>
<h2>5 Results</h2>
<p>Trees win on the benchmark.</p>
<h2>6 Conclusion</h2>
<p>Tree-based models remain state of the art on medium-sized data.</p>
<p>We hope this helps future work.</p>
<h2>References</h2>
<p>[1] A reference entry.</p>
</body></html>
"""


class TestPassages:
    def install(self, monkeypatch, pages):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            return Response(pages[url]) if url in pages else Response("", 404)

        monkeypatch.setattr(arxiv.httpx, "get", get)
        return calls

    def test_the_conclusion_paragraphs_are_returned(self, monkeypatch):
        self.install(monkeypatch, {"https://arxiv.org/html/2207.08815": HTML})
        text = arxiv.fetch_passages("2207.08815")
        assert text == "Tree-based models remain state of the art on medium-sized data. We hope this helps future work."

    def test_other_sections_are_left_out(self, monkeypatch):
        self.install(monkeypatch, {"https://arxiv.org/html/2207.08815": HTML})
        text = arxiv.fetch_passages("2207.08815")
        assert "Trees win on the benchmark" not in text and "reference entry" not in text and "We study" not in text

    def test_the_fallback_mirror_is_tried_when_the_first_is_missing(self, monkeypatch):
        calls = self.install(monkeypatch, {"https://ar5iv.labs.arxiv.org/html/2207.08815": HTML})
        assert arxiv.fetch_passages("2207.08815").startswith("Tree-based models")
        assert calls == ["https://arxiv.org/html/2207.08815", "https://ar5iv.labs.arxiv.org/html/2207.08815"]

    def test_no_page_gives_no_passages_and_no_error(self, monkeypatch):
        self.install(monkeypatch, {})
        assert arxiv.fetch_passages("2207.08815") == ""

    def test_a_network_error_gives_no_passages(self, monkeypatch):
        def get(*args, **kwargs):
            raise arxiv.httpx.ConnectError("down")

        monkeypatch.setattr(arxiv.httpx, "get", get)
        assert arxiv.fetch_passages("2207.08815") == ""

    def test_a_page_without_a_conclusion_gives_nothing(self, monkeypatch):
        self.install(monkeypatch, {"https://arxiv.org/html/2207.08815": "<html><body><h2>Intro</h2><p>Text.</p></body></html>"})
        assert arxiv.fetch_passages("2207.08815") == ""

    def test_the_text_is_capped(self, monkeypatch):
        body = "<h2>Conclusion</h2>" + "".join(f"<p>{'word ' * 100}</p>" for _ in range(20))
        self.install(monkeypatch, {"https://arxiv.org/html/2207.08815": f"<html><body>{body}</body></html>"})
        text = arxiv.fetch_passages("2207.08815")
        assert 0 < len(text) <= arxiv.MAX_PASSAGE_CHARS == 3000

    def test_nested_markup_and_entities_become_plain_text(self, monkeypatch):
        html = "<h2><span>6</span> Conclusions &amp; discussion</h2><p>Trees <em>beat</em> nets &gt; always.</p>"
        self.install(monkeypatch, {"https://arxiv.org/html/2207.08815": f"<html><body>{html}</body></html>"})
        assert arxiv.fetch_passages("2207.08815") == "Trees beat nets > always."

    def test_scripts_and_styles_are_ignored(self, monkeypatch):
        html = "<h2>Conclusion</h2><script>var x = 1;</script><style>p {color: red}</style><p>Real text.</p>"
        self.install(monkeypatch, {"https://arxiv.org/html/2207.08815": f"<html><body>{html}</body></html>"})
        assert arxiv.fetch_passages("2207.08815") == "Real text."

    def test_a_discussion_section_counts_too(self, monkeypatch):
        html = "<h2>7 Discussion</h2><p>Discussed here.</p><h2>Acknowledgements</h2><p>Thanks.</p>"
        self.install(monkeypatch, {"https://arxiv.org/html/2207.08815": f"<html><body>{html}</body></html>"})
        assert arxiv.fetch_passages("2207.08815") == "Discussed here."


class TestEdges:
    def test_a_too_long_new_style_number_is_not_an_identifier(self):
        assert arxiv.arxiv_ids("arXiv:2207.123456") == []
        assert arxiv.arxiv_ids("arxiv.org/abs/2207.123456") == []

    def test_a_too_long_old_style_number_is_not_an_identifier(self):
        assert arxiv.arxiv_ids("arxiv.org/abs/cs/01120171") == []

    def test_no_ids_never_reaches_the_network(self, monkeypatch):
        monkeypatch.setattr(arxiv.httpx, "get", lambda *args, **kwargs: pytest.fail("requested"))
        with pytest.raises(RuntimeError, match="no arxiv identifier"):
            arxiv.fetch_arxiv_papers([])

    def test_an_empty_author_name_is_dropped(self, monkeypatch):
        text = feed(entry("http://arxiv.org/abs/2207.08815v1", "T", "S", ["Ada Lovelace", "  "]))
        monkeypatch.setattr(arxiv.httpx, "get", lambda *args, **kwargs: Response(text))
        assert arxiv.fetch_arxiv_papers(["2207.08815"])[0]["authors"] == ["Ada Lovelace"]

    def pages(self, monkeypatch, mapping):
        monkeypatch.setattr(arxiv.httpx, "get", lambda url, **kwargs: Response(mapping[url]) if url in mapping else Response("", 404))

    def test_the_second_mirror_is_used_when_the_first_has_no_conclusion(self, monkeypatch):
        self.pages(monkeypatch, {"https://arxiv.org/html/2207.08815": "<h2>Intro</h2><p>Text.</p>", "https://ar5iv.labs.arxiv.org/html/2207.08815": HTML})
        assert arxiv.fetch_passages("2207.08815").startswith("Tree-based models")

    def test_a_block_inside_a_heading_does_not_end_it(self, monkeypatch):
        self.pages(monkeypatch, {"https://arxiv.org/html/2207.08815": "<h2>Conclusion <p>x</p> end</h2><p>Body.</p>"})
        assert arxiv.fetch_passages("2207.08815") == "Body."

    def test_a_script_inside_a_paragraph_is_ignored(self, monkeypatch):
        self.pages(monkeypatch, {"https://arxiv.org/html/2207.08815": "<h2>Conclusion</h2><p>Real <script>var hidden = 1;</script>text.</p>"})
        assert arxiv.fetch_passages("2207.08815") == "Real text."

    def test_a_heading_inside_a_paragraph_does_not_end_it(self, monkeypatch):
        self.pages(monkeypatch, {"https://arxiv.org/html/2207.08815": "<h2>Conclusion</h2><p>Intro text <h3>inner</h3> continues</p>"})
        assert arxiv.fetch_passages("2207.08815") == "Intro text inner continues"

    def test_empty_paragraphs_add_nothing(self, monkeypatch):
        self.pages(monkeypatch, {"https://arxiv.org/html/2207.08815": "<h2>Conclusion</h2><p>A.</p><p>  </p><p>B.</p>"})
        assert arxiv.fetch_passages("2207.08815") == "A. B."
