import logging

import psycopg

from app.config import DATABASE_URL

logger = logging.getLogger("axiomforge")

MAX_MESSAGE_LENGTH = 2000
CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS research_errors ("
    "thread_id TEXT PRIMARY KEY, "
    "message TEXT NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
)
UPSERT = (
    "INSERT INTO research_errors (thread_id, message) VALUES (%s, %s) "
    "ON CONFLICT (thread_id) DO UPDATE SET message = EXCLUDED.message, created_at = now()"
)
SELECT = "SELECT message FROM research_errors WHERE thread_id = %s"

_memory: dict[str, str] = {}
_table_ready = False


def _connect() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing")
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _ensure_table(connection: psycopg.Connection) -> None:
    global _table_ready
    if not _table_ready:
        connection.execute(CREATE_TABLE)
        _table_ready = True


def describe_error(exc: BaseException) -> str:
    return (str(exc) or type(exc).__name__)[:MAX_MESSAGE_LENGTH]


def record_error(thread_id: str, message: str) -> None:
    text = message[:MAX_MESSAGE_LENGTH]
    _memory[thread_id] = text
    try:
        with _connect() as connection:
            _ensure_table(connection)
            connection.execute(UPSERT, (thread_id, text))
    except Exception:
        logger.exception("could not persist research error thread_id=%s", thread_id)


def read_error(thread_id: str) -> str:
    try:
        with _connect() as connection:
            _ensure_table(connection)
            row = connection.execute(SELECT, (thread_id,)).fetchone()
    except Exception:
        logger.exception("could not read research error thread_id=%s", thread_id)
        return _memory.get(thread_id, "")
    if row is None:
        return _memory.get(thread_id, "")
    return str(row[0])
