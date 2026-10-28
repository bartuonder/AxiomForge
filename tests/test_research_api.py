import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.research.session as session
from tests.test_research_session import MODELS, config, make_runner, planted


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())
    return tmp_path / "research"


@pytest.fixture
def client():
    return TestClient(main.app)


def done(session_id="s1"):
    return session.run_session(config(id=session_id), runner=make_runner(planted()))


class TestSummary:
    def test_it_counts_the_statuses_and_keeps_the_basics(self):
        state = done()
        summary = session.summary_of(state)
        assert summary["id"] == "s1" and summary["status"] == "completed" and summary["models"] == MODELS
        assert summary["registered"] == len(state["hypotheses"]) and summary["budget"] == state["budget"]
        assert summary["counts"]["confirmed"] == sum(1 for item in state["confirmations"] if item["status"] == "confirmed")
        assert set(summary["counts"]) == {"confirmed", "reversed", "not_confirmed", "not_testable"}
        assert len(summary["explore"]) == 6 and len(summary["confirm"]) == 10

    def test_a_session_without_results_has_zero_counts(self):
        summary = session.summary_of({"id": "x", "status": "running", "hypotheses": [], "config": {"models": MODELS}, "explore": [], "confirm": [], "budget": 0})
        assert summary["counts"] == {"confirmed": 0, "reversed": 0, "not_confirmed": 0, "not_testable": 0} and summary["registered"] == 0

    def test_the_reason_and_the_times_are_kept(self):
        summary = session.summary_of(done())
        assert summary["created"].endswith("+00:00") and summary["finished"].endswith("+00:00") and summary["reason"] == ""
        stopped = session.summary_of({"id": "x", "status": "aborted", "reason": "only 2 of 6 exploration datasets finished", "hypotheses": [], "config": {"models": MODELS}, "explore": [], "confirm": [], "budget": 0})
        assert stopped["reason"] == "only 2 of 6 exploration datasets finished"

    def test_the_stages_are_summarised(self):
        summary = session.summary_of(done())
        assert summary["stages"] == [{"name": "default", "finished": 16, "failed": 0}]


class TestList:
    def test_an_empty_list(self, client):
        assert client.get("/research_sessions").json() == {"items": []}

    def test_the_newest_session_comes_first(self, client):
        done("a")
        done("b")
        items = client.get("/research_sessions").json()["items"]
        assert [item["id"] for item in items] == ["b", "a"]
        assert items[0]["status"] == "completed" and "counts" in items[0]


class TestDetail:
    def test_it_returns_the_session_with_its_summary(self, client):
        state = done()
        body = client.get("/research_sessions/s1").json()
        assert body["summary"]["id"] == "s1" and body["session"]["hypotheses"] == state["hypotheses"]
        assert body["session"]["confirmations"] == state["confirmations"]

    def test_an_unknown_session_is_404(self, client):
        assert client.get("/research_sessions/nope").status_code == 404

    def test_a_bad_id_is_400(self, client):
        assert client.get("/research_sessions/..%2Fx").status_code in {400, 404}
        assert client.get("/research_sessions/.hidden").status_code == 400

    def test_the_report_is_returned(self, client):
        done()
        body = client.get("/research_sessions/s1/report").json()
        assert body["markdown"].startswith("# Research session s1")

    def test_the_report_of_a_bad_id_is_400_and_of_an_unknown_session_404(self, client):
        assert client.get("/research_sessions/.hidden/report").status_code == 400
        assert client.get("/research_sessions/nope/report").status_code == 404

    def test_a_session_without_a_report_is_404(self, client):
        session.save({"id": "bare", "status": "running", "hypotheses": [], "config": {"models": MODELS}, "explore": [], "confirm": [], "budget": 0})
        assert client.get("/research_sessions/bare/report").status_code == 404

    def test_the_integrity_of_the_registered_hypotheses_is_reported(self, client, root):
        import json

        done()
        assert client.get("/research_sessions/s1").json()["intact"] is True
        path = root / "s1" / "session.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["hypotheses"][0]["subject"] = ["MLP"]
        path.write_text(json.dumps(data), encoding="utf-8")
        assert client.get("/research_sessions/s1").json()["intact"] is False
