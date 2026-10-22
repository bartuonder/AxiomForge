from xml.etree import ElementTree

import httpx

ATOM = "{http://www.w3.org/2005/Atom}"
API_URL = "https://export.arxiv.org/api/query"


def search_arxiv(query: str, limit: int = 3) -> list[dict[str, str]]:
    cleaned = " ".join(query.split())
    if not cleaned:
        raise RuntimeError("arxiv query is empty")
    papers = _fetch(f"all:{cleaned}", limit)
    if not papers:
        raise RuntimeError("arxiv returned no papers")
    return papers


def search_arxiv_phrases(phrases: list[str], limit: int = 8) -> list[dict[str, str]]:
    cleaned = [" ".join(phrase.replace('"', " ").split()) for phrase in phrases]
    cleaned = [phrase for phrase in cleaned if phrase]
    if not cleaned:
        raise RuntimeError("arxiv query is empty")
    return _fetch(" AND ".join(f'all:"{phrase}"' for phrase in cleaned), limit)


def _fetch(search_query: str, limit: int) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            API_URL,
            params={
                "search_query": search_query,
                "start": 0,
                "max_results": limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
            headers={"User-Agent": "AxiomForge/0.1"},
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
    except (httpx.HTTPError, ElementTree.ParseError) as exc:
        raise RuntimeError(f"arxiv request failed: {exc}") from exc
    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        title = _text(entry.find(f"{ATOM}title"))
        abstract = _text(entry.find(f"{ATOM}summary"))
        if not title:
            continue
        papers.append({"title": title, "abstract": abstract})
        if len(papers) == limit:
            break
    return papers


def _text(node: ElementTree.Element | None) -> str:
    if node is None or not node.text:
        return ""
    return " ".join(node.text.split())
