import json
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.campaign.service as service
import app.campaign.store as store
import app.graph.campaign_nodes as campaign_nodes
import app.graph.workflow as workflow
import app.tasks as tasks
from app.campaign.demos import demo_spec
from app.campaign.spec import CampaignSpecError
from app.graph.campaign_nodes import campaign_collect_node, campaign_dispatch_node

SPEC = demo_spec("grinsztajn-2022")
CONFIG = {"configurable": {"thread_id": "thread-1"}}
ANALYSIS = {"coverage": {"finished": ["a"]}, "claims": [{"id": "C1", "verdict": "replicated"}]}
LEDGER = [{"id": "E1", "kind": "dataset", "key": "a"}]


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    return tmp_path / "campaigns"


@pytest.fixture
def queue(monkeypatch):
    sent = []
    monkeypatch.setattr(campaign_nodes, "_enqueue_campaign", lambda campaign_id, spec, thread_id: sent.append((campaign_id, spec, thread_id)))
    return sent


def finish(campaign_id, status="completed", **extra):
    store.save_artifacts(campaign_id, "# r", LEDGER, ANALYSIS, {})
    state = store.load_state(campaign_id)
    store.save_state(campaign_id, state | {"status": status, **extra})


class TestCampaignId:
    def test_it_is_a_valid_store_id(self):
        campaign_id = service.campaign_id_for("thread-1", SPEC)
        assert re.fullmatch(r"g-[0-9a-f]{32}", campaign_id)
        assert store.campaign_dir(campaign_id).name == campaign_id

    def test_it_is_stable(self):
        assert service.campaign_id_for("t", SPEC) == service.campaign_id_for("t", dict(SPEC))

    def test_key_order_does_not_matter(self):
        reordered = dict(reversed(list(SPEC.items())))
        assert service.campaign_id_for("t", SPEC) == service.campaign_id_for("t", reordered)

    def test_another_thread_or_spec_gives_another_id(self):
        base = service.campaign_id_for("t", SPEC)
        assert service.campaign_id_for("u", SPEC) != base
        assert service.campaign_id_for("t", {**SPEC, "title": "other"}) != base


class TestQueueOnce:
    def test_the_first_call_stores_a_queued_campaign(self):
        spec, created = service.queue_once("g-1", SPEC)
        assert created is True and spec["title"] == SPEC["title"]
        state = store.load_state("g-1")
        assert state["status"] == "queued" and state["queued"].endswith("+00:00")
        assert list(state["datasets"]) == spec["datasets"]

    def test_the_second_call_changes_nothing(self):
        service.queue_once("g-1", SPEC)
        store.save_state("g-1", store.load_state("g-1") | {"status": "running"})
        spec, created = service.queue_once("g-1", SPEC)
        assert created is False and store.load_state("g-1")["status"] == "running"

    def test_an_invalid_spec_is_refused_before_anything_is_stored(self, root):
        with pytest.raises(CampaignSpecError):
            service.queue_once("g-1", {**SPEC, "claims": []})
        assert not root.exists()

    def test_the_returned_spec_is_the_validated_one(self):
        spec, _ = service.queue_once("g-1", {**SPEC, "unknown_key": 1})
        assert "unknown_key" not in spec


def test_the_analysis_is_read_back_and_a_missing_one_is_none():
    assert store.load_analysis("g-1") is None
    store.save_artifacts("g-1", "r", [], {"claims": [{"id": "C1"}]}, {})
    assert store.load_analysis("g-1") == {"claims": [{"id": "C1"}]}


class TestDispatch:
    def state(self, **changes):
        return {"campaign_spec": SPEC, **changes}

    def test_a_first_dispatch_stores_the_campaign_and_enqueues_it_once(self, queue):
        update = campaign_dispatch_node(self.state(), CONFIG)
        campaign_id = service.campaign_id_for("thread-1", SPEC)
        assert update == {"campaign_id": campaign_id, "campaign_status": "queued"}
        assert store.load_state(campaign_id)["status"] == "queued"
        assert len(queue) == 1 and queue[0][0] == campaign_id and queue[0][2] == "thread-1"
        assert queue[0][1]["title"] == SPEC["title"] and queue[0][1]["claims"][0]["id"] == "C1"
        assert queue[0][1]["params"] == {} and queue[0][1]["datasets"] == SPEC.get("datasets", queue[0][1]["datasets"])
        assert len(queue[0][1]["datasets"]) == 9

    def test_a_replayed_dispatch_never_enqueues_a_second_campaign(self, queue):
        first = campaign_dispatch_node(self.state(), CONFIG)
        second = campaign_dispatch_node(self.state(), CONFIG)
        assert first == second and len(queue) == 1

    def test_a_replay_after_the_campaign_started_leaves_it_alone(self, queue):
        update = campaign_dispatch_node(self.state(), CONFIG)
        store.save_state(update["campaign_id"], store.load_state(update["campaign_id"]) | {"status": "running"})
        campaign_dispatch_node(self.state(), CONFIG)
        assert len(queue) == 1 and store.load_state(update["campaign_id"])["status"] == "running"

    def test_another_thread_gets_its_own_campaign(self, queue):
        campaign_dispatch_node(self.state(), CONFIG)
        campaign_dispatch_node(self.state(), {"configurable": {"thread_id": "thread-2"}})
        assert len(queue) == 2 and queue[0][0] != queue[1][0]

    @pytest.mark.parametrize("config", [{}, {"configurable": {}}, {"configurable": {"thread_id": ""}}, None])
    def test_a_missing_thread_id_is_refused(self, queue, config):
        with pytest.raises(RuntimeError, match="needs a research thread id"):
            campaign_dispatch_node(self.state(), config)
        assert queue == []

    def test_a_missing_approved_spec_is_refused(self, queue):
        with pytest.raises(RuntimeError, match="no campaign was approved"):
            campaign_dispatch_node({}, CONFIG)
        with pytest.raises(RuntimeError, match="no campaign was approved"):
            campaign_dispatch_node({"campaign_spec": {}}, CONFIG)
        assert queue == []

    def test_an_invalid_spec_enqueues_nothing_and_stores_nothing(self, queue, root):
        with pytest.raises(CampaignSpecError):
            campaign_dispatch_node({"campaign_spec": {**SPEC, "claims": []}}, CONFIG)
        assert queue == [] and not root.exists()

    def test_a_queue_that_is_down_marks_the_campaign_failed_and_raises(self, monkeypatch):
        def down(campaign_id, spec, thread_id):
            raise ConnectionError("broker is down")

        monkeypatch.setattr(campaign_nodes, "_enqueue_campaign", down)
        with pytest.raises(ConnectionError, match="broker is down"):
            campaign_dispatch_node(self.state(), CONFIG)
        campaign_id = service.campaign_id_for("thread-1", SPEC)
        state = store.load_state(campaign_id)
        assert state["status"] == "failed" and "could not be queued: broker is down" in state["error"]

    def test_the_celery_task_receives_the_ids(self, monkeypatch):
        sent = []
        monkeypatch.setattr(tasks.run_campaign_task, "delay", lambda *args: sent.append(args))
        campaign_nodes._enqueue_campaign("g-1", {"title": "x"}, "thread-1")
        assert sent == [("g-1", {"title": "x"}, "thread-1")]


class TestCollect:
    def test_a_completed_campaign_is_collected(self):
        service.queue_once("g-1", SPEC)
        finish("g-1", issues=[], mlflow_run_id="run-7")
        update = campaign_collect_node({"campaign_id": "g-1"})
        assert update == {
            "campaign_status": "completed",
            "campaign_analysis": ANALYSIS,
            "campaign_ledger": LEDGER,
            "campaign_issues": [],
            "campaign_mlflow_run_id": "run-7",
        }

    def test_a_campaign_that_needs_review_is_collected_with_its_issues(self):
        service.queue_once("g-1", SPEC)
        finish("g-1", status="needs_review", issues=["E9 is cited but not in the ledger"])
        update = campaign_collect_node({"campaign_id": "g-1"})
        assert update["campaign_status"] == "needs_review" and update["campaign_issues"] == ["E9 is cited but not in the ledger"]
        assert update["campaign_mlflow_run_id"] == ""

    def test_a_failed_campaign_stops_the_research_with_its_error(self):
        service.queue_once("g-1", SPEC)
        service.reject_campaign("g-1", "E2B_API_KEY is missing")
        with pytest.raises(RuntimeError, match="campaign failed: E2B_API_KEY is missing"):
            campaign_collect_node({"campaign_id": "g-1"})

    def test_a_failed_campaign_without_an_error_still_says_so(self):
        service.queue_once("g-1", SPEC)
        store.save_state("g-1", store.load_state("g-1") | {"status": "failed"})
        with pytest.raises(RuntimeError, match="no error was recorded"):
            campaign_collect_node({"campaign_id": "g-1"})

    @pytest.mark.parametrize("status", ["queued", "running"])
    def test_a_campaign_that_is_still_running_is_not_collected(self, status):
        service.queue_once("g-1", SPEC)
        store.save_state("g-1", store.load_state("g-1") | {"status": status})
        with pytest.raises(RuntimeError, match=f"has not finished: {status}"):
            campaign_collect_node({"campaign_id": "g-1"})

    def test_an_unknown_campaign_is_refused(self):
        with pytest.raises(RuntimeError, match="was not found"):
            campaign_collect_node({"campaign_id": "g-404"})

    def test_a_state_without_a_campaign_is_refused(self):
        with pytest.raises(RuntimeError, match="no campaign was dispatched"):
            campaign_collect_node({})

    def test_a_finished_campaign_without_its_files_is_refused(self):
        service.queue_once("g-1", SPEC)
        store.save_state("g-1", store.load_state("g-1") | {"status": "completed"})
        with pytest.raises(RuntimeError, match="without its analysis and ledger"):
            campaign_collect_node({"campaign_id": "g-1"})

    def test_the_ledger_alone_is_not_enough(self):
        service.queue_once("g-1", SPEC)
        store.save_artifacts("g-1", "r", LEDGER, ANALYSIS, {})
        (store.campaign_dir("g-1") / "analysis.json").unlink()
        store.save_state("g-1", store.load_state("g-1") | {"status": "completed"})
        with pytest.raises(RuntimeError, match="without its analysis and ledger"):
            campaign_collect_node({"campaign_id": "g-1"})

    def test_the_analysis_alone_is_not_enough(self):
        service.queue_once("g-1", SPEC)
        store.save_artifacts("g-1", "r", LEDGER, ANALYSIS, {})
        (store.campaign_dir("g-1") / "ledger.json").unlink()
        store.save_state("g-1", store.load_state("g-1") | {"status": "completed"})
        with pytest.raises(RuntimeError, match="without its analysis and ledger"):
            campaign_collect_node({"campaign_id": "g-1"})


class FakeGraph:
    def __init__(self, values, next_nodes=("campaign_collect_node",)):
        self.values = values
        self.next_nodes = tuple(next_nodes)

    def get_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next_nodes)

    def update_state(self, config, update):
        self.values = {**self.values, **update}


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph({"mode": "campaign", "campaign_id": "g-1"})

    @contextmanager
    def opened():
        yield SimpleNamespace(setup=lambda: None)

    monkeypatch.setattr(workflow, "_open_graph", opened)
    monkeypatch.setattr(workflow, "_compile", lambda checkpointer: fake)
    monkeypatch.setattr(workflow, "read_error", lambda thread_id: "")
    return fake


class TestResumeCampaign:
    @pytest.fixture
    def resumed(self, monkeypatch):
        calls = []
        monkeypatch.setattr(workflow, "resume_research", lambda thread_id: calls.append(thread_id))
        return calls

    def test_a_finished_campaign_at_the_collection_step_resumes_the_graph(self, graph, resumed):
        service.queue_once("g-1", SPEC)
        finish("g-1")
        assert workflow.resume_campaign("t") == "resumed" and resumed == ["t"]

    def test_a_failed_campaign_resumes_too_so_that_the_graph_can_report_it(self, graph, resumed):
        service.queue_once("g-1", SPEC)
        service.reject_campaign("g-1", "boom")
        assert workflow.resume_campaign("t") == "resumed" and resumed == ["t"]

    def test_a_graph_that_has_not_reached_the_collection_step_is_waited_for(self, graph, resumed):
        service.queue_once("g-1", SPEC)
        finish("g-1")
        graph.next_nodes = ("campaign_dispatch_node",)
        assert workflow.resume_campaign("t") == "waiting" and resumed == []

    def test_a_graph_at_the_approval_gate_is_waited_for(self, graph, resumed):
        graph.next_nodes = ("approval_gate",)
        assert workflow.resume_campaign("t") == "waiting" and resumed == []

    @pytest.mark.parametrize("status", ["queued", "running"])
    def test_a_campaign_that_is_still_running_is_waited_for(self, graph, resumed, status):
        service.queue_once("g-1", SPEC)
        store.save_state("g-1", store.load_state("g-1") | {"status": status})
        assert workflow.resume_campaign("t") == "waiting" and resumed == []

    def test_a_missing_campaign_state_is_waited_for(self, graph, resumed):
        assert workflow.resume_campaign("t") == "waiting" and resumed == []

    def test_a_thread_that_already_collected_is_done_and_not_resumed_twice(self, graph, resumed):
        service.queue_once("g-1", SPEC)
        finish("g-1")
        graph.values["campaign_analysis"] = ANALYSIS
        graph.next_nodes = ()
        assert workflow.resume_campaign("t") == "done" and resumed == []

    def test_a_thread_without_a_campaign_id_is_waited_for(self, graph, resumed):
        graph.values = {"mode": "campaign"}
        assert workflow.resume_campaign("t") == "waiting" and resumed == []


class TestStaleCampaign:
    NOW = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture(autouse=True)
    def clock(self, monkeypatch):
        monkeypatch.setattr(workflow, "_now", lambda: self.NOW)

    def running(self, minutes_ago, status="running"):
        service.queue_once("g-1", SPEC)
        stamp = (self.NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        path = store.campaign_dir("g-1") / "state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**state, "status": status, "updated": stamp}), encoding="utf-8")

    def values(self, **changes):
        return {"mode": "campaign", "campaign_id": "g-1", **changes}

    def test_a_campaign_silent_for_longer_than_the_limit_is_stale(self):
        self.running(21)
        assert workflow._stale_campaign_error(self.values()) == "the campaign has reported no progress for 21 minutes; its worker may have stopped"

    def test_a_queued_campaign_that_never_started_is_stale_too(self):
        self.running(30, status="queued")
        assert "no progress for 30 minutes" in workflow._stale_campaign_error(self.values())

    def test_a_campaign_within_the_limit_is_fine(self):
        self.running(19)
        assert workflow._stale_campaign_error(self.values()) == ""

    def test_the_limit_itself_is_still_fine(self):
        self.running(20)
        assert workflow._stale_campaign_error(self.values()) == ""

    @pytest.mark.parametrize("status", ["completed", "needs_review", "failed"])
    def test_a_finished_campaign_is_never_stale(self, status):
        self.running(500, status=status)
        assert workflow._stale_campaign_error(self.values()) == ""

    def test_a_collected_campaign_is_never_stale(self):
        self.running(500)
        assert workflow._stale_campaign_error(self.values(campaign_analysis=ANALYSIS)) == ""

    def test_an_experiment_thread_is_never_stale(self):
        self.running(500)
        assert workflow._stale_campaign_error({"mode": "experiment", "campaign_id": "g-1"}) == ""
        assert workflow._stale_campaign_error({"campaign_id": "g-1"}) == ""

    def test_a_thread_without_a_campaign_id_is_never_stale(self):
        assert workflow._stale_campaign_error({"mode": "campaign"}) == ""

    def test_an_unknown_or_invalid_campaign_is_not_reported_as_stale(self):
        assert workflow._stale_campaign_error(self.values(campaign_id="g-404")) == ""
        assert workflow._stale_campaign_error(self.values(campaign_id="../bad")) == ""

    def test_a_broken_timestamp_is_ignored(self):
        self.running(1)
        path = store.campaign_dir("g-1") / "state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**state, "updated": "yesterday"}), encoding="utf-8")
        assert workflow._stale_campaign_error(self.values()) == ""

    def test_the_status_of_a_stale_campaign_is_failed_with_the_reason(self, graph):
        self.running(45)
        graph.values.update({"approval_status": "approved"})
        status = workflow.get_research("t")
        assert status["status"] == "failed" and "no progress for 45 minutes" in status["error"]

    def test_a_recorded_error_wins_over_the_stale_message(self, graph, monkeypatch):
        self.running(45)
        monkeypatch.setattr(workflow, "read_error", lambda thread_id: "the real error")
        assert workflow.get_research("t")["error"] == "the real error"

    def test_a_healthy_campaign_keeps_running(self, graph):
        self.running(1)
        graph.values.update({"approval_status": "approved"})
        status = workflow.get_research("t")
        assert status["status"] == "running" and status["error"] == ""


class TestTasks:
    def test_a_finished_campaign_task_wakes_the_graph(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tasks, "execute_campaign", lambda spec, campaign_id, tracker: calls.append(("run", campaign_id, tracker)))
        monkeypatch.setattr(tasks.resume_campaign_task, "delay", lambda thread_id: calls.append(("resume", thread_id)))
        tasks.run_campaign_task("g-1", {"title": "x"}, "thread-1")
        assert calls == [("run", "g-1", tasks.log_campaign), ("resume", "thread-1")]

    def test_a_campaign_started_without_a_thread_does_not_wake_anything(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tasks, "execute_campaign", lambda spec, campaign_id, tracker: calls.append("run"))
        monkeypatch.setattr(tasks.resume_campaign_task, "delay", lambda thread_id: calls.append("resume"))
        tasks.run_campaign_task("g-1", {"title": "x"})
        assert calls == ["run"]

    def test_the_graph_is_woken_even_when_the_campaign_failed(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tasks, "execute_campaign", lambda spec, campaign_id, tracker: {"status": "failed"})
        monkeypatch.setattr(tasks.resume_campaign_task, "delay", lambda thread_id: calls.append(thread_id))
        tasks.run_campaign_task("g-1", {"title": "x"}, "thread-1")
        assert calls == ["thread-1"]

    @pytest.mark.parametrize("outcome", ["resumed", "done"])
    def test_a_resumed_or_finished_thread_needs_no_retry(self, monkeypatch, outcome):
        retries = []
        monkeypatch.setattr(tasks, "resume_campaign", lambda thread_id: outcome)
        monkeypatch.setattr(tasks.resume_campaign_task, "apply_async", lambda *args, **kwargs: retries.append((args, kwargs)))
        tasks.resume_campaign_task("thread-1")
        assert retries == []

    def test_a_graph_that_is_not_ready_is_retried_with_a_delay_and_the_next_attempt(self, monkeypatch):
        retries = []
        monkeypatch.setattr(tasks, "resume_campaign", lambda thread_id: "waiting")
        monkeypatch.setattr(tasks.resume_campaign_task, "apply_async", lambda *args, **kwargs: retries.append((args, kwargs)))
        tasks.resume_campaign_task("thread-1")
        tasks.resume_campaign_task("thread-1", 7)
        assert retries == [
            ((("thread-1", 2),), {"countdown": tasks.RESUME_DELAY_SECONDS}),
            ((("thread-1", 8),), {"countdown": tasks.RESUME_DELAY_SECONDS}),
        ]

    def test_the_last_attempt_records_an_error_instead_of_retrying(self, monkeypatch):
        retries, errors = [], []
        monkeypatch.setattr(tasks, "resume_campaign", lambda thread_id: "waiting")
        monkeypatch.setattr(tasks, "record_error", lambda thread_id, message: errors.append((thread_id, message)))
        monkeypatch.setattr(tasks.resume_campaign_task, "apply_async", lambda *args, **kwargs: retries.append(args))
        tasks.resume_campaign_task("thread-1", tasks.RESUME_ATTEMPTS)
        assert retries == [] and errors == [("thread-1", "the research graph never reached the campaign collection step")]

    def test_the_second_to_last_attempt_still_retries(self, monkeypatch):
        retries = []
        monkeypatch.setattr(tasks, "resume_campaign", lambda thread_id: "waiting")
        monkeypatch.setattr(tasks, "record_error", lambda thread_id, message: pytest.fail("recorded"))
        monkeypatch.setattr(tasks.resume_campaign_task, "apply_async", lambda *args, **kwargs: retries.append(args))
        tasks.resume_campaign_task("thread-1", tasks.RESUME_ATTEMPTS - 1)
        assert retries == [(("thread-1", tasks.RESUME_ATTEMPTS),)]

    def test_the_task_names_are_stable(self):
        assert tasks.run_campaign_task.name == "axiomforge.run_campaign"
        assert tasks.resume_campaign_task.name == "axiomforge.resume_campaign"
