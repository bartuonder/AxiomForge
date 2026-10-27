import argparse
import json
import sys
from typing import Any

from psycopg import connect

from app.config import DATABASE_URL

COLLECTION_NAME = "experiment_memory"
TITLE_LIMIT = 120
CAMPAIGN = "campaign"
SELECT = (
    "SELECT e.id, e.cmetadata FROM langchain_pg_embedding e "
    "JOIN langchain_pg_collection c ON c.uuid = e.collection_id WHERE c.name = %s ORDER BY e.id"
)
DELETE = (
    "DELETE FROM langchain_pg_embedding WHERE id = ANY(%s) "
    "AND collection_id IN (SELECT uuid FROM langchain_pg_collection WHERE name = %s)"
)


def describe(identifier: str, metadata: dict[str, Any]) -> dict[str, str]:
    spec = metadata.get("spec") or {}
    title = str(spec.get("title") or metadata.get("hypothesis") or "")
    return {
        "id": str(identifier),
        "outcome": str(metadata.get("outcome") or ""),
        "title": title[:TITLE_LIMIT],
        "verdicts": str(metadata.get("metric") or ""),
    }


def _rows() -> list[dict[str, str]]:
    with connect(DATABASE_URL, autocommit=True) as connection:
        found = connection.execute(SELECT, (COLLECTION_NAME,)).fetchall()
    return [describe(identifier, metadata or {}) for identifier, metadata in found]


def _list(arguments: argparse.Namespace) -> int:
    rows = _rows()
    shown = [row for row in rows if not arguments.outcome or row["outcome"] == arguments.outcome]
    for row in shown:
        print(json.dumps(row, ensure_ascii=False))
    campaigns = sum(1 for row in rows if row["outcome"] == CAMPAIGN)
    print(f"{len(rows)} memories ({campaigns} campaigns)", file=sys.stderr)
    return 0


def _delete(arguments: argparse.Namespace) -> int:
    known = {row["id"] for row in _rows()}
    unknown = [identifier for identifier in arguments.ids if identifier not in known]
    if unknown:
        print("unknown memory ids: " + ", ".join(unknown), file=sys.stderr)
        return 2
    if not arguments.yes:
        print("nothing was deleted; repeat the command with --yes to delete " + ", ".join(arguments.ids), file=sys.stderr)
        return 2
    with connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(DELETE, (list(arguments.ids), COLLECTION_NAME))
    print(f"deleted {len(arguments.ids)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List or delete the memories of past runs that the planner reads.")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list the stored memories; never changes anything")
    listing.add_argument("--outcome", help="show only this outcome, for example campaign")
    removal = commands.add_parser("delete", help="delete memories by id; needs --yes")
    removal.add_argument("ids", nargs="+")
    removal.add_argument("--yes", action="store_true", help="really delete")
    arguments = parser.parse_args(argv)
    if not DATABASE_URL:
        print("DATABASE_URL is missing", file=sys.stderr)
        return 2
    return _list(arguments) if arguments.command == "list" else _delete(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
