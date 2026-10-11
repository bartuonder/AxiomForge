from xml.etree import ElementTree

import httpx

ATOM = "{http://www.w3.org/2005/Atom}"
API_URL = "https://export.arxiv.org/api/query"


def search_arxiv(query: str, limit: int = 3) -> list[dict[str, str]]:
    cleaned = " ".join(query.split())
    if not cleaned:
        raise RuntimeError("arxiv query is empty")
    try:
        response = httpx.get(
            API_URL,
            params={
                "search_query": f"all:{cleaned}",
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
    if not papers:
        raise RuntimeError("arxiv returned no papers")
    return papers


def _text(node: ElementTree.Element | None) -> str:
    if node is None or not node.text:
        return ""
    return " ".join(node.text.split())
