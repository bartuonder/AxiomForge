from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import app.agents.campaign_planner as planner
import app.campaign.memory as memory
import app.graph.campaign_nodes as campaign_nodes
import app.graph.workflow as workflow
from app.campaign.analysis import analyze_campaign
from app.campaign.memory import claim_signatures, find_repeats, past_campaigns, remember_campaign, verdict_summary

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Tree-based models beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc"],
     "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"], "subject": ["MLP"], "other": ["LogisticRegression"]},
]
SPEC = {"title": "Trees against networks", "models": MODELS, "claims": CLAIMS, "datasets": ["a"], "source": {}}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h", "tb_pol", "tb_eye"]
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}


def analysis():
    def summary(shift):
        return {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}

    data = {
        "order": KEYS,
        "datasets": {
            key: {"summary": summary(0.001 * index), "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5}, "seconds": 1.0, "attempts": 1, "script": "s"}
            for index, key in enumerate(KEYS)
        },
        "failed": {},
    }
    return analyze_campaign(SPEC, data)


class TestSignatures:
    def test_order_inside_a_claim_does_not_matter(self):
        first = claim_signatures({"claims": [{"subject": ["B", "A"], "other": ["C"], "metrics": ["f1", "roc_auc"]}]})
        second = claim_signatures({"claims": [{"subject": ["A", "B"], "other": ["C"], "metrics": ["roc_auc", "f1"]}]})
        assert first == second

    def test_a_single_metric_key_counts_as_one_metric(self):
        assert claim_signatures({"claims": [{"subject": ["A"], "other": ["B"], "metric": "f1"}]}) == {(("A",), ("B",), ("f1",))}

    def test_different_groups_or_metrics_are_different_claims(self):
        base = {"subject": ["A"], "other": ["B"], "metrics": ["f1"]}
        assert claim_signatures({"claims": [base]}) != claim_signatures({"claims": [{**base, "other": ["C"]}]})
        assert claim_signatures({"claims": [base]}) != claim_signatures({"claims": [{**base, "metrics": ["roc_auc"]}]})
        assert claim_signatures({"claims": [base]}) != claim_signatures({"claims": [{"subject": ["B"], "other": ["A"], "metrics": ["f1"]}]})

    def test_order_inside_the_other_group_does_not_matter_either(self):
        first = claim_signatures({"claims": [{"subject": ["A"], "other": ["C", "B"], "metrics": ["f1"]}]})
        second = claim_signatures({"claims": [{"subject": ["A"], "other": ["B", "C"], "metrics": ["f1"]}]})
        assert first == second

    def test_a_spec_without_claims_has_none(self):
        assert claim_signatures({}) == set()


class TestVerdictSummary:
    def test_it_lists_each_claim_with_its_verdict(self):
        assert verdict_summary(analysis()) == "C1 replicated; C2 replicated"

    def test_without_claims_it_says_nothing_was_assessed(self):
        assert verdict_summary({"error": "x"}) == "no claim could be assessed"
        assert verdict_summary({"claims": []}) == "no claim could be assessed"

    def test_a_partial_verdict_reads_naturally(self):
        assert verdict_summary({"claims": [{"id": "C1", "verdict": "partially_replicated"}]}) == "C1 partially replicated"


class TestRemember:
    def test_the_record_carries_the_title_the_claims_the_verdicts_and_the_spec(self, monkeypatch):
        saved = []
        monkeypatch.setattr(memory, "save_experiment", lambda **kwargs: saved.append(kwargs) or "memory-1")
        assert remember_campaign(SPEC, analysis(), "Completed") == "memory-1"
        record = saved[0]
        assert record["hypothesis"] == "Trees against networks: Tree-based models beat the MLP; The MLP beats logistic regression"
        assert record["metric"] == "C1 replicated; C2 replicated" and record["outcome"] == "campaign"
        assert record["is_success"] is True and record["code"] == "" and record["error_log"] == ""
        assert record["spec"] == SPEC
        assert record["finding"] == "Review status Completed. HistGradientBoosting ranked first overall."

    def test_a_campaign_without_ranks_has_a_finding_without_a_leader(self, monkeypatch):
        saved = []
        monkeypatch.setattr(memory, "save_experiment", lambda **kwargs: saved.append(kwargs) or "m")
        remember_campaign(SPEC, {"error": "no dataset finished"}, "NeedsReview")
        assert saved[0]["finding"] == "Review status NeedsReview." and saved[0]["metric"] == "no claim could be assessed"


class TestPast:
    RECORDS = [
        {"outcome": "campaign", "spec": SPEC, "hypothesis": "h", "metric": "C1 replicated; C2 replicated"},
        {"outcome": "success", "spec": {"title": "single"}, "hypothesis": "x", "metric": "m"},
        {"outcome": "campaign", "spec": {}, "hypothesis": "no spec", "metric": "m"},
        {"outcome": "campaign", "spec": {"claims": []}, "hypothesis": "untitled", "metric": "C1 inconclusive"},
    ]

    def test_only_campaign_records_with_a_spec_are_returned(self, monkeypatch):
        monkeypatch.setattr(memory, "search_past_experiments", lambda query, k: self.RECORDS)
        past = past_campaigns("tabular")
        assert [item["title"] for item in past] == ["Trees against networks", "untitled"]
        assert past[0]["verdicts"] == "C1 replicated; C2 replicated" and past[0]["spec"] == SPEC

    def test_the_default_limit_is_five(self):
        assert memory.PAST_LIMIT == 5

    def test_the_search_uses_the_query_and_the_limit(self, monkeypatch):
        seen = []
        monkeypatch.setattr(memory, "search_past_experiments", lambda query, k: seen.append((query, k)) or [])
        past_campaigns("my question")
        past_campaigns("other", limit=2)
        assert seen == [("my question", memory.PAST_LIMIT), ("other", 2)]

    def test_a_memory_outage_means_no_past_campaigns(self, monkeypatch):
        def broken(query, k):
            raise ConnectionError("database is down")

        monkeypatch.setattr(memory, "search_past_experiments", broken)
        assert past_campaigns("q") == []

    def test_in_tests_the_real_memory_is_refused_and_so_nothing_is_found(self):
        assert past_campaigns("anything") == []


class TestRepeats:
    def test_a_shared_claim_marks_the_past_campaign_as_a_repeat(self):
        past = [{"title": "Earlier run", "spec": SPEC, "verdicts": "x"}]
        assert find_repeats({"claims": [CLAIMS[0], {**CLAIMS[1], "other": ["KNN"]}]}, past) == ["Earlier run"]

    def test_a_new_claim_is_no_repeat(self):
        past = [{"title": "Earlier run", "spec": SPEC, "verdicts": "x"}]
        assert find_repeats({"claims": [{**CLAIMS[0], "metrics": ["f1"]}]}, past) == []

    def test_several_past_campaigns_are_listed_in_order(self):
        past = [{"title": "One", "spec": SPEC, "verdicts": ""}, {"title": "Two", "spec": {"claims": [CLAIMS[0]]}, "verdicts": ""}, {"title": "Three", "spec": {"claims": []}, "verdicts": ""}]
        assert find_repeats(SPEC, past) == ["One", "Two"]

    def test_without_a_past_there_is_nothing_to_repeat(self):
        assert find_repeats(SPEC, []) == []


ABSTRACT = "While deep learning has enabled tremendous progress on text and image datasets, tree-based models remain state-of-the-art on medium-sized data, even without accounting for their superior speed."
SOURCES = [{"title": "Why do trees win", "abstract": ABSTRACT, "url": ""}]
QUOTE = "tree-based models remain state-of-the-art on medium-sized data"


def candidate():
    import json

    return json.dumps({
        "unsupported": "",
        "candidates": [{
            "title": "Trees against networks",
            "source_index": 1,
            "pool": "benchmark",
            "claims": [{"statement": "Tree-based models beat the MLP", "metrics": ["roc_auc", "pr_auc"], "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"], "source_quote": QUOTE}],
        }],
    })


def test_the_planner_node_searches_the_past_with_the_query(monkeypatch):
    import app.graph.nodes as nodes

    seen = []
    monkeypatch.setattr(nodes, "past_campaigns", lambda query: seen.append(query) or [])
    monkeypatch.setattr(nodes, "run_campaign_planner", lambda query, sources, past: [])
    nodes.campaign_planner_node({"query": "my question"})
    assert seen == ["my question"]


@pytest.mark.usefixtures("approve_judge")
class TestPlanner:
    @pytest.fixture
    def llm(self, monkeypatch):
        prompts = []
        monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")
        monkeypatch.setattr(planner, "_complete", lambda user: prompts.append(user) or candidate())
        return prompts

    def test_past_campaigns_are_listed_in_the_prompt(self, llm):
        past = [{"title": "Earlier run", "spec": SPEC, "verdicts": "C1 replicated; C2 replicated"}]
        planner.run_campaign_planner("q", SOURCES, past)
        assert "Campaigns that were already run on similar questions. Do not propose the same claim again unless the user query asks to repeat it:" in llm[0]
        assert "- Earlier run: Tree-based models beat the MLP; The MLP beats logistic regression (C1 replicated; C2 replicated)" in llm[0]

    def test_without_a_past_the_prompt_has_no_such_section(self, llm):
        planner.run_campaign_planner("q", SOURCES)
        planner.run_campaign_planner("q", SOURCES, [])
        assert all("already run" not in prompt for prompt in llm)

    def test_a_candidate_that_repeats_a_past_claim_is_marked_not_dropped(self, llm):
        past = [{"title": "Earlier run", "spec": {"claims": [{"subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"], "metrics": ["roc_auc", "pr_auc"]}]}, "verdicts": ""}]
        plan = planner.run_campaign_planner("q", SOURCES, past)
        assert len(plan) == 1 and plan[0]["repeats"] == ["Earlier run"]

    def test_a_new_candidate_has_no_repeats(self, llm):
        plan = planner.run_campaign_planner("q", SOURCES, [{"title": "Other", "spec": {"claims": []}, "verdicts": ""}])
        assert plan[0]["repeats"] == []
        assert planner.run_campaign_planner("q", SOURCES)[0]["repeats"] == []


class TestNodes:
    def state(self, **changes):
        return {"campaign_spec": SPEC, "campaign_analysis": analysis(), "consistency_rounds": 0, "campaign_issues": [], "campaign_status": "completed", **changes}

    @pytest.fixture
    def written(self, monkeypatch):
        calls = []
        monkeypatch.setattr(campaign_nodes, "remember_campaign", lambda spec, analysis, status: calls.append(status))
        monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: [])
        return calls

    def test_the_memory_receives_the_spec_and_the_analysis_of_the_run(self, monkeypatch):
        seen = []
        monkeypatch.setattr(campaign_nodes, "remember_campaign", lambda spec, analysis, status: seen.append((spec, analysis, status)))
        monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: [])
        current = self.state()
        campaign_nodes.meta_consistency_node(current)
        assert seen == [(current["campaign_spec"], current["campaign_analysis"], "Completed")]

    def test_a_completed_campaign_is_remembered_once(self, written):
        campaign_nodes.meta_consistency_node(self.state())
        assert written == ["Completed"]

    def test_a_campaign_for_review_is_remembered_as_such(self, written):
        campaign_nodes.meta_consistency_node(self.state(campaign_status="needs_review"))
        assert written == ["NeedsReview"]

    def test_a_rewrite_round_remembers_nothing(self, written, monkeypatch):
        monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: ["a problem"])
        campaign_nodes.meta_consistency_node(self.state())
        assert written == []

    def test_the_final_failed_round_is_remembered_as_needing_review(self, written, monkeypatch):
        monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: ["a problem"])
        campaign_nodes.meta_consistency_node(self.state(consistency_rounds=campaign_nodes.MAX_META_ROUNDS))
        assert written == ["NeedsReview"]

    def test_a_memory_outage_does_not_change_the_verdict(self, monkeypatch, caplog):
        def broken(spec, analysis, status):
            raise ConnectionError("database is down")

        monkeypatch.setattr(campaign_nodes, "remember_campaign", broken)
        monkeypatch.setattr(campaign_nodes, "meta_issues", lambda *args: [])
        with caplog.at_level("ERROR", logger="axiomforge"):
            update = campaign_nodes.meta_consistency_node(self.state())
        assert update["research_status"] == "Completed"
        assert any("could not be written to the memory" in record.getMessage() for record in caplog.records)

    def test_a_state_without_a_spec_writes_nothing(self, written):
        campaign_nodes.meta_consistency_node({})
        assert written == []


class FakeGraph:
    def __init__(self, values, next_nodes=("campaign_collect_node",)):
        self.values = values
        self.next_nodes = tuple(next_nodes)

    def get_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next_nodes)


def test_the_status_carries_the_mlflow_run_of_the_campaign(monkeypatch):
    fake = FakeGraph({"mode": "campaign", "campaign_id": "g-1", "campaign_status": "completed", "campaign_mlflow_run_id": "run-7"})

    @contextmanager
    def opened():
        yield SimpleNamespace(setup=lambda: None)

    monkeypatch.setattr(workflow, "_open_graph", opened)
    monkeypatch.setattr(workflow, "_compile", lambda checkpointer: fake)
    monkeypatch.setattr(workflow, "read_error", lambda thread_id: "")
    assert workflow.get_research("t")["campaign_mlflow_run_id"] == "run-7"
    fake.values = {"mode": "campaign"}
    assert workflow.get_research("t")["campaign_mlflow_run_id"] == ""
