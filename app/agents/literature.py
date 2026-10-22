import json
import logging
import time

import numpy as np
from openai import OpenAI

from app.config import OPENAI_API_KEY
from app.tools.arxiv import search_arxiv_phrases

MODEL = "gpt-4o"
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_QUERIES = 3
MAX_PHRASES = 4
MAX_PHRASE_WORDS = 4
CANDIDATES_PER_QUERY = 8
KEEP_PAPERS = 3
MIN_RELEVANCE = 0.35
ARXIV_DELAY_SECONDS = 3.0

logger = logging.getLogger("axiomforge")

SYSTEM_PROMPT = (
    "You turn a research question into arXiv keyword searches. "
    f"Write up to {MAX_QUERIES} different searches. "
    f"Each search is a list of 2 to {MAX_PHRASES} short English noun phrases of at most {MAX_PHRASE_WORDS} words, "
    "and a paper must contain every phrase of a search, so every extra phrase narrows it: use 2 phrases unless a third is essential. "
    "Name the models, the task and the data setting of the question. "
    "Do not write sentences and do not repeat the question. "
    'Return only JSON: {"queries": [["random forest", "xgboost", "imbalanced"], ["..."]]}.'
)


def run_literature_agent(query: str) -> list[str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    searches = _keyword_searches(client, query)
    for search in searches:
        logger.info("literature search=%s", search)
    candidates = _collect(searches)
    logger.info("literature candidates=%s", len(candidates))
    if not candidates:
        raise RuntimeError("arxiv returned no papers")
    scores = _relevance(client, query, candidates)
    ranked = sorted(zip(scores, candidates), key=lambda item: item[0], reverse=True)
    kept = [(score, paper) for score, paper in ranked if score >= MIN_RELEVANCE][:KEEP_PAPERS]
    for score, paper in ranked:
        logger.info("literature relevance=%.3f kept=%s title=%s", score, (score, paper) in kept, paper["title"])
    if not kept:
        raise RuntimeError("arxiv returned no relevant papers")
    return [f"{paper['title']}: {paper['abstract']}" for _, paper in kept]


def _keyword_searches(client: OpenAI, query: str) -> list[list[str]]:
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
    )
    content = response.choices[0].message.content or ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("literature agent returned invalid JSON") from exc
    items = payload.get("queries") if isinstance(payload, dict) else None
    searches: list[list[str]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, list):
            continue
        phrases = [
            " ".join(phrase.replace('"', " ").split())
            for phrase in item
            if isinstance(phrase, str)
        ]
        phrases = [phrase for phrase in phrases if phrase and len(phrase.split()) <= MAX_PHRASE_WORDS]
        if phrases and phrases[:MAX_PHRASES] not in searches:
            searches.append(phrases[:MAX_PHRASES])
    if not searches:
        raise RuntimeError("literature agent returned no usable search")
    return searches[:MAX_QUERIES]


def _collect(searches: list[list[str]]) -> list[dict[str, str]]:
    papers: dict[str, dict[str, str]] = {}
    for index, phrases in enumerate(searches):
        if index:
            time.sleep(ARXIV_DELAY_SECONDS)
        for paper in search_arxiv_phrases(phrases, limit=CANDIDATES_PER_QUERY):
            papers.setdefault(paper["title"].lower(), paper)
    return list(papers.values())


def _relevance(client: OpenAI, query: str, papers: list[dict[str, str]]) -> list[float]:
    texts = [query] + [f"{paper['title']}. {paper['abstract']}" for paper in papers]
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    vectors = np.asarray([item.embedding for item in response.data], dtype=float)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return [float(score) for score in vectors[1:] @ vectors[0]]
