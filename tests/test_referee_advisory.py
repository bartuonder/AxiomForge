from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import app.graph.nodes as nodes
import app.graph.workflow as workflow

CLEAN = "# Abstract\nWe compare two models.\n"
SUPERIOR = "# Abstract\nXGBoost is better than RandomForest.\n"


def state(paper=CLEAN, rounds=0, **overrides):
    base = {
        "paper_markdown": paper,
        "statistical_results": {},
        "statistical_decision": {"outcome": "tie"},
        "consistency_rounds": rounds,
        "verification_status": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def referee(monkeypatch):
    class Referee:
        calls = 0
        result = (False, ["a", "b"])
        error = None

    box = Referee()
    box.calls = 0

    def judge(*args):
        box.calls += 1
        if box.error is not None:
            raise box.error
        return box.result

    monkeypatch.setattr(nodes, "judge_consistency", judge)
    return box


def test_a_referee_that_objects_does_not_block_a_clean_paper(referee):
    referee.result = (False, ["a number looks off", "pr-auc is under-emphasised"])
    result = nodes.consistency_checker_node(state())
    assert result["research_status"] == "Completed"
    assert result["consistency_continue"] is False
    assert result["consistency_feedback"] == ""
    assert result["referee_notes"] == ["a number looks off", "pr-auc is under-emphasised"]


def test_a_referee_that_approves_leaves_no_notes(referee):
    referee.result = (True, [])
    result = nodes.consistency_checker_node(state())
    assert result["research_status"] == "Completed"
    assert result["referee_notes"] == []


def test_the_referee_is_not_asked_while_a_rewrite_is_pending(referee):
    result = nodes.consistency_checker_node(state(paper=SUPERIOR, rounds=0))
    assert result["consistency_continue"] is True
    assert result["consistency_rounds"] == 1
    assert referee.calls == 0
    assert "referee_notes" not in result


def test_the_referee_is_asked_once_when_the_paper_passes(referee):
    nodes.consistency_checker_node(state())
    assert referee.calls == 1


def test_the_referee_is_asked_once_when_the_rewrites_run_out(referee):
    result = nodes.consistency_checker_node(state(paper=SUPERIOR, rounds=2))
    assert result["research_status"] == "NeedsReview"
    assert result["referee_notes"] == ["a", "b"]
    assert referee.calls == 1


def test_only_the_deterministic_checks_decide_the_status(referee):
    referee.result = (True, [])
    assert nodes.consistency_checker_node(state(paper=SUPERIOR, rounds=2))["research_status"] == "NeedsReview"
    referee.result = (False, ["x"])
    assert nodes.consistency_checker_node(state(paper=CLEAN))["research_status"] == "Completed"


def test_the_feedback_to_the_writer_never_contains_a_referee_note(referee):
    referee.result = (False, ["referee secret note"])
    result = nodes.consistency_checker_node(state(paper=SUPERIOR, rounds=2))
    assert "referee secret note" not in result["consistency_feedback"]
    assert "Yön Çelişkisi" in result["consistency_feedback"]


def test_a_referee_that_crashes_does_not_fail_the_research(referee):
    referee.error = RuntimeError("invalid JSON from the referee")
    result = nodes.consistency_checker_node(state())
    assert result["research_status"] == "Completed"
    assert result["referee_notes"] == []


def test_a_referee_that_crashes_does_not_hide_a_real_problem(referee):
    referee.error = RuntimeError("boom")
    result = nodes.consistency_checker_node(state(paper=SUPERIOR, rounds=2))
    assert result["research_status"] == "NeedsReview"
    assert result["referee_notes"] == []


def test_notes_are_limited_in_number_and_length(referee):
    referee.result = (False, ["x" * 1000] + [f"note {i}" for i in range(20)])
    notes = nodes.consistency_checker_node(state())["referee_notes"]
    assert len(notes) == nodes.MAX_REFEREE_NOTES == 8
    assert len(notes[0]) == nodes.MAX_REFEREE_NOTE_LENGTH == 400
    assert notes[1] == "note 0"


def test_a_fresh_state_has_no_referee_notes():
    assert workflow.empty_research_state("q")["referee_notes"] == []


class FakeGraph:
    def __init__(self, values):
        self.values = values

    def get_state(self, config):
        return SimpleNamespace(values=self.values, next=())


def test_the_status_endpoint_returns_the_notes(monkeypatch):
    fake = FakeGraph({"research_status": "Completed", "referee_notes": ["one", "two"]})

    @contextmanager
    def opened():
        yield SimpleNamespace(setup=lambda: None)

    monkeypatch.setattr(workflow, "_open_graph", opened)
    monkeypatch.setattr(workflow, "_compile", lambda checkpointer: fake)
    monkeypatch.setattr(workflow, "read_error", lambda thread_id: "")
    assert workflow.get_research("t")["referee_notes"] == ["one", "two"]
    fake.values = {}
    assert workflow.get_research("t")["referee_notes"] == []
