from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.graph.workflow as workflow

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def minutes_ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat()


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(workflow, "_now", lambda: NOW)


class TestRule:
    def values(self, **changes):
        return {"mode": "experiment", "hypotheses": ["h"], "approval_status": "approved", **changes}

    def test_a_checkpoint_older_than_the_limit_is_stale(self):
        text = workflow._stale_research_error(self.values(), ["experiment_node"], minutes_ago(31))
        assert text == "the research has reported no progress for 31 minutes; its worker may have stopped"

    def test_a_recent_checkpoint_is_fine(self):
        assert workflow._stale_research_error(self.values(), ["experiment_node"], minutes_ago(29)) == ""

    def test_the_limit_itself_is_still_fine(self):
        assert workflow._stale_research_error(self.values(), ["experiment_node"], minutes_ago(30)) == ""

    def test_the_limit_is_thirty_minutes(self):
        assert workflow.STALE_RESEARCH_SECONDS == 1800

    def test_a_finished_research_is_never_stale(self):
        assert workflow._stale_research_error(self.values(research_status="Completed"), [], minutes_ago(500)) == ""
        assert workflow._stale_research_error(self.values(research_status="NeedsReview"), [], minutes_ago(500)) == ""

    def test_a_finished_research_with_a_pending_node_is_not_stale(self):
        assert workflow._stale_research_error(self.values(research_status="Completed"), ["meta_report_node"], minutes_ago(500)) == ""
        assert workflow._stale_research_error(self.values(research_status="NeedsReview"), ["meta_report_node"], minutes_ago(500)) == ""

    def test_an_approved_research_stuck_at_the_gate_is_stale(self):
        assert "no progress" in workflow._stale_research_error(self.values(), ["approval_gate"], minutes_ago(45))

    def test_a_campaign_id_in_an_experiment_does_not_exempt_it(self):
        assert "no progress" in workflow._stale_research_error(self.values(campaign_id="c-1"), ["experiment_node"], minutes_ago(45))

    def test_a_graph_with_nothing_left_to_run_is_not_stale(self):
        assert workflow._stale_research_error(self.values(), [], minutes_ago(500)) == ""

    def test_a_paused_research_waits_for_the_user_not_for_a_worker(self):
        values = self.values(approval_status="")
        assert workflow._stale_research_error(values, ["approval_gate"], minutes_ago(500)) == ""

    def test_a_rejected_research_is_not_stale(self):
        assert workflow._stale_research_error(self.values(approval_status="rejected"), ["experiment_node"], minutes_ago(500)) == ""

    def test_the_wait_for_a_campaign_is_left_to_the_campaign_rule(self):
        values = self.values(mode="campaign", campaign_id="c-1")
        assert workflow._stale_research_error(values, ["campaign_collect_node"], minutes_ago(500)) == ""

    def test_a_campaign_without_an_id_yet_can_be_stale(self):
        values = self.values(mode="campaign")
        assert "no progress" in workflow._stale_research_error(values, ["campaign_planner_node"], minutes_ago(45))

    def test_a_campaign_whose_results_arrived_can_be_stale(self):
        values = self.values(mode="campaign", campaign_id="c-1", campaign_analysis={"claims": []})
        assert "no progress" in workflow._stale_research_error(values, ["meta_report_node"], minutes_ago(45))

    def test_a_thread_without_state_is_not_stale(self):
        assert workflow._stale_research_error({}, [], minutes_ago(500)) == ""
        assert workflow._stale_research_error({}, ["literature_node"], minutes_ago(500)) == ""

    @pytest.mark.parametrize("created", [None, "", "not a date", 5])
    def test_a_missing_or_broken_timestamp_is_ignored(self, created):
        assert workflow._stale_research_error(self.values(), ["experiment_node"], created) == ""

    def test_a_timestamp_without_a_zone_is_read_as_utc(self):
        naive = (NOW - timedelta(minutes=45)).replace(tzinfo=None).isoformat()
        assert "no progress for 45 minutes" in workflow._stale_research_error(self.values(), ["experiment_node"], naive)


class FakeGraph:
    def __init__(self, values, next_nodes, created_at):
        self.snapshot = SimpleNamespace(values=values, next=tuple(next_nodes), created_at=created_at)

    def get_state(self, config):
        return self.snapshot


@pytest.fixture
def graph(monkeypatch):
    def install(values, next_nodes, created_at):
        fake = FakeGraph(values, next_nodes, created_at)

        @contextmanager
        def opened():
            yield SimpleNamespace(setup=lambda: None)

        monkeypatch.setattr(workflow, "_open_graph", opened)
        monkeypatch.setattr(workflow, "_compile", lambda checkpointer: fake)
        monkeypatch.setattr(workflow, "read_error", lambda thread_id: "")

    return install


class TestStatus:
    VALUES = {"mode": "experiment", "hypotheses": ["h"], "approval_status": "approved", "query": "q"}

    def test_a_stale_run_is_reported_as_failed_with_the_reason(self, graph):
        graph(dict(self.VALUES), ["experiment_node"], minutes_ago(50))
        result = workflow.get_research("t")
        assert result["status"] == "failed" and "no progress for 50 minutes" in result["error"]

    def test_a_fresh_run_stays_running(self, graph):
        graph(dict(self.VALUES), ["experiment_node"], minutes_ago(2))
        result = workflow.get_research("t")
        assert result["status"] == "running" and result["error"] == ""

    def test_a_recorded_error_wins_over_the_stale_text(self, graph, monkeypatch):
        graph(dict(self.VALUES), ["experiment_node"], minutes_ago(50))
        monkeypatch.setattr(workflow, "read_error", lambda thread_id: "boom")
        assert workflow.get_research("t")["error"] == "boom"

    def test_a_snapshot_without_a_timestamp_is_fine(self, graph):
        graph(dict(self.VALUES), ["experiment_node"], None)
        assert workflow.get_research("t")["status"] == "running"

    def test_a_paused_run_stays_paused_however_old(self, graph):
        graph({**self.VALUES, "approval_status": ""}, ["approval_gate"], minutes_ago(900))
        assert workflow.get_research("t")["status"] == "paused"
