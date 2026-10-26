import json

import pytest

import app.agents.campaign_planner as planner
from app.agents.campaign_planner import run_campaign_planner
from app.campaign.spec import validate_campaign
from app.campaign.tuning import DEFAULT_FOLDS, DEFAULT_ITERATIONS

pytestmark = pytest.mark.usefixtures("approve_judge")

ABSTRACT = "We show that tree-based models remain state-of-the-art on medium-sized data."
SOURCE = {"title": "Why do trees win", "abstract": ABSTRACT, "url": "https://arxiv.org/abs/2207.08815", "citation": "Grinsztajn et al., arXiv:2207.08815 (2022)"}
QUOTE = "tree-based models remain state-of-the-art on medium-sized data"
QUERY = "Replicate the paper."


def claim(metrics=("roc_auc", "pr_auc", "f1"), **changes):
    base = {"statement": "Trees beat nets", "metrics": list(metrics), "subject": ["Random Forest"], "other": ["MLP"], "source_quote": QUOTE}
    return {**base, **changes}


def candidate(title="Base", metrics=("roc_auc", "pr_auc", "f1"), tuned=False, **changes):
    return {"title": title, "source_index": 1, "pool": "benchmark", "claims": [claim(metrics)], "tuned": tuned, **changes}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(planner, "FILL_VARIANTS", True)


@pytest.fixture
def llm(monkeypatch):
    replies = []
    monkeypatch.setattr(planner, "_complete", lambda user: replies.pop(0))
    return replies


def plan(llm, *candidates):
    llm.append(json.dumps({"unsupported": "", "candidates": list(candidates)}))
    return run_campaign_planner(QUERY, [SOURCE])


class TestFilling:
    def test_one_candidate_is_completed_to_three(self, llm):
        result = plan(llm, candidate())
        assert [item["spec"]["title"] for item in result] == ["Base", "Base (ROC-AUC only)", "Base (tuned)"]

    def test_the_roc_auc_variant_keeps_one_metric(self, llm):
        variant = plan(llm, candidate())[1]["spec"]
        assert [claim["metrics"] for claim in variant["claims"]] == [["roc_auc"]] and variant["claims"][0]["metric"] == "roc_auc"

    def test_the_tuned_variant_adds_the_default_search_and_swaps_the_note(self, llm):
        base, _, tuned = [item["spec"] for item in plan(llm, candidate())]
        assert tuned["tuning"] == {"iterations": DEFAULT_ITERATIONS, "folds": DEFAULT_FOLDS} and not base["tuning"]
        assert base["source"]["deviations"][0].startswith("No hyperparameter search")
        assert tuned["source"]["deviations"][0].startswith("Each model was tuned")
        assert tuned["source"]["deviations"][1:] == base["source"]["deviations"][1:]

    def test_the_variants_keep_the_claims_the_source_and_the_quote(self, llm):
        base, roc, tuned = [item["spec"] for item in plan(llm, candidate())]
        for variant in (roc, tuned):
            assert variant["models"] == base["models"] and variant["datasets"] == base["datasets"]
            assert variant["source"]["title"] == base["source"]["title"] and variant["source"]["citation"] == base["source"]["citation"]
            assert variant["claims"][0]["statement"] == base["claims"][0]["statement"] and variant["claims"][0]["quote"] == QUOTE

    def test_every_variant_is_a_valid_specification_with_its_own_estimate(self, llm):
        result = plan(llm, candidate())
        for item in result:
            assert validate_campaign(item["spec"]) == item["spec"]
        assert result[2]["estimate"]["estimated_seconds"] > result[0]["estimate"]["estimated_seconds"]
        assert result[1]["estimate"]["datasets"] == result[0]["estimate"]["datasets"]

    def test_the_variants_share_the_evidence_of_their_base(self, llm):
        result = plan(llm, candidate())
        assert all(item["evidence"] == result[0]["evidence"] for item in result)

    def test_a_base_with_one_metric_skips_the_metric_variant(self, llm):
        result = plan(llm, candidate(metrics=("roc_auc",)))
        assert [item["spec"]["title"] for item in result] == ["Base", "Base (tuned)"]
        assert not any(item["spec"]["title"] == "Base (ROC-AUC only)" for item in result)

    def test_a_tuned_base_skips_the_tuned_variant(self, llm):
        result = plan(llm, candidate(tuned=True))
        titles = [item["spec"]["title"] for item in result]
        assert "Base (tuned)" not in titles and "Base (ROC-AUC only)" in titles

    def test_two_candidates_get_one_variant(self, llm):
        result = plan(llm, candidate("One"), candidate("Two", claims=[claim(statement="Trees beat linear models", other=["LogisticRegression"])]))
        assert [item["spec"]["title"] for item in result] == ["One", "Two", "One (ROC-AUC only)"]

    def test_three_candidates_get_none(self, llm):
        result = plan(
            llm,
            candidate("One"),
            candidate("Two", claims=[claim(statement="b", other=["LogisticRegression"])]),
            candidate("Three", claims=[claim(statement="c", other=["KNN"])]),
        )
        assert [item["spec"]["title"] for item in result] == ["One", "Two", "Three"]

    def test_a_variant_that_repeats_a_candidate_is_not_added_twice(self, llm):
        result = plan(llm, candidate("One"), candidate("Two", metrics=("roc_auc",)))
        titles = [item["spec"]["title"] for item in result]
        assert len(titles) == 3 and len({tuple(item["spec"]["claims"][0]["metrics"]) + (bool(item["spec"]["tuning"]),) for item in result}) == 3

    def test_the_switch_turns_the_filling_off(self, llm, monkeypatch):
        monkeypatch.setattr(planner, "FILL_VARIANTS", False)
        assert len(plan(llm, candidate())) == 1

    def test_variants_carry_the_repeat_marks(self, llm, monkeypatch):
        monkeypatch.setattr(planner, "find_repeats", lambda spec, past: ["old-run"])
        assert all(item["repeats"] == ["old-run"] for item in plan(llm, candidate()))

    def test_a_query_claim_is_varied_too_but_stays_without_a_source(self, llm):
        quote = "Random forests beat the MLP on every dataset in my experience."
        llm.append(json.dumps({"unsupported": "", "candidates": [candidate(index=0, **{"claims": [claim(source_quote=quote)], "source_index": 0})]}))
        result = run_campaign_planner(f"{QUERY} {quote}", [SOURCE])
        assert len(result) == 3 and all("title" not in item["spec"]["source"] for item in result)
        assert all("quote" not in item["spec"]["claims"][0] for item in result)


def test_a_variant_that_would_break_the_title_limit_is_left_out(llm):
    result = plan(llm, candidate("T" * 155))
    assert [item["spec"]["title"] for item in result] == ["T" * 155]


def test_variants_come_from_a_later_candidate_when_the_first_cannot_vary(llm):
    first = candidate("First", metrics=("roc_auc",), tuned=True)
    second = candidate("Second", claims=[claim(statement="Trees beat linear models", other=["LogisticRegression"])])
    result = plan(llm, first, second)
    assert [item["spec"]["title"] for item in result] == ["First", "Second", "Second (ROC-AUC only)"]


def test_the_filling_is_on_by_default():
    import importlib.util

    loader = importlib.util.spec_from_file_location("fresh_planner", planner.__file__)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    assert module.FILL_VARIANTS is True


def test_the_signature_distinguishes_tuned_from_plain(llm):
    plain, _, tuned = plan(llm, candidate())
    assert planner._signature(plain) != planner._signature(tuned)
