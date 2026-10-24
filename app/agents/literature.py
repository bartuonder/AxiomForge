import json
import logging
import re
import time

import numpy as np
from openai import OpenAI

from app.agents.experiment import requested_models
from app.agents.spec import MODEL_PARAMS
from app.config import OPENAI_API_KEY
from app.tools.arxiv import search_arxiv_phrases

MODEL = "gpt-4o"
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_TOPICS = 2
MAX_TOPIC_WORDS = 3
MAX_SEARCHES = 5
ENOUGH_CANDIDATES = 12
CANDIDATES_PER_QUERY = 8
KEEP_PAPERS = 3
MIN_RELEVANCE = 0.35
ARXIV_DELAY_SECONDS = 3.0

logger = logging.getLogger("axiomforge")

MODEL_SEARCH_NAMES = {
    "LinearSVC": "linear svm",
    "SVM": "support vector machine",
    "RandomForest": "random forest",
    "LogisticRegression": "logistic regression",
    "DecisionTree": "decision tree",
    "GradientBoosting": "gradient boosting",
    "HistGradientBoosting": "gradient boosting",
    "XGBoost": "xgboost",
    "LightGBM": "lightgbm",
    "CatBoost": "catboost",
    "KNN": "k nearest neighbors",
    "GaussianNB": "naive bayes",
    "MLP": "multilayer perceptron",
    "AdaBoost": "adaboost",
    "ExtraTrees": "extra trees",
    "QDA": "quadratic discriminant analysis",
    "LDA": "linear discriminant analysis",
}

GENERIC_TAILS = frozenset({"prediction", "classification", "analysis", "task", "problem", "dataset", "detection"})

SYSTEM_PROMPT = (
    "From a research question, extract only its application domain or task. "
    f"Return up to {MAX_TOPICS} short English noun phrases of 1 to {MAX_TOPIC_WORDS} words, "
    "such as 'customer churn' or 'credit default'. "
    "Never include model or algorithm names, hyperparameters, numbers, settings or instructions, "
    "and do not use generic phrases such as 'machine learning' or 'classification'. "
    'Return only JSON: {"topics": ["customer churn", "churn prediction"]}.'
)


def _blocked_words() -> set[str]:
    words = {name.lower() for names in MODEL_PARAMS.values() for name in names}
    words |= {key.lower() for key in MODEL_SEARCH_NAMES}
    words |= {"hyperparameter", "hyperparameters", "tuned", "tuning", "settings", "parameter", "parameters"}
    return words


def clean_topics(raw: object) -> list[str]:
    blocked = _blocked_words()
    phrases = {phrase for phrase in MODEL_SEARCH_NAMES.values()}
    topics: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, str):
            continue
        phrase = " ".join(re.sub(r"[^a-z0-9_= ]+", " ", item.lower()).split())
        words = phrase.split()
        if len(words) > MAX_TOPIC_WORDS and words[-1] in GENERIC_TAILS:
            words = words[:-1]
            phrase = " ".join(words)
        if not words or len(words) > MAX_TOPIC_WORDS:
            continue
        if any(character in phrase for character in "=_") or any(character.isdigit() for character in phrase):
            continue
        if any(word in blocked for word in words) or any(model in phrase for model in phrases):
            continue
        if phrase in {"machine learning", "classification", "prediction"}:
            continue
        if phrase not in topics:
            topics.append(phrase)
    return topics[:MAX_TOPICS]


def search_plan(model_keys: list[str], topics: list[str]) -> list[list[str]]:
    names: list[str] = []
    for key in model_keys:
        name = MODEL_SEARCH_NAMES.get(key, key.lower())
        if name not in names:
            names.append(name)
    plan: list[list[str]] = []
    if topics:
        for name in names[:2]:
            plan.append([topics[0], name])
        plan.append([topics[0], "machine learning"])
    if len(names) >= 2:
        plan.append(names[:2])
    elif names and not topics:
        plan.append([names[0], "classification"])
    for topic in topics:
        plan.append([topic])
    if not plan and names:
        plan.append([names[0], "classification"])
    unique: list[list[str]] = []
    for item in plan:
        if item not in unique:
            unique.append(item)
    return unique[:MAX_SEARCHES]


def format_papers(papers: list[dict[str, str]]) -> list[str]:
    return [f"{paper['title']}: {paper['abstract']}" for paper in papers]


def run_literature_agent(query: str) -> list[str]:
    return format_papers(run_literature_search(query))


def run_literature_search(query: str) -> list[dict[str, str]]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    topics = _topics(client, query)
    model_keys = [str(item["key"]) for item in requested_models(query)]
    searches = search_plan(model_keys, topics)
    logger.info("literature topics=%s models=%s", topics, model_keys)
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
    return [{"title": paper["title"], "abstract": paper["abstract"], "url": paper.get("url", "")} for _, paper in kept]


def _topics(client: OpenAI, query: str) -> list[str]:
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
    return clean_topics(payload.get("topics") if isinstance(payload, dict) else None)


def _collect(searches: list[list[str]]) -> list[dict[str, str]]:
    papers: dict[str, dict[str, str]] = {}
    for index, phrases in enumerate(searches):
        if len(papers) >= ENOUGH_CANDIDATES:
            break
        if index:
            time.sleep(ARXIV_DELAY_SECONDS)
        logger.info("literature search=%s", phrases)
        for paper in search_arxiv_phrases(phrases, limit=CANDIDATES_PER_QUERY):
            papers.setdefault(paper["title"].lower(), paper)
    return list(papers.values())


def _relevance(client: OpenAI, query: str, papers: list[dict[str, str]]) -> list[float]:
    texts = [query] + [f"{paper['title']}. {paper['abstract']}" for paper in papers]
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    vectors = np.asarray([item.embedding for item in response.data], dtype=float)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return [float(score) for score in vectors[1:] @ vectors[0]]
