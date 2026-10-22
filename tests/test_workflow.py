import uuid

import pytest

from app.agents.experiment import QueryNamesNoModel
from app.graph.workflow import (
    _active_step,
    _research_status,
    _steps,
    empty_research_state,
    new_thread_id,
)

PLAN_READY = {"hypotheses": ["h1", "h2", "h3"], "literature_context": ["paper"]}


def status(values=None, next_nodes=(), error=""):
    return _research_status(values or {}, list(next_nodes), error)


def test_an_unknown_thread_is_starting():
    assert status() == "starting"


def test_a_running_thread_before_the_plan_is_running():
    assert status({"literature_context": ["paper"]}, ["planner_node"]) == "running"


def test_a_plan_waiting_at_the_gate_is_paused():
    assert status(PLAN_READY, ["approval_gate"]) == "paused"


def test_an_approved_plan_waiting_for_the_worker_is_running():
    values = {**PLAN_READY, "approval_status": "approved"}
    assert status(values, ["approval_gate"]) == "running"


def test_a_rejected_plan_is_rejected():
    values = {**PLAN_READY, "approval_status": "rejected"}
    assert status(values, ["approval_gate"]) == "rejected"


def test_an_error_marks_the_thread_failed():
    assert status(PLAN_READY, [], "boom") == "failed"
    assert status({**PLAN_READY, "approval_status": "approved"}, ["experiment_node"], "boom") == "failed"


def test_a_finished_paper_beats_a_recorded_error():
    assert status({"research_status": "Completed"}, [], "old error") == "completed"
    assert status({"research_status": "NeedsReview"}, [], "old error") == "needs_review"


def test_an_error_wins_over_a_rejection():
    values = {**PLAN_READY, "approval_status": "rejected"}
    assert status(values, [], "boom") == "failed"


def test_finished_threads_report_the_last_step():
    assert _active_step({}, [], "completed") == "consistency_checker_node"
    assert _active_step({}, [], "needs_review") == "consistency_checker_node"


def test_paused_and_rejected_threads_sit_on_the_planner():
    assert _active_step(PLAN_READY, ["approval_gate"], "paused") == "planner_node"
    assert _active_step(PLAN_READY, [], "rejected") == "planner_node"


@pytest.mark.parametrize(
    "node",
    [
        "consistency_checker_node",
        "report_node",
        "verifier_node",
        "experiment_node",
        "planner_node",
        "literature_node",
    ],
)
def test_the_pending_node_is_the_active_step(node):
    assert _active_step({}, [node], "running") == node


def test_an_approved_thread_without_code_is_in_the_experiment():
    assert _active_step({"approval_status": "approved"}, ["approval_gate"], "running") == "experiment_node"


def test_a_thread_with_code_is_being_verified():
    values = {"approval_status": "approved", "current_experiment_code": "x = 1"}
    assert _active_step(values, [], "running") == "verifier_node"


def test_a_verified_thread_is_in_the_report():
    values = {"current_experiment_code": "x = 1", "verification_status": "Passed"}
    assert _active_step(values, [], "running") == "report_node"


def test_a_rewrite_round_returns_to_the_report():
    values = {"paper_markdown": "paper", "consistency_continue": True, "verification_status": "Passed"}
    assert _active_step(values, [], "running") == "report_node"


def test_a_thread_with_nothing_is_in_the_literature():
    assert _active_step({}, [], "starting") == "literature_node"


def phases(steps):
    return {step["id"]: step["phase"] for step in steps}


def test_steps_start_with_the_literature_active():
    result = phases(_steps({}, [], "starting"))
    assert result["literature_node"] == "active"
    assert result["planner_node"] == "pending"


def test_steps_mark_the_plan_done_while_paused():
    values = {**PLAN_READY}
    result = phases(_steps(values, ["approval_gate"], "paused"))
    assert result["literature_node"] == "done"
    assert result["planner_node"] == "done"
    assert result["experiment_node"] == "pending"


def test_every_step_is_done_when_the_run_finished():
    values = {"research_status": "Completed"}
    assert set(phases(_steps(values, [], "completed")).values()) == {"done"}


def test_a_failed_run_shows_no_active_step():
    values = {**PLAN_READY, "approval_status": "approved"}
    assert "active" not in phases(_steps(values, [], "failed")).values()


def test_a_rejected_run_shows_no_active_step():
    values = {**PLAN_READY, "approval_status": "rejected"}
    assert "active" not in phases(_steps(values, [], "rejected")).values()


def test_a_verifier_that_will_loop_back_is_not_done():
    values = {
        **PLAN_READY,
        "current_experiment_code": "x = 1",
        "verification_status": "Failed",
        "critic_continue": True,
        "approval_status": "approved",
    }
    assert phases(_steps(values, ["experiment_node"], "running"))["verifier_node"] != "done"


def test_the_steps_keep_the_console_order():
    assert [step["id"] for step in _steps({}, [], "starting")] == [
        "literature_node",
        "planner_node",
        "experiment_node",
        "verifier_node",
        "report_node",
        "consistency_checker_node",
    ]


def test_a_fresh_state_is_empty_and_keeps_the_query():
    state = empty_research_state("Compare SVM and KNN")
    assert state["query"] == "Compare SVM and KNN"
    assert state["hypotheses"] == []
    assert state["experiment_specs"] == []
    assert state["tested_models"] == []
    assert state["statistical_results"] == {}
    assert state["critic_rounds"] == 0
    assert state["research_status"] == ""
    assert state["mlflow_run_id"] == ""
    assert state["experiment_error"] == ""


def test_fresh_states_do_not_share_mutable_values():
    first = empty_research_state("q")
    second = empty_research_state("q")
    first["hypotheses"].append("leak")
    assert second["hypotheses"] == []


def test_a_query_without_a_model_gets_no_thread():
    with pytest.raises(QueryNamesNoModel):
        new_thread_id("How does churn behave?")


def test_each_thread_gets_a_new_uuid():
    first = new_thread_id("Compare SVM and KNN")
    second = new_thread_id("Compare SVM and KNN")
    assert first != second
    assert str(uuid.UUID(first)) == first
