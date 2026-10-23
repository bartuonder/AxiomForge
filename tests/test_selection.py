import pytest

from app.agents.report import _brief
from app.graph.selection import primary_hypothesis, selected_index, validate_selection

SPECS = [
    {"statement": "first", "dataset": "breast_cancer", "models": ["A"], "params": {}},
    {"statement": "second", "dataset": "customer_churn", "models": ["A"], "params": {"A": {"C": 2}}},
    {"statement": "third", "dataset": "breast_cancer", "models": ["A"], "params": {}},
]


def state(**overrides):
    base = {"query": "q", "hypotheses": ["first", "second", "third"], "experiment_specs": SPECS}
    base.update(overrides)
    return base


def test_without_a_selection_the_first_spec_is_used():
    assert primary_hypothesis(state()) == ("first", SPECS[0])


@pytest.mark.parametrize("index", [0, 1, 2])
def test_the_selected_spec_is_used(index):
    statement, spec = primary_hypothesis(state(selected_hypothesis=index))
    assert spec == SPECS[index]
    assert statement == SPECS[index]["statement"]


def test_an_out_of_range_selection_falls_back_to_the_first():
    assert selected_index(state(selected_hypothesis=5)) == 0
    assert selected_index(state(selected_hypothesis=-1)) == 0
    assert selected_index(state(selected_hypothesis="1")) == 0


def test_without_specs_the_selected_hypothesis_or_the_query_is_used():
    legacy = {"hypotheses": ["only", "other"], "query": "q"}
    assert primary_hypothesis(legacy) == ("only", None)
    assert primary_hypothesis({**legacy, "selected_hypothesis": 1}) == ("other", None)
    assert primary_hypothesis({"hypotheses": [], "query": "q"}) == ("q", None)


@pytest.mark.parametrize("selected", [0, 1, 2])
def test_a_valid_selection_is_returned(selected):
    assert validate_selection(3, selected) == selected


@pytest.mark.parametrize("selected", [-1, 3, 10, None, "1", 1.0, True])
def test_an_invalid_selection_is_rejected(selected):
    with pytest.raises(ValueError):
        validate_selection(3, selected)


def test_nothing_can_be_selected_when_there_are_no_hypotheses():
    with pytest.raises(ValueError):
        validate_selection(0, 0)


def test_the_report_brief_carries_only_the_selected_hypothesis():
    brief = _brief(state(selected_hypothesis=1), [], "run")
    assert '["second"]' in brief
    assert "first" not in brief
    assert "third" not in brief
    assert '"customer_churn"' in brief
    assert '"C": 2' in brief
