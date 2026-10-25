import re
from html.parser import HTMLParser
from xml.etree import ElementTree

import httpx

ATOM = "{http://www.w3.org/2005/Atom}"
API_URL = "https://export.arxiv.org/api/query"
HTML_MIRRORS = ("https://arxiv.org/html/{}", "https://ar5iv.labs.arxiv.org/html/{}")
MAX_REFERENCES = 3
MAX_PASSAGE_CHARS = 3000
MAX_AUTHORS_LISTED = 3

_ID = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:\s*)(\d{4}\.\d{4,5}(?!\d)|[a-z][a-z\-]*(?:\.[a-z]{2})?/\d{7}(?!\d))(?:v\d+)?",
    re.IGNORECASE,
)
_CLOSING_SECTION = re.compile(r"\b(conclusions?|discussion|summary)\b", re.IGNORECASE)
_BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}
_SKIPPED = {"script", "style"}


def arxiv_ids(text: str) -> list[str]:
    found = list(dict.fromkeys(match.group(1) for match in _ID.finditer(text or "")))
    return found[:MAX_REFERENCES]


def search_arxiv_phrases(phrases: list[str], limit: int = 8) -> list[dict[str, str]]:
    cleaned = [" ".join(phrase.replace('"', " ").split()) for phrase in phrases]
    cleaned = [phrase for phrase in cleaned if phrase]
    if not cleaned:
        raise RuntimeError("arxiv query is empty")
    return _fetch(" AND ".join(f'all:"{phrase}"' for phrase in cleaned), limit)


def fetch_arxiv_papers(ids: list[str]) -> list[dict[str, object]]:
    if not ids:
        raise RuntimeError("no arxiv identifier was given")
    root = _request({"id_list": ",".join(ids), "start": 0, "max_results": len(ids)})
    found: dict[str, dict[str, object]] = {}
    for entry in root.findall(f"{ATOM}entry"):
        url = _abs_url(_text(entry.find(f"{ATOM}id")))
        title = _text(entry.find(f"{ATOM}title"))
        if not url or not title:
            continue
        identifier = url.removeprefix("https://arxiv.org/abs/")
        authors = [_text(person.find(f"{ATOM}name")) for person in entry.findall(f"{ATOM}author")]
        found[identifier] = {
            "title": title,
            "abstract": _text(entry.find(f"{ATOM}summary")),
            "url": url,
            "authors": [name for name in authors if name],
            "year": _text(entry.find(f"{ATOM}published"))[:4],
            "arxiv_id": identifier,
        }
    missing = [identifier for identifier in ids if identifier not in found]
    if missing:
        raise RuntimeError("arxiv paper not found: " + ", ".join(missing))
    return [found[identifier] for identifier in ids]


def citation(paper: dict[str, object]) -> str:
    authors = [str(name) for name in paper.get("authors") or [] if str(name).strip()]
    if not authors:
        return ""
    surnames = [name.split()[-1] for name in authors]
    if len(surnames) > MAX_AUTHORS_LISTED:
        names = f"{surnames[0]} et al."
    elif len(surnames) == 1:
        names = surnames[0]
    else:
        names = ", ".join(surnames[:-1]) + f" and {surnames[-1]}"
    year = str(paper.get("year") or "")
    return f"{names}, arXiv:{paper['arxiv_id']}" + (f" ({year})" if year else "")


def fetch_passages(identifier: str) -> str:
    for template in HTML_MIRRORS:
        try:
            response = httpx.get(template.format(identifier), headers={"User-Agent": "AxiomForge/0.1"}, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        passages = _closing_text(response.text)
        if passages:
            return passages
    return ""


class _Blocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._open: str | None = None
        self._parts: list[str] = []
        self._skipped = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED:
            self._skipped += 1
        elif tag in _BLOCKS and self._open is None:
            self._open, self._parts = tag, []

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED:
            self._skipped = max(0, self._skipped - 1)
        elif tag == self._open:
            self.blocks.append(("p" if tag == "p" else "h", " ".join("".join(self._parts).split())))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None and not self._skipped:
            self._parts.append(data)


def _closing_text(page: str) -> str:
    parser = _Blocks()
    parser.feed(page)
    parser.close()
    inside = False
    paragraphs: list[str] = []
    for kind, text in parser.blocks:
        if kind == "h":
            inside = bool(_CLOSING_SECTION.search(text))
        elif inside and text:
            paragraphs.append(text)
    return " ".join(paragraphs)[:MAX_PASSAGE_CHARS].rstrip()


def _fetch(search_query: str, limit: int) -> list[dict[str, str]]:
    root = _request({"search_query": search_query, "start": 0, "max_results": limit, "sortBy": "relevance", "sortOrder": "descending"})
    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        title = _text(entry.find(f"{ATOM}title"))
        abstract = _text(entry.find(f"{ATOM}summary"))
        if not title:
            continue
        papers.append({"title": title, "abstract": abstract, "url": _abs_url(_text(entry.find(f"{ATOM}id")))})
        if len(papers) == limit:
            break
    return papers


def _request(params: dict[str, object]) -> ElementTree.Element:
    try:
        response = httpx.get(
            API_URL,
            params=params,
            headers={"User-Agent": "AxiomForge/0.1"},
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        return ElementTree.fromstring(response.text)
    except (httpx.HTTPError, ElementTree.ParseError) as exc:
        raise RuntimeError(f"arxiv request failed: {exc}") from exc


def _abs_url(identifier: str) -> str:
    match = re.search(r"arxiv\.org/abs/(.+?)(?:v\d+)?$", identifier)
    return f"https://arxiv.org/abs/{match.group(1)}" if match else ""


def _text(node: ElementTree.Element | None) -> str:
    if node is None or not node.text:
        return ""
    return " ".join(node.text.split())
