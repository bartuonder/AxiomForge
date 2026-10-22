import pytest

import app.graph.nodes as nodes
from app.sandbox.e2b_runner import SandboxCodeError

LINE = (
    "model={model} accuracy=0.9 f1=0.8 roc_auc={roc} pr_auc=0.8 "
    "train_seconds=1.0 tn=50 fp=5 fn=5 tp=40"
)
WILD = [0.95, 0.60, 0.97, 0.70, 0.99]
STEADY = [0.90, 0.91, 0.89, 0.92, 0.90]
SPEC = {"statement": "stmt", "dataset": "imbalanced", "models": ["A", "B"], "params": {}}
PROFILE = {"dataset": "d", "samples": 500.0, "features": 20.0, "negative_ratio": 0.9, "positive_ratio": 0.1}


def sandbox_output(a_values, b_values):
    lines = [LINE.format(model="A", roc=value) for value in a_values]
    lines += [LINE.format(model="B", roc=value) for value in b_values]
    return "\n".join(lines)


def base_state(**overrides):
    state = {
        "query": "Compare A and B",
        "hypotheses": ["stmt"],
        "experiment_specs": [SPEC],
        "current_experiment_code": "x = 1",
        "experiment_metrics": {"accuracy": 0.9, "f1": 0.8},
        "dataset_profile": PROFILE,
        "critic_rounds": 0,
    }
    state.update(overrides)
    return state


@pytest.fixture
def world(monkeypatch):
    class World:
        memory = []
        tracked = []
        failed = []
        leakage = (False, "")
        output = sandbox_output(WILD, STEADY)
        sandbox_error = None
        mlflow_error = None

    world = World()
    world.memory = []
    world.tracked = []
    world.failed = []

    def save(**kwargs):
        world.memory.append(kwargs)
        return "memory-id"

    def run(code, schema):
        if world.sandbox_error is not None:
            raise world.sandbox_error
        return world.output

    def track(*args, **kwargs):
        if world.mlflow_error is not None:
            raise world.mlflow_error
        world.tracked.append((args, kwargs))
        return "run-id"

    def track_failure(**kwargs):
        if world.mlflow_error is not None:
            raise world.mlflow_error
        world.failed.append(kwargs)
        return "failed-run-id"

    monkeypatch.setattr(nodes, "save_experiment", save)
    monkeypatch.setattr(nodes, "run_classification", run)
    monkeypatch.setattr(nodes, "judge_data_leakage", lambda code: world.leakage)
    monkeypatch.setattr(nodes, "log_verified_comparison", track)
    monkeypatch.setattr(nodes, "log_failed_run", track_failure)
    return world


def test_a_stable_run_passes_and_is_remembered_as_a_success(world):
    world.output = sandbox_output(STEADY, [0.91, 0.92, 0.90, 0.93, 0.91])
    result = nodes.verifier_node(base_state())
    assert result["verification_status"] == "Passed"
    assert result["critic_continue"] is False
    assert result["mlflow_run_id"] == "run-id"
    assert len(world.memory) == 1
    record = world.memory[0]
    assert record["outcome"] == "success"
    assert record["is_success"] is True
    assert record["finding"] == ""
    assert record["hypothesis"] == "stmt"
    assert record["spec"] == SPEC
    assert "A accuracy=" in record["metric"]


def test_high_variance_passes_as_a_finding_and_not_as_a_failure(world):
    result = nodes.verifier_node(base_state())
    assert result["verification_status"] == "Passed"
    assert result["critic_continue"] is False
    decision = result["statistical_decision"]
    assert decision["instability"]["unstable"] is True
    assert decision["outcome"] == "winner"
    assert decision["winner"] == "B"
    record = world.memory[0]
    assert record["outcome"] == "finding"
    assert record["is_success"] is True
    assert "A roc_auc" in record["finding"]


def test_the_decision_carries_the_performance_tests(world):
    result = nodes.verifier_node(base_state())
    assert {item["metric"] for item in result["statistical_decision"]["performance"]} == {
        "roc_auc",
        "pr_auc",
        "f1",
    }


def test_results_are_summarised_per_model(world):
    result = nodes.verifier_node(base_state())
    assert set(result["statistical_results"]) == {"A", "B", "statistical_conclusion"}
    assert result["statistical_results"]["B"]["roc_auc_mean"] == pytest.approx(sum(STEADY) / 5)


def test_leakage_sends_the_code_back_without_writing_memory(world):
    world.leakage = (True, "imputer fit before the split")
    result = nodes.verifier_node(base_state())
    assert result["verification_status"] == "Failed"
    assert result["critic_continue"] is True
    assert result["critic_rounds"] == 1
    assert "Leakage çözülemedi: imputer fit before the split" in result["verifier_feedback"]
    assert world.memory == []
    assert world.tracked == []
    assert world.failed == []


def test_the_last_round_records_one_failure_and_stops(world):
    world.leakage = (True, "leak")
    result = nodes.verifier_node(base_state(critic_rounds=2))
    assert result["verification_status"] == "Failed"
    assert result["critic_continue"] is False
    assert "critic_rounds" not in result
    assert len(world.memory) == 1
    record = world.memory[0]
    assert record["outcome"] == "failure"
    assert record["is_success"] is False
    assert "Leakage çözülemedi" in record["error_log"]
    assert result["mlflow_run_id"] == "failed-run-id"
    assert world.failed[0]["attempts"] == 3
    assert world.tracked == []


def test_a_crash_is_a_run_error_and_not_an_instability(world):
    world.sandbox_error = SandboxCodeError("kaboom")
    result = nodes.verifier_node(base_state())
    assert result["verification_status"] == "Failed"
    assert result["critic_continue"] is True
    assert "Çalışma hatası" in result["verifier_feedback"]
    assert "Kararsız" not in result["verifier_feedback"]


def test_a_missing_experiment_reports_the_real_error(world):
    state = base_state(
        current_experiment_code="",
        experiment_metrics={},
        experiment_error="models must be one dict literal",
    )
    result = nodes.verifier_node(state)
    assert result["verification_status"] == "Failed"
    assert result["verifier_feedback"] == "Deney metrik üretmedi. models must be one dict literal"


def test_a_missing_experiment_without_an_error_has_a_clean_message(world):
    state = base_state(current_experiment_code="", experiment_metrics={})
    result = nodes.verifier_node(state)
    assert result["verifier_feedback"] == "Deney metrik üretmedi."


def test_an_mlflow_outage_does_not_fail_the_research(world):
    world.mlflow_error = RuntimeError("mlflow down")
    result = nodes.verifier_node(base_state())
    assert result["verification_status"] == "Passed"
    assert result["mlflow_run_id"] == ""
    assert len(world.memory) == 1


def test_memory_is_written_before_mlflow(world):
    order = []
    original_save = nodes.save_experiment
    nodes.save_experiment = lambda **kwargs: (order.append("memory"), original_save(**kwargs))[1]
    original_track = nodes.log_verified_comparison
    nodes.log_verified_comparison = lambda *a, **k: (order.append("mlflow"), original_track(*a, **k))[1]
    nodes.verifier_node(base_state())
    assert order == ["memory", "mlflow"]


def test_the_script_split_loop_is_used_when_it_prints_five_rows(world):
    calls = []
    original = nodes.run_classification
    nodes.run_classification = lambda code, schema: (calls.append(1), original(code, schema))[1]
    nodes.verifier_node(base_state())
    assert len(calls) == 1


def test_a_script_without_a_loop_is_rerun_once_per_seed(world):
    world.output = sandbox_output([0.9], [0.9])
    calls = []
    original = nodes.run_classification
    nodes.run_classification = lambda code, schema: (calls.append(1), original(code, schema))[1]
    result = nodes.verifier_node(base_state())
    assert len(calls) == 6
    assert result["verification_status"] == "Passed"


def test_routes_follow_the_flags():
    assert nodes.route_after_verifier({"critic_continue": True}) == "experiment_node"
    assert nodes.route_after_verifier({"critic_continue": False}) == "report_node"
    assert nodes.route_after_verifier({}) == "report_node"
    assert nodes.route_after_consistency({"consistency_continue": True}) == "report_node"
    assert nodes.route_after_consistency({"consistency_continue": False}) == "end"


def test_the_first_spec_decides_the_hypothesis():
    statement, spec = nodes._primary_hypothesis(
        {"experiment_specs": [SPEC, {**SPEC, "statement": "other"}], "hypotheses": ["x"], "query": "q"}
    )
    assert (statement, spec) == ("stmt", SPEC)


def test_without_specs_the_first_hypothesis_or_the_query_is_used():
    assert nodes._primary_hypothesis({"hypotheses": ["only"], "query": "q"}) == ("only", None)
    assert nodes._primary_hypothesis({"hypotheses": [], "query": "q"}) == ("q", None)


@pytest.fixture
def experiment_calls(monkeypatch):
    calls = []

    def fake(prompt, schema, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {
            "code": "x = 1",
            "accuracy": 0.9,
            "f1": 0.8,
            "model_results": [{"model": "A"}, {"model": "B"}, {"model": "A"}],
            "dataset_profile": PROFILE,
        }

    monkeypatch.setattr(nodes, "execute_experiment", fake)
    return calls


def test_the_experiment_runs_the_approved_spec_without_side_effects(experiment_calls):
    state = base_state(query="Compare SVM and Random Forest")
    result = nodes.experiment_node(state)
    call = experiment_calls[0]
    assert call["spec"] == SPEC
    assert call["record_memory"] is False
    assert call["track_run"] is False
    assert [item["key"] for item in call["models"]] == ["SVM", "RandomForest"]
    assert "Hypothesis:\nstmt" in call["prompt"]
    assert "existing_code" not in call
    assert result["tested_models"] == ["A", "B"]
    assert result["experiment_metrics"] == {"accuracy": 0.9, "f1": 0.8}
    assert result["experiment_error"] == ""
    assert result["critic_continue"] is False


def test_a_critique_makes_the_experiment_correct_the_existing_code(experiment_calls):
    state = base_state(
        query="Compare SVM and Random Forest",
        verifier_feedback="Leakage çözülemedi: x",
        current_experiment_code="old code",
    )
    nodes.experiment_node(state)
    call = experiment_calls[0]
    assert call["existing_code"] == "old code"
    assert call["criticism"] == "Leakage çözülemedi: x"
    assert call["record_memory"] is False
    assert call["track_run"] is False


def test_a_failed_experiment_hands_its_error_to_the_verifier(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "execute_experiment",
        lambda prompt, schema, **kwargs: {"code": "bad", "status": "Failed", "error": "sandbox said no"},
    )
    result = nodes.experiment_node(base_state(query="Compare SVM and Random Forest"))
    assert result["experiment_error"] == "sandbox said no"
    assert result["experiment_metrics"] == {}
    assert result["tested_models"] == []


def test_the_planner_node_stores_statements_and_specs(monkeypatch):
    specs = [{**SPEC, "statement": f"h{index}"} for index in range(3)]
    seen = {}

    def fake_planner(query, literature, failed, models):
        seen["failed"] = failed
        seen["models"] = [item["key"] for item in models]
        return specs, "note"

    monkeypatch.setattr(
        nodes,
        "search_past_experiments",
        lambda query, k: [{"is_success": False, "error_log": "e"}, {"is_success": True}, {"is_success": None}],
    )
    monkeypatch.setattr(nodes, "run_planner_agent", fake_planner)
    result = nodes.planner_node({"query": "Compare SVM and KNN", "literature_context": ["paper"]})
    assert result == {"hypotheses": ["h0", "h1", "h2"], "experiment_specs": specs}
    assert seen["failed"] == [{"is_success": False, "error_log": "e"}]
    assert seen["models"] == ["SVM", "KNN"]


def paper_state(**overrides):
    state = {
        "paper_markdown": "A neutral paper.",
        "statistical_results": {},
        "statistical_decision": {"outcome": "tie"},
        "consistency_rounds": 0,
    }
    state.update(overrides)
    return state


def test_a_direction_conflict_never_reaches_the_llm_referee(monkeypatch):
    def forbidden(*args):
        raise AssertionError("the LLM referee must not run")

    monkeypatch.setattr(nodes, "judge_consistency", forbidden)
    result = nodes.consistency_checker_node(
        paper_state(paper_markdown="XGBoost is better than RandomForest.")
    )
    assert result["consistency_continue"] is True
    assert result["consistency_rounds"] == 1
    assert "Yön Çelişkisi" in result["consistency_feedback"]
    assert "research_status" not in result


def test_a_consistent_paper_completes_the_research(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))
    result = nodes.consistency_checker_node(paper_state())
    assert result["research_status"] == "Completed"
    assert result["consistency_continue"] is False
    assert result["consistency_feedback"] == ""


def test_the_referee_issues_trigger_a_rewrite(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (False, ["number mismatch"]))
    result = nodes.consistency_checker_node(paper_state())
    assert result["consistency_continue"] is True
    assert result["consistency_rounds"] == 1
    assert result["consistency_feedback"] == "number mismatch"


def test_after_two_rewrites_the_paper_needs_review(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (False, ["still wrong"]))
    result = nodes.consistency_checker_node(paper_state(consistency_rounds=2))
    assert result["research_status"] == "NeedsReview"
    assert result["consistency_continue"] is False
    assert result["consistency_feedback"] == "still wrong"


def test_a_winner_paper_that_omits_the_winner_is_sent_back(monkeypatch):
    monkeypatch.setattr(nodes, "judge_consistency", lambda *args: (True, []))
    state = paper_state(
        paper_markdown="RandomForest is steady.",
        statistical_decision={"outcome": "winner", "winner": "XGBoost"},
    )
    result = nodes.consistency_checker_node(state)
    assert result["consistency_continue"] is True
    assert "XGBoost" in result["consistency_feedback"]
