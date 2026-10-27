import json

import pytest

import tools.memory_report as memory_tool


class FakeConnection:
    def __init__(self, rows, log):
        self.rows = rows
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params=None):
        self.log.append((" ".join(statement.split()), params))
        if statement.lstrip().upper().startswith("SELECT"):
            return type("Cursor", (), {"fetchall": lambda cursor: self.rows})()
        return type("Cursor", (), {"rowcount": len(params[0]) if params else 0})()


@pytest.fixture
def database(monkeypatch):
    log = []
    rows = [
        ("id-1", {"outcome": "campaign", "hypothesis": "Trees vs nets: Trees beat nets", "metric": "C1 replicated", "spec": {"title": "Trees vs nets", "claims": [{"statement": "Trees beat nets"}]}}),
        ("id-2", {"outcome": "success", "hypothesis": "RF beats SVM", "metric": "", "spec": {}}),
        ("id-3", {"outcome": "campaign", "hypothesis": "Boosting beats regression", "metric": "C1 inconclusive", "spec": {"title": "Boosting", "claims": []}}),
    ]
    monkeypatch.setattr(memory_tool, "DATABASE_URL", "postgresql://x")
    monkeypatch.setattr(memory_tool, "connect", lambda url, **kwargs: FakeConnection(rows, log))
    return log


class TestRows:
    def test_a_row_is_described_by_its_id_outcome_title_and_verdicts(self):
        row = memory_tool.describe("id-1", {"outcome": "campaign", "hypothesis": "H", "metric": "C1 replicated", "spec": {"title": "Trees vs nets"}})
        assert row == {"id": "id-1", "outcome": "campaign", "title": "Trees vs nets", "verdicts": "C1 replicated"}

    def test_the_hypothesis_is_the_title_when_there_is_no_spec(self):
        assert memory_tool.describe("x", {"outcome": "success", "hypothesis": "RF beats SVM"})["title"] == "RF beats SVM"

    def test_missing_fields_are_empty(self):
        assert memory_tool.describe("x", {}) == {"id": "x", "outcome": "", "title": "", "verdicts": ""}

    def test_a_long_title_is_cut(self):
        assert len(memory_tool.describe("x", {"hypothesis": "h" * 500})["title"]) == memory_tool.TITLE_LIMIT


class TestList:
    def test_it_lists_every_memory(self, database, capsys):
        assert memory_tool.main(["list"]) == 0
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert [line["id"] for line in lines] == ["id-1", "id-2", "id-3"]

    def test_it_can_show_only_the_campaigns(self, database, capsys):
        memory_tool.main(["list", "--outcome", "campaign"])
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert [line["id"] for line in lines] == ["id-1", "id-3"]

    def test_listing_never_writes(self, database):
        memory_tool.main(["list"])
        assert all(statement.upper().startswith("SELECT") for statement, _ in database)

    def test_the_query_reads_the_memory_collection(self, database):
        memory_tool.main(["list"])
        statement, params = database[0]
        assert "langchain_pg_embedding" in statement and "langchain_pg_collection" in statement and params == (memory_tool.COLLECTION_NAME,)

    def test_the_summary_line_counts_what_was_found(self, database, capsys):
        memory_tool.main(["list"])
        assert capsys.readouterr().err.strip() == "3 memories (2 campaigns)"


class TestDelete:
    def test_without_the_confirmation_nothing_is_deleted(self, database, capsys):
        assert memory_tool.main(["delete", "id-1"]) == 2
        assert "--yes" in capsys.readouterr().err
        assert all(statement.upper().startswith("SELECT") for statement, _ in database)

    def test_with_the_confirmation_the_given_ids_are_deleted(self, database, capsys):
        assert memory_tool.main(["delete", "id-1", "id-3", "--yes"]) == 0
        statement, params = database[-1]
        assert statement.upper().startswith("DELETE") and params == (["id-1", "id-3"], memory_tool.COLLECTION_NAME)
        assert capsys.readouterr().out.strip() == "deleted 2"

    def test_an_unknown_id_is_refused_before_anything_is_deleted(self, database, capsys):
        assert memory_tool.main(["delete", "id-1", "nope", "--yes"]) == 2
        assert "nope" in capsys.readouterr().err
        assert all(not statement.upper().startswith("DELETE") for statement, _ in database)

    def test_an_id_is_needed(self):
        with pytest.raises(SystemExit):
            memory_tool.main(["delete", "--yes"])

    def test_the_delete_is_limited_to_the_memory_collection(self, database):
        memory_tool.main(["delete", "id-1", "--yes"])
        statement, _ = database[-1]
        assert "collection_id" in statement


class TestSetup:
    def test_a_missing_database_is_reported(self, monkeypatch, capsys):
        monkeypatch.setattr(memory_tool, "DATABASE_URL", "")
        assert memory_tool.main(["list"]) == 2
        assert "DATABASE_URL" in capsys.readouterr().err

    def test_a_command_is_needed(self):
        with pytest.raises(SystemExit):
            memory_tool.main([])


class TestConstants:
    def test_the_collection_is_the_one_the_memory_writes_to(self):
        from app.memory.rag_memory import COLLECTION_NAME

        assert memory_tool.COLLECTION_NAME == COLLECTION_NAME == "experiment_memory"

    def test_the_titles_are_cut_at_one_hundred_and_twenty_characters(self):
        assert memory_tool.TITLE_LIMIT == 120
        assert len(memory_tool.describe("x", {"hypothesis": "h" * 500})["title"]) == 120
