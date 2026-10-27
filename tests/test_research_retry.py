from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.graph.errors as errors
import app.graph.workflow as workflow
import app.guard as guard
import app.main as main


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("DAILY_START_LIMIT", raising=False)


def values(**changes):
    return {"mode": "experiment", "hypotheses": ["h"], "approval_status": "approved", **changes}


class TestPlan:
    def plan(self, vals=None, next_nodes=("experiment_node",), status="failed", campaign=None):
        return workflow.research_retry_plan(values() if vals is None else vals, list(next_nodes), status, campaign)

    def test_a_failed_research_with_a_step_left_is_resumed(self):
        assert self.plan() == {"action": "resume"}

    def test_a_missing_thread_is_404(self):
        with pytest.raises(workflow.PlanDecisionError) as caught:
            self.plan(vals={}, next_nodes=())
        assert caught.value.status_code == 404

    @pytest.mark.parametrize("status", ["running", "paused", "completed", "needs_review", "rejected", "starting"])
    def test_only_a_failed_research_can_be_started_again(self, status):
        with pytest.raises(workflow.PlanDecisionError) as caught:
            self.plan(status=status)
        assert caught.value.status_code == 409 and status in str(caught.value)

    def test_a_graph_with_nothing_left_has_nothing_to_run(self):
        with pytest.raises(workflow.PlanDecisionError) as caught:
            self.plan(next_nodes=())
        assert caught.value.status_code == 409

    def test_waiting_for_the_user_at_the_gate_is_not_a_failure_to_resume(self):
        with pytest.raises(workflow.PlanDecisionError) as caught:
            self.plan(vals=values(approval_status=""), next_nodes=("approval_gate",))
        assert caught.value.status_code == 409

    def test_an_approved_research_stuck_at_the_gate_is_resumed(self):
        assert self.plan(next_nodes=("approval_gate",)) == {"action": "resume"}

    def test_a_gate_that_is_not_the_next_step_does_not_mean_waiting(self):
        assert self.plan(vals=values(approval_status=""), next_nodes=("experiment_node", "approval_gate")) == {"action": "resume"}

    def test_a_rejected_research_stuck_at_the_gate_is_not_resumed(self):
        with pytest.raises(workflow.PlanDecisionError):
            self.plan(vals=values(approval_status="rejected"), next_nodes=("approval_gate",))

    @pytest.mark.parametrize("status", ["failed", "cancelled"])
    def test_a_campaign_research_whose_campaign_stopped_restarts_the_campaign(self, status):
        vals = values(mode="campaign", campaign_id="g-1")
        assert self.plan(vals=vals, next_nodes=("campaign_collect_node",), campaign={"status": status}) == {"action": "campaign", "campaign_id": "g-1"}

    @pytest.mark.parametrize("status", ["queued", "running", "completed", "needs_review"])
    def test_a_campaign_that_is_not_stopped_is_left_alone_and_the_graph_resumes(self, status):
        vals = values(mode="campaign", campaign_id="g-1")
        assert self.plan(vals=vals, next_nodes=("campaign_collect_node",), campaign={"status": status}) == {"action": "resume"}

    def test_a_campaign_research_without_a_campaign_record_resumes_the_graph(self):
        assert self.plan(vals=values(mode="campaign", campaign_id="g-1"), next_nodes=("campaign_dispatch_node",), campaign=None) == {"action": "resume"}

    def test_an_experiment_never_restarts_a_campaign(self):
        assert self.plan(vals=values(campaign_id="g-1"), campaign={"status": "failed"}) == {"action": "resume"}

    def test_a_campaign_whose_result_already_arrived_resumes_the_graph(self):
        vals = values(mode="campaign", campaign_id="g-1", campaign_analysis={"claims": []})
        assert self.plan(vals=vals, next_nodes=("meta_report_node",), campaign={"status": "failed"}) == {"action": "resume"}

    def test_a_campaign_research_before_any_campaign_exists_resumes_the_graph(self):
        assert self.plan(vals=values(mode="campaign"), next_nodes=("campaign_planner_node",), campaign={"status": "failed"}) == {"action": "resume"}


class TestCanRetry:
    def test_it_follows_the_plan(self):
        assert workflow._can_retry(values(), ["experiment_node"], "failed") is True

    def test_it_is_false_when_the_plan_refuses(self):
        assert workflow._can_retry(values(), [], "failed") is False
        assert workflow._can_retry(values(), ["experiment_node"], "running") is False
        assert workflow._can_retry({}, [], "starting") is False

    def test_a_failed_campaign_research_can_be_retried_without_looking_at_the_campaign(self):
        assert workflow._can_retry(values(mode="campaign", campaign_id="g-1"), ["campaign_collect_node"], "failed") is True


class TestStatusField:
    def snapshot(self, monkeypatch, vals, next_nodes, error=""):
        snapshot = SimpleNamespace(values=vals, next=tuple(next_nodes), created_at=None)
        monkeypatch.setattr(workflow, "read_error", lambda thread_id: error)
        monkeypatch.setattr(workflow, "_load_snapshot", lambda thread_id: snapshot)
        return snapshot

    def test_a_failed_research_offers_a_retry(self, monkeypatch):
        self.snapshot(monkeypatch, values(), ["experiment_node"], error="[unknown] boom")
        body = workflow.get_research("t")
        assert body["status"] == "failed" and body["can_retry"] is True

    def test_a_running_research_does_not(self, monkeypatch):
        self.snapshot(monkeypatch, values(), ["experiment_node"])
        assert workflow.get_research("t")["can_retry"] is False

    def test_a_failure_at_the_very_start_does_not(self, monkeypatch):
        self.snapshot(monkeypatch, {}, [], error="[unknown] boom")
        body = workflow.get_research("t")
        assert body["status"] == "failed" and body["can_retry"] is False


class TestPlanFromTheStore:
    NOW = __import__("datetime").datetime(2026, 10, 27, 12, 0, tzinfo=__import__("datetime").timezone.utc)

    def load(self, monkeypatch, vals, next_nodes, error="", minutes=0, campaign=None):
        from datetime import timedelta

        created = (self.NOW - timedelta(minutes=minutes)).isoformat()
        snapshot = SimpleNamespace(values=vals, next=tuple(next_nodes), created_at=created)
        monkeypatch.setattr(workflow, "_now", lambda: self.NOW)
        monkeypatch.setattr(workflow, "read_error", lambda thread_id: error)
        monkeypatch.setattr(workflow, "_load_snapshot", lambda thread_id: snapshot)
        monkeypatch.setattr(workflow.campaign_store, "load_state", lambda campaign_id: campaign)

    def test_a_recorded_error_makes_the_research_retryable(self, monkeypatch):
        self.load(monkeypatch, values(), ["experiment_node"], error="[unknown] boom")
        assert workflow.plan_research_retry("t") == {"action": "resume"}

    def test_an_idle_checkpoint_counts_as_stale_and_is_retryable(self, monkeypatch):
        self.load(monkeypatch, values(), ["experiment_node"], minutes=45)
        assert workflow.plan_research_retry("t") == {"action": "resume"}

    def test_a_recent_checkpoint_without_an_error_is_still_running(self, monkeypatch):
        self.load(monkeypatch, values(), ["experiment_node"], minutes=5)
        with pytest.raises(workflow.PlanDecisionError) as caught:
            workflow.plan_research_retry("t")
        assert caught.value.status_code == 409 and "running" in str(caught.value)

    def test_a_stale_campaign_is_restarted_with_its_thread(self, monkeypatch):
        vals = values(mode="campaign", campaign_id="g-1")
        campaign = {"id": "g-1", "status": "running", "updated": (self.NOW.replace(hour=10)).isoformat(timespec="seconds"), "datasets": {}}
        self.load(monkeypatch, vals, ["campaign_collect_node"], minutes=1, campaign=campaign)
        monkeypatch.setattr(workflow, "effective_state", __import__("functools").partial(__import__("app.campaign.service", fromlist=["x"]).effective_state, now=self.NOW))
        assert workflow.plan_research_retry("t") == {"action": "campaign", "campaign_id": "g-1"}

    def test_a_cancelled_campaign_is_restarted(self, monkeypatch):
        vals = values(mode="campaign", campaign_id="g-1")
        self.load(monkeypatch, vals, ["campaign_collect_node"], error="[campaign_cancelled] x", campaign={"id": "g-1", "status": "cancelled", "datasets": {}})
        assert workflow.plan_research_retry("t") == {"action": "campaign", "campaign_id": "g-1"}

    def test_a_missing_campaign_record_falls_back_to_resuming(self, monkeypatch):
        vals = values(mode="campaign", campaign_id="g-1")
        self.load(monkeypatch, vals, ["campaign_collect_node"], error="[unknown] x", campaign=None)
        assert workflow.plan_research_retry("t") == {"action": "resume"}

    def test_an_unreadable_campaign_record_falls_back_to_resuming(self, monkeypatch):
        vals = values(mode="campaign", campaign_id="../bad")
        self.load(monkeypatch, vals, ["campaign_collect_node"], error="[unknown] x")

        def broken(campaign_id):
            raise workflow.campaign_store.CampaignStoreError("bad id")

        monkeypatch.setattr(workflow.campaign_store, "load_state", broken)
        assert workflow.plan_research_retry("t") == {"action": "resume"}

    def test_an_unknown_thread_is_404(self, monkeypatch):
        self.load(monkeypatch, {}, [])
        with pytest.raises(workflow.PlanDecisionError) as caught:
            workflow.plan_research_retry("t")
        assert caught.value.status_code == 404


class TestErrors:
    def test_clearing_forgets_the_remembered_error(self, monkeypatch):
        monkeypatch.setattr(errors, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("no database")))
        errors.record_error("t-1", "boom")
        assert errors.read_error("t-1") == "boom"
        errors.clear_error("t-1")
        assert errors.read_error("t-1") == ""

    def test_clearing_something_never_recorded_is_harmless(self, monkeypatch):
        monkeypatch.setattr(errors, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("no database")))
        errors.clear_error("never-recorded")
        assert errors.read_error("never-recorded") == ""

    def test_clearing_deletes_the_stored_row(self, monkeypatch):
        executed = []

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                executed.append((sql, params))
                return SimpleNamespace(fetchone=lambda: None)

        monkeypatch.setattr(errors, "_connect", lambda: Connection())
        monkeypatch.setattr(errors, "_table_ready", True)
        errors.clear_error("t-2")
        assert executed == [(errors.DELETE, ("t-2",))]
        assert errors.DELETE == "DELETE FROM research_errors WHERE thread_id = %s"


class TestEndpoint:
    @pytest.fixture
    def client(self, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "_enqueue", lambda task, *args: calls.append((task, args)))
        monkeypatch.setattr(main, "plan_research_retry", lambda thread_id: {"action": "resume"})
        monkeypatch.setattr(main, "clear_error", lambda thread_id: calls.append(("cleared", thread_id)))
        client = TestClient(main.app)
        client.calls = calls
        return client

    def test_a_resume_clears_the_error_and_queues_the_resume_task(self, client):
        response = client.post("/research/t-1/retry")
        assert response.status_code == 200 and response.json() == {"thread_id": "t-1", "status": "running", "action": "resume"}
        assert client.calls == [("cleared", "t-1"), (main.resume_research_task, ("t-1",))]

    def test_a_stopped_campaign_is_started_again_with_the_thread_attached(self, client, monkeypatch):
        monkeypatch.setattr(main, "plan_research_retry", lambda thread_id: {"action": "campaign", "campaign_id": "g-9"})
        seen = []
        monkeypatch.setattr(main, "retry_campaign", lambda campaign_id, before=None: seen.append(campaign_id) or ({"title": "spec"}, {}))
        response = client.post("/research/t-1/retry")
        assert response.status_code == 200 and response.json()["action"] == "campaign"
        assert seen == ["g-9"]
        assert client.calls == [("cleared", "t-1"), (main.run_campaign_task, ("g-9", {"title": "spec"}, "t-1"))]

    def test_the_refusal_of_the_plan_is_passed_on(self, client, monkeypatch):
        def refuse(thread_id):
            raise workflow.PlanDecisionError("the research is running, so there is nothing to start again", 409)

        monkeypatch.setattr(main, "plan_research_retry", refuse)
        response = client.post("/research/t-1/retry")
        assert response.status_code == 409 and "running" in response.json()["detail"]
        assert client.calls == []

    def test_a_missing_database_is_503(self, client, monkeypatch):
        def broken(thread_id):
            raise RuntimeError("DATABASE_URL is missing")

        monkeypatch.setattr(main, "plan_research_retry", broken)
        assert client.post("/research/t-1/retry").status_code == 503

    def test_it_spends_one_start_after_the_plan_is_accepted(self, client, monkeypatch):
        spent = []
        monkeypatch.setattr(main, "spend_start", lambda: spent.append(1))
        client.post("/research/t-1/retry")
        assert spent == [1]

    def test_a_refused_plan_spends_nothing(self, client, monkeypatch):
        spent = []
        monkeypatch.setattr(main, "spend_start", lambda: spent.append(1))

        def refuse(thread_id):
            raise workflow.PlanDecisionError("no", 409)

        monkeypatch.setattr(main, "plan_research_retry", refuse)
        client.post("/research/t-1/retry")
        assert spent == []

    def test_a_spent_daily_limit_stops_the_retry_and_leaves_the_error_alone(self, client, monkeypatch):
        def exhausted():
            raise main.HTTPException(status_code=429, detail="[daily_limit] 100")

        recorded = []
        monkeypatch.setattr(main, "spend_start", exhausted)
        monkeypatch.setattr(main, "record_error", lambda thread_id, message: recorded.append(message))
        response = client.post("/research/t-1/retry")
        assert response.status_code == 429
        assert client.calls == [] and recorded == []

    def test_a_campaign_that_cannot_be_started_again_is_reported(self, client, monkeypatch):
        import app.campaign.service as service

        monkeypatch.setattr(main, "plan_research_retry", lambda thread_id: {"action": "campaign", "campaign_id": "g-9"})

        def refuse(campaign_id, before=None):
            raise service.CampaignControlError("the specification of this campaign was not saved", 409)

        monkeypatch.setattr(main, "retry_campaign", refuse)
        response = client.post("/research/t-1/retry")
        assert response.status_code == 409 and "specification" in response.json()["detail"]
        assert client.calls == []

    def test_the_status_code_of_a_campaign_refusal_is_kept(self, client, monkeypatch):
        import app.campaign.service as service

        monkeypatch.setattr(main, "plan_research_retry", lambda thread_id: {"action": "campaign", "campaign_id": "g-9"})

        def refuse(campaign_id, before=None):
            raise service.CampaignControlError("campaign not found", 404)

        monkeypatch.setattr(main, "retry_campaign", refuse)
        assert client.post("/research/t-1/retry").status_code == 404

    def test_a_key_is_required_when_one_is_set(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        assert client.post("/research/t-1/retry").status_code == 401
        assert client.post("/research/t-1/retry", headers={"X-API-Key": "secret"}).status_code == 200

    def test_a_queue_that_is_down_leaves_the_error_in_place_message(self, monkeypatch):
        def refuse(task, *args):
            raise main.HTTPException(status_code=503, detail="queue is down")

        recorded = []
        monkeypatch.setattr(main, "_enqueue", refuse)
        monkeypatch.setattr(main, "plan_research_retry", lambda thread_id: {"action": "resume"})
        monkeypatch.setattr(main, "clear_error", lambda thread_id: None)
        monkeypatch.setattr(main, "record_error", lambda thread_id, message: recorded.append((thread_id, message)))
        response = TestClient(main.app).post("/research/t-1/retry")
        assert response.status_code == 503
        assert recorded == [("t-1", "queue is down")]
