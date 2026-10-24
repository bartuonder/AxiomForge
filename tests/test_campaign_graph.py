from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import app.graph.nodes as nodes
import app.graph.workflow as workflow
import app.tasks as tasks
from app.agents.campaign_planner import CampaignUnsupported
from app.agents.experiment import QueryNamesTooFewModels
from app.graph.workflow import (
    _active_step,
    _research_status,
    _steps,
    empty_research_state,
    new_thread_id,
)

CANDIDATES = [
    {"spec": {"title": "First campaign", "datasets": ["a"]}, "estimate": {"estimated_seconds": 228}, "evidence": []},
    {"spec": {"title": "Second campaign", "datasets": ["b"]}, "estimate": {"estimated_seconds": 100}, "evidence": []},
    {"spec": {"title": "Third campaign", "datasets": ["c"]}, "estimate": {"estimated_seconds": 50}, "evidence": []},
]
SOURCES = [{"title": "A paper", "abstract": "Trees win.", "url": "https://arxiv.org/abs/1"}]
PLANNED = {"mode": "campaign", "literature_context": ["A paper: Trees win."], "campaign_specs": CANDIDATES}


def phases(steps):
    return {step["id"]: step["phase"] for step in steps}


class TestFreshState:
    def test_the_default_mode_is_the_single_dataset_experiment(self):
        assert empty_research_state("q")["mode"] == "experiment"

    def test_the_mode_is_stored(self):
        assert empty_research_state("q", "campaign")["mode"] == "campaign"

    def test_the_campaign_fields_start_empty(self):
        state = empty_research_state("q", "campaign")
        assert state["literature_sources"] == [] and state["campaign_specs"] == []
        assert state["selected_campaign"] == 0 and state["campaign_spec"] == {}
        assert state["campaign_id"] == "" and state["campaign_status"] == ""
        assert state["campaign_analysis"] == {} and state["campaign_ledger"] == [] and state["campaign_issues"] == []
        assert state["campaign_mlflow_run_id"] == ""

    def test_fresh_states_do_not_share_the_new_mutable_values(self):
        first, second = empty_research_state("q"), empty_research_state("q")
        first["campaign_specs"].append("leak")
        first["literature_sources"].append("leak")
        first["campaign_analysis"]["leak"] = 1
        first["campaign_ledger"].append("leak")
        first["campaign_issues"].append("leak")
        assert second["campaign_specs"] == [] and second["literature_sources"] == []
        assert second["campaign_analysis"] == {} and second["campaign_ledger"] == [] and second["campaign_issues"] == []


class TestThreadIds:
    def test_a_campaign_query_needs_no_model_names(self):
        assert new_thread_id("Replicate the claim of the tabular benchmark paper", "campaign")

    def test_an_experiment_query_still_needs_two_models(self):
        with pytest.raises(QueryNamesTooFewModels):
            new_thread_id("How does churn behave?")
        with pytest.raises(QueryNamesTooFewModels):
            new_thread_id("How does churn behave?", "experiment")

    def test_an_unknown_mode_is_refused_for_every_query(self):
        with pytest.raises(ValueError, match="mode must be one of: experiment, campaign"):
            new_thread_id("Compare SVM and KNN", "auto")
        with pytest.raises(ValueError):
            new_thread_id("anything", "")


class TestNodes:
    def test_the_literature_node_keeps_the_papers_and_their_text(self, monkeypatch):
        monkeypatch.setattr(nodes, "run_literature_search", lambda query: SOURCES)
        result = nodes.literature_node({"query": "q"})
        assert result == {"literature_context": ["A paper: Trees win."], "literature_sources": SOURCES}

    def test_the_campaign_planner_node_hands_the_sources_to_the_planner(self, monkeypatch):
        seen = []
        monkeypatch.setattr(nodes, "run_campaign_planner", lambda query, sources: seen.append((query, sources)) or CANDIDATES)
        result = nodes.campaign_planner_node({"query": "q", "literature_sources": SOURCES})
        assert result == {"campaign_specs": CANDIDATES} and seen == [("q", SOURCES)]

    def test_a_state_without_sources_gives_the_planner_an_empty_list(self, monkeypatch):
        seen = []
        monkeypatch.setattr(nodes, "run_campaign_planner", lambda query, sources: seen.append(sources) or CANDIDATES)
        nodes.campaign_planner_node({"query": "q"})
        assert seen == [[]]

    def test_an_unsupported_paper_stops_the_graph_with_its_reason(self, monkeypatch):
        def refuse(query, sources):
            raise CampaignUnsupported("the paper is about images")

        monkeypatch.setattr(nodes, "run_campaign_planner", refuse)
        with pytest.raises(CampaignUnsupported, match="images"):
            nodes.campaign_planner_node({"query": "q"})

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [("campaign", "campaign_planner_node"), ("experiment", "planner_node"), ("", "planner_node"), (None, "planner_node")],
    )
    def test_the_literature_hands_over_by_mode(self, mode, expected):
        assert nodes.route_after_literature({"mode": mode}) == expected

    def test_a_state_without_a_mode_is_an_experiment(self):
        assert nodes.route_after_literature({}) == "planner_node"
        assert nodes.route_after_approval({}) == "experiment"

    @pytest.mark.parametrize(("mode", "expected"), [("campaign", "campaign"), ("experiment", "experiment")])
    def test_the_approval_hands_over_by_mode(self, mode, expected):
        assert nodes.route_after_approval({"mode": mode}) == expected


@pytest.fixture
def run_graph(monkeypatch):
    calls = []

    def fake(name, update=None):
        def node(state):
            calls.append(name)
            return dict(update or {})

        return node

    monkeypatch.setattr(workflow, "literature_node", fake("literature", {"literature_context": ["p"], "literature_sources": SOURCES}))
    monkeypatch.setattr(workflow, "planner_node", fake("planner", {"hypotheses": ["h"], "experiment_specs": [{"statement": "h"}]}))
    monkeypatch.setattr(workflow, "campaign_planner_node", fake("campaign_planner", {"campaign_specs": CANDIDATES}))
    monkeypatch.setattr(workflow, "experiment_node", fake("experiment", {"current_experiment_code": "x"}))
    monkeypatch.setattr(workflow, "verifier_node", fake("verifier", {"verification_status": "Passed"}))
    monkeypatch.setattr(workflow, "report_node", fake("report", {"paper_markdown": "paper"}))
    monkeypatch.setattr(workflow, "consistency_checker_node", fake("consistency", {"research_status": "Completed"}))
    saver = InMemorySaver()
    compiled = workflow._compile(saver)
    return compiled, calls


class TestTopology:
    def config(self, name):
        return {"configurable": {"thread_id": name}}

    def test_an_experiment_pauses_at_the_gate_after_the_single_dataset_planner(self, run_graph):
        compiled, calls = run_graph
        compiled.invoke(empty_research_state("Compare SVM and KNN"), self.config("e"))
        assert calls == ["literature", "planner"]
        assert compiled.get_state(self.config("e")).next == ("approval_gate",)

    def test_an_approved_experiment_runs_the_whole_single_dataset_hat(self, run_graph):
        compiled, calls = run_graph
        config = self.config("e")
        compiled.invoke(empty_research_state("Compare SVM and KNN"), config)
        compiled.update_state(config, {"approval_status": "approved"})
        compiled.invoke(None, config)
        assert calls == ["literature", "planner", "experiment", "verifier", "report", "consistency"]
        assert compiled.get_state(config).values["research_status"] == "Completed"

    def test_a_campaign_pauses_at_the_gate_after_the_campaign_planner(self, run_graph):
        compiled, calls = run_graph
        compiled.invoke(empty_research_state("Replicate the paper", "campaign"), self.config("c"))
        assert calls == ["literature", "campaign_planner"]
        snapshot = compiled.get_state(self.config("c"))
        assert snapshot.next == ("approval_gate",) and snapshot.values["campaign_specs"] == CANDIDATES
        assert snapshot.values["literature_sources"] == SOURCES

    def test_a_campaign_never_touches_the_single_dataset_nodes(self, run_graph):
        compiled, calls = run_graph
        config = self.config("c")
        compiled.invoke(empty_research_state("Replicate the paper", "campaign"), config)
        compiled.update_state(config, {"approval_status": "approved", "selected_campaign": 1})
        compiled.invoke(None, config)
        assert calls == ["literature", "campaign_planner"]
        assert compiled.get_state(config).next == ()

    def test_the_single_dataset_planner_is_skipped_in_campaign_mode(self, run_graph):
        compiled, calls = run_graph
        compiled.invoke(empty_research_state("Replicate the paper", "campaign"), self.config("c"))
        assert "planner" not in calls


class TestCampaignStatus:
    def status(self, values, next_nodes=(), error=""):
        return _research_status(values, list(next_nodes), error)

    def test_planned_candidates_waiting_at_the_gate_are_paused(self):
        assert self.status(PLANNED, ["approval_gate"]) == "paused"

    def test_a_campaign_without_candidates_is_not_paused(self):
        assert self.status({"mode": "campaign"}, ["approval_gate"]) == "running"

    def test_an_approved_campaign_is_running(self):
        assert self.status({**PLANNED, "approval_status": "approved"}, ["approval_gate"]) == "running"

    def test_a_rejected_campaign_is_rejected(self):
        assert self.status({**PLANNED, "approval_status": "rejected"}) == "rejected"

    def test_the_final_statuses_are_shared_with_the_experiment_hat(self):
        assert self.status({"research_status": "Completed"}) == "completed"
        assert self.status({"research_status": "NeedsReview"}) == "needs_review"
        assert self.status(PLANNED, error="the paper is about images") == "failed"


class TestCampaignSteps:
    def active(self, values, next_nodes=(), status="running"):
        return _active_step({"mode": "campaign", **values}, list(next_nodes), status)

    def test_a_new_campaign_starts_in_the_literature(self):
        assert self.active({}, [], "starting") == "literature_node"

    def test_the_pending_nodes_map_to_console_steps(self):
        assert self.active({}, ["literature_node"]) == "literature_node"
        assert self.active({}, ["campaign_planner_node"]) == "campaign_planner_node"
        assert self.active({}, ["campaign_dispatch_node"]) == "campaign_node"
        assert self.active({}, ["campaign_collect_node"]) == "campaign_node"
        assert self.active({}, ["meta_report_node"]) == "meta_report_node"
        assert self.active({}, ["meta_consistency_node"]) == "meta_consistency_node"

    def test_a_paused_or_rejected_campaign_sits_on_the_planner(self):
        assert self.active(PLANNED, ["approval_gate"], "paused") == "campaign_planner_node"
        assert self.active(PLANNED, [], "rejected") == "campaign_planner_node"

    def test_a_finished_campaign_sits_on_the_last_step(self):
        assert self.active({}, [], "completed") == "meta_consistency_node"
        assert self.active({}, [], "needs_review") == "meta_consistency_node"

    def test_the_values_decide_between_nodes(self):
        assert self.active({"approval_status": "approved"}) == "campaign_node"
        assert self.active({"campaign_id": "abc"}) == "campaign_node"
        assert self.active({"campaign_analysis": {"claims": []}}) == "meta_report_node"
        assert self.active({"paper_markdown": "paper"}) == "meta_report_node"
        assert self.active({"campaign_specs": CANDIDATES}) == "campaign_planner_node"

    def test_the_steps_use_the_campaign_order(self):
        steps = _steps({"mode": "campaign"}, [], "starting")
        assert [step["id"] for step in steps] == ["literature_node", "campaign_planner_node", "campaign_node", "meta_report_node", "meta_consistency_node"]

    def test_a_paused_campaign_has_literature_and_plan_done(self):
        result = phases(_steps(PLANNED, ["approval_gate"], "paused"))
        assert result == {
            "literature_node": "done",
            "campaign_planner_node": "done",
            "campaign_node": "pending",
            "meta_report_node": "pending",
            "meta_consistency_node": "pending",
        }

    def test_a_running_campaign_shows_the_campaign_step_active(self):
        values = {**PLANNED, "approval_status": "approved", "campaign_id": "abc"}
        result = phases(_steps(values, ["campaign_collect_node"], "running"))
        assert result["campaign_node"] == "active" and result["meta_report_node"] == "pending"

    def test_a_collected_campaign_moves_on_to_the_report(self):
        values = {**PLANNED, "approval_status": "approved", "campaign_id": "abc", "campaign_analysis": {"claims": []}}
        result = phases(_steps(values, ["meta_report_node"], "running"))
        assert result["campaign_node"] == "done" and result["meta_report_node"] == "active"

    def test_a_rewrite_round_keeps_the_report_open(self):
        values = {**PLANNED, "campaign_analysis": {"claims": []}, "paper_markdown": "paper", "consistency_continue": True}
        assert phases(_steps(values, ["meta_report_node"], "running"))["meta_report_node"] != "done"

    def test_a_finished_campaign_is_done_everywhere(self):
        result = phases(_steps({"mode": "campaign", "research_status": "Completed"}, [], "completed"))
        assert set(result.values()) == {"done"}

    def test_failed_and_rejected_campaigns_have_no_active_step(self):
        values = {**PLANNED, "approval_status": "approved"}
        assert "active" not in phases(_steps(values, [], "failed")).values()
        assert "active" not in phases(_steps({**PLANNED, "approval_status": "rejected"}, [], "rejected")).values()

    def test_an_experiment_thread_keeps_its_six_steps(self):
        assert len(_steps({}, [], "starting")) == 6 and len(_steps({"mode": "experiment"}, [], "starting")) == 6


class FakeGraph:
    def __init__(self, values, next_nodes=("approval_gate",)):
        self.values = values
        self.next_nodes = tuple(next_nodes)
        self.updates = []

    def get_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next_nodes)

    def update_state(self, config, update):
        self.updates.append(update)
        self.values = {**self.values, **update}


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph({**PLANNED, "approval_status": ""})

    @contextmanager
    def opened():
        yield SimpleNamespace(setup=lambda: None)

    monkeypatch.setattr(workflow, "_open_graph", opened)
    monkeypatch.setattr(workflow, "_compile", lambda checkpointer: fake)
    monkeypatch.setattr(workflow, "read_error", lambda thread_id: "")
    return fake


class TestCampaignApproval:
    def test_approving_stores_the_chosen_spec_for_the_dispatcher(self, graph):
        result = workflow.decide_plan("t", "Y", 1)
        assert graph.updates == [{"approval_status": "approved", "selected_campaign": 1, "campaign_spec": CANDIDATES[1]["spec"]}]
        assert result == {
            "thread_id": "t",
            "status": "running",
            "approval_status": "approved",
            "selected_campaign": 1,
            "hypotheses": ["First campaign", "Second campaign", "Third campaign"],
        }

    @pytest.mark.parametrize("selected", [None, -1, 3, "1", True])
    def test_a_bad_selection_changes_nothing(self, graph, selected):
        with pytest.raises(ValueError):
            workflow.decide_plan("t", "Y", selected)
        assert graph.updates == []

    def test_rejecting_needs_no_selection_and_lists_the_titles(self, graph):
        result = workflow.decide_plan("t", "N")
        assert graph.updates == [{"approval_status": "rejected"}]
        assert result["hypotheses"] == ["First campaign", "Second campaign", "Third campaign"]

    def test_a_second_decision_is_refused(self, graph):
        workflow.decide_plan("t", "Y", 0)
        with pytest.raises(RuntimeError, match="already decided"):
            workflow.decide_plan("t", "Y", 2)

    def test_an_experiment_thread_still_stores_a_hypothesis_selection(self, graph):
        graph.values = {"hypotheses": ["a", "b"], "experiment_specs": [{"statement": "a"}, {"statement": "b"}], "approval_status": ""}
        workflow.decide_plan("t", "Y", 1)
        assert graph.updates == [{"approval_status": "approved", "selected_hypothesis": 1}]


class TestCampaignStatusReport:
    def test_the_status_carries_the_mode_the_candidates_and_the_selection(self, graph):
        status = workflow.get_research("t")
        assert status["mode"] == "campaign" and status["status"] == "paused"
        assert status["campaign_specs"] == CANDIDATES and status["selected_campaign"] == 0
        assert status["campaign_id"] == "" and status["campaign_status"] == ""
        assert [step["id"] for step in status["steps"]][1] == "campaign_planner_node"
        assert status["active_step"] == "campaign_planner_node"

    def test_the_selection_follows_the_approval(self, graph):
        workflow.decide_plan("t", "Y", 2)
        status = workflow.get_research("t")
        assert status["selected_campaign"] == 2 and status["status"] == "running"

    def test_an_out_of_range_stored_selection_falls_back_to_the_first(self, graph):
        graph.values["selected_campaign"] = 9
        assert workflow.get_research("t")["selected_campaign"] == 0

    def test_the_campaign_pointer_is_reported(self, graph):
        graph.values.update({"campaign_id": "abc", "campaign_status": "running", "approval_status": "approved"})
        graph.next_nodes = ("campaign_collect_node",)
        status = workflow.get_research("t")
        assert status["campaign_id"] == "abc" and status["campaign_status"] == "running" and status["active_step"] == "campaign_node"

    def test_an_old_thread_without_a_mode_reads_as_an_experiment(self, graph):
        graph.values = {"hypotheses": ["a"], "experiment_specs": [{"statement": "a"}], "approval_status": ""}
        status = workflow.get_research("t")
        assert status["mode"] == "experiment" and status["campaign_specs"] == [] and status["selected_campaign"] == 0


class TestTask:
    def test_the_research_task_passes_the_mode(self, monkeypatch):
        seen = []
        monkeypatch.setattr(tasks, "run_until_pause", lambda thread_id, query, mode: seen.append((thread_id, query, mode)))
        tasks.run_research_task("t", "q", "campaign")
        tasks.run_research_task("t2", "q2")
        assert seen == [("t", "q", "campaign"), ("t2", "q2", "experiment")]

    def test_the_pause_runner_starts_from_a_state_with_that_mode(self, monkeypatch):
        captured = {}

        class Saver:
            def setup(self):
                return None

        class Compiled:
            def get_state(self, config):
                return SimpleNamespace(values={})

            def invoke(self, fresh, config):
                captured["state"] = fresh
                return fresh

        @contextmanager
        def opened():
            yield Saver()

        monkeypatch.setattr(workflow, "_open_graph", opened)
        monkeypatch.setattr(workflow, "_compile", lambda saver: Compiled())
        workflow.run_until_pause("t", "q", "campaign")
        assert captured["state"]["mode"] == "campaign"
        workflow.run_until_pause("t", "q")
        assert captured["state"]["mode"] == "experiment"


class TestSurvivors:
    def test_a_stored_selection_equal_to_the_count_falls_back_to_the_first(self, graph):
        graph.values["selected_campaign"] = len(CANDIDATES)
        assert workflow.get_research("t")["selected_campaign"] == 0
        graph.values["selected_campaign"] = len(CANDIDATES) - 1
        assert workflow.get_research("t")["selected_campaign"] == 2

    @pytest.mark.parametrize("stored", ["1", None, 1.5, -1])
    def test_a_malformed_stored_selection_falls_back_to_the_first(self, graph, stored):
        graph.values["selected_campaign"] = stored
        assert workflow.get_research("t")["selected_campaign"] == 0

    def test_a_review_verdict_alone_closes_the_last_step(self):
        for verdict in ("Completed", "NeedsReview"):
            result = phases(_steps({"mode": "campaign", "research_status": verdict}, [], "running"))
            assert result["meta_consistency_node"] == "done"
