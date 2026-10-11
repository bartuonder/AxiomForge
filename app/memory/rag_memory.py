from pathlib import Path

import psycopg
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from app.config import DATABASE_URL, OPENAI_API_KEY

COLLECTION_NAME = "experiment_memory"
EMBEDDING_MODEL = "text-embedding-3-small"
EXTENSION_SQL = Path(__file__).with_name("enable_pgvector.sql")


def enable_pgvector() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing")
    statement = EXTENSION_SQL.read_text(encoding="utf-8")
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(statement)


def _vector_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    return url


def _store() -> PGVector:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    enable_pgvector()
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
    return PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=_vector_url(DATABASE_URL),
        use_jsonb=True,
        create_extension=True,
        async_mode=False,
    )


def _summary(hypothesis: str, code: str, metric: str, error_log: str, is_success: bool) -> str:
    status = "success" if is_success else "failure"
    return (
        f"Status: {status}\n"
        f"Hypothesis: {hypothesis}\n"
        f"Metric: {metric}\n"
        f"Error log: {error_log}\n"
        f"Code:\n{code}"
    )


def save_experiment(
    hypothesis: str,
    code: str,
    metric: str,
    error_log: str,
    is_success: bool,
) -> str:
    document_id = _store().add_texts(
        [_summary(hypothesis, code, metric, error_log, is_success)],
        metadatas=[
            {
                "hypothesis": hypothesis,
                "code": code,
                "metric": metric,
                "error_log": error_log,
                "is_success": is_success,
            }
        ],
    )[0]
    return document_id


def search_past_experiments(query: str, k: int = 3) -> list[dict]:
    documents = _store().similarity_search(query, k=k)
    results = []
    for document in documents:
        metadata = document.metadata or {}
        results.append(
            {
                "summary": document.page_content,
                "hypothesis": metadata.get("hypothesis", ""),
                "code": metadata.get("code", ""),
                "metric": metadata.get("metric", ""),
                "error_log": metadata.get("error_log", ""),
                "is_success": metadata.get("is_success"),
            }
        )
    return results
