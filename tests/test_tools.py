import importlib
import json

import pytest

import tools.bench_gate_loop as gate_loop
import tools.bench_planner_hard as planner_hard
import tools.sim_power as sim_power


@pytest.mark.parametrize("name", ["bench_gate_loop", "bench_planner_hard", "sim_power"])
def test_a_tool_can_be_imported_without_running_anything(name):
    module = importlib.import_module(f"tools.{name}")
    assert callable(module.main)


def stub_gate(monkeypatch, answers):
    monkeypatch.setattr(gate_loop.store, "load_analysis", lambda campaign_id: {"claims": []})
    monkeypatch.setattr(gate_loop.store, "load_ledger", lambda campaign_id: [])
    monkeypatch.setattr(gate_loop.store, "load_report", lambda campaign_id: "")
    monkeypatch.setattr(gate_loop, "write_prose", lambda *args: {"introduction": "i", "discussion": "d"})
    monkeypatch.setattr(gate_loop, "compose", lambda *args: "paper")
    iterator = iter(answers)
    monkeypatch.setattr(gate_loop, "meta_issues", lambda *args: next(iterator))


def test_the_gate_tool_refuses_an_unknown_campaign(monkeypatch, capsys):
    for loader in ("load_analysis", "load_ledger", "load_report"):
        monkeypatch.setattr(gate_loop.store, loader, lambda campaign_id: None)
    assert gate_loop.main(["nope", "1"]) == 2
    assert "nope has no stored analysis" in capsys.readouterr().out


def test_the_gate_tool_reports_the_draft_that_passed(monkeypatch, capsys):
    stub_gate(monkeypatch, [["issue"], [], [], ["issue"], ["issue"], ["issue"]])
    assert gate_loop.main(["any", "3"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert [line["passed_at_draft"] for line in lines] == [2, 1, None]
    assert lines[2]["last_issues"] == ["issue"]


def test_the_gate_tool_summary_counts_the_passes(monkeypatch, capsys):
    stub_gate(monkeypatch, [[]] * 4)
    gate_loop.main(["any", "4"])
    summary = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("SUMMARY"))
    assert json.loads(summary.split(" ", 1)[1]) == {"samples": 4, "passed": 4, "wilson95": [0.51, 1.0]}


def test_the_planner_tool_exits_zero_only_when_every_case_is_accepted(monkeypatch, capsys):
    from app.agents.campaign_planner import CampaignUnsupported

    def planner(query, sources, past):
        raise CampaignUnsupported("not about models")

    monkeypatch.setattr(planner_hard, "run_campaign_planner", planner)
    assert planner_hard.main() == 1
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    accepted = {line["id"]: line["accepted"] for line in lines}
    assert accepted["H7"] is True and accepted["H4"] is False and len(lines) == 8


def test_the_planner_tool_records_a_crash_as_a_rejected_case(monkeypatch, capsys):
    def planner(query, sources, past):
        raise RuntimeError("boom")

    monkeypatch.setattr(planner_hard, "run_campaign_planner", planner)
    assert planner_hard.main() == 1
    first = json.loads(next(line for line in capsys.readouterr().out.splitlines() if line.startswith("{")))
    assert first["outcome"] == "error" and "boom" in first["detail"]


def test_the_power_tool_runs_a_tiny_simulation(capsys):
    assert sim_power.main(["--replications", "2", "--splits", "3"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["scenario"] for line in lines] == list(sim_power.SCENARIOS)
    assert all(0.0 <= line["rejection_rate"] <= 1.0 and line["splits"] == 3 for line in lines)


@pytest.mark.parametrize("missing", ["load_analysis", "load_ledger", "load_report"])
def test_any_missing_part_of_the_campaign_is_refused(monkeypatch, capsys, missing):
    stub_gate(monkeypatch, [])
    monkeypatch.setattr(gate_loop.store, missing, lambda campaign_id: None)
    assert gate_loop.main(["half", "1"]) == 2


def test_the_gate_tool_allows_the_rewrite_rounds_of_the_pipeline(monkeypatch, capsys):
    stub_gate(monkeypatch, [["issue"], ["issue"], []])
    gate_loop.main(["any", "1"])
    line = json.loads(next(line for line in capsys.readouterr().out.splitlines() if line.startswith("{")))
    assert line["passed_at_draft"] == gate_loop.MAX_META_ROUNDS + 1


def test_a_rewrite_gets_the_issues_and_the_previous_text(monkeypatch):
    stub_gate(monkeypatch, [["first problem", "second problem"], []])
    calls = []
    monkeypatch.setattr(gate_loop, "write_prose", lambda *args: calls.append(args) or {"introduction": "i", "discussion": f"draft {len(calls)}"})
    gate_loop.main(["any", "1"])
    assert calls[0][5:] == ("", None)
    assert calls[1][5] == "first problem second problem" and calls[1][6] == {"introduction": "i", "discussion": "draft 1"}


def test_the_power_tool_counts_a_rejection_when_p_is_below_the_level(monkeypatch):
    monkeypatch.setattr(sim_power, "corrected_resampled_t", lambda *args: (0.0, 0.0, 0.01))
    monkeypatch.setattr(sim_power, "split_scores", lambda *args: ([0.5], [0.5]))
    assert sim_power.rejection_rate(None, None, 3, 4) == 1.0
    monkeypatch.setattr(sim_power, "corrected_resampled_t", lambda *args: (0.0, 0.0, 0.2))
    assert sim_power.rejection_rate(None, None, 3, 4) == 0.0


def test_the_power_tool_uses_the_requested_number_of_splits(monkeypatch):
    seen = []
    monkeypatch.setattr(sim_power, "split_scores", lambda features, labels, seeds, a, b: seen.append(len(seeds)) or ([0.5], [0.5]))
    monkeypatch.setattr(sim_power, "corrected_resampled_t", lambda *args: (0.0, 0.0, 0.5))
    sim_power.rejection_rate(None, None, 7, 2)
    assert seen == [7, 7]


def test_the_splits_are_stratified(monkeypatch):
    seen = {}
    real = sim_power.train_test_split

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(sim_power, "train_test_split", spy)
    features, labels = sim_power.make_classification(n_samples=100, n_features=5, random_state=0)
    sim_power.split_scores(features, labels, [1], lambda seed: sim_power.ExtraTreesClassifier(n_estimators=2, random_state=seed), lambda seed: sim_power.ExtraTreesClassifier(n_estimators=2, random_state=seed))
    assert seen["stratify"] is labels and seen["test_size"] == 0.2
