import json

import pytest

import app.agents.campaign_planner as planner
from app.agents.campaign_planner import CANDIDATES, MAX_PLAN_ATTEMPTS, CampaignUnsupported, run_campaign_planner
from app.datasets import benchmark_keys, core_keys

pytestmark = pytest.mark.usefixtures("approve_judge")

ABSTRACT_ONE = (
    "While deep learning has enabled tremendous progress on text and image datasets, its superiority on tabular data is not clear. "
    "We show that tree-based models remain state-of-the-art on medium-sized data, even without accounting for their superior speed."
)
ABSTRACT_TWO = "We study ensembles. Gradient boosted trees are better than neural networks on small tabular problems according to our experiments."
SOURCES = [
    {"title": "Why do tree-based models still outperform deep learning on tabular data?", "abstract": ABSTRACT_ONE, "url": "https://arxiv.org/abs/2207.08815"},
    {"title": "Ensembles on small tables", "abstract": ABSTRACT_TWO, "url": ""},
]
QUERY = "Check whether tree-based models beat the ResNet on tabular data. Random forests are also better than linear models in my experience."
QUOTE_ONE = "tree-based models remain state-of-the-art on medium-sized data"
QUOTE_TWO = "Gradient boosted trees are better than neural networks on small tabular problems"


def claim(**changes):
    base = {
        "statement": "Tree-based models outperform neural networks on tabular data",
        "metrics": ["roc_auc", "pr_auc", "f1"],
        "subject": ["Random Forest", "HistGradientBoosting"],
        "other": ["MLP"],
        "source_quote": QUOTE_ONE,
    }
    return {**base, **changes}


def candidate(**changes):
    base = {"title": "Trees against networks", "source_index": 1, "pool": "benchmark", "claims": [claim()]}
    return {**base, **changes}


def answer(*candidates, unsupported=""):
    return json.dumps({"unsupported": unsupported, "candidates": list(candidates)})


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")


@pytest.fixture
def llm(monkeypatch):
    replies = []
    prompts = []

    def complete(user):
        prompts.append(user)
        return replies.pop(0)

    monkeypatch.setattr(planner, "_complete", complete)
    return replies, prompts


def three():
    return answer(
        candidate(title="All three metrics"),
        candidate(title="ROC-AUC only", claims=[claim(metrics=["roc_auc"])]),
        candidate(title="Linear models too", claims=[claim(), claim(statement="Trees beat linear models", other=["LogisticRegression"], source_quote=QUOTE_ONE)]),
    )


def test_three_valid_candidates_come_back_with_spec_estimate_and_evidence(llm):
    replies, prompts = llm
    replies.append(three())
    plan = run_campaign_planner(QUERY, SOURCES)
    assert [item["spec"]["title"] for item in plan] == ["All three metrics", "ROC-AUC only", "Linear models too"]
    first = plan[0]
    assert first["spec"]["models"] == ["RandomForest", "HistGradientBoosting", "MLP"]
    assert first["spec"]["datasets"] == benchmark_keys()
    assert first["spec"]["source"]["title"] == SOURCES[0]["title"] and first["spec"]["source"]["url"] == "https://arxiv.org/abs/2207.08815"
    assert first["estimate"]["datasets"] == 9 and first["estimate"]["estimated_seconds"] > 0
    assert first["evidence"] == [{"claim": "C1", "quote": QUOTE_ONE, "source": SOURCES[0]["title"]}]
    assert len(prompts) == 1


def test_the_prompt_lists_numbered_sources_and_the_query_and_the_system_prompt_the_estimators(llm):
    replies, prompts = llm
    replies.append(three())
    run_campaign_planner(QUERY, SOURCES)
    assert f"User query:\n{QUERY}" in prompts[0]
    assert f"[1] {SOURCES[0]['title']}: {ABSTRACT_ONE}" in prompts[0] and f"[2] {SOURCES[1]['title']}" in prompts[0]
    assert "HistGradientBoosting" in planner.SYSTEM_PROMPT and "exactly 3 different candidate" in planner.SYSTEM_PROMPT


def test_a_missing_key_stops_before_any_call(monkeypatch):
    monkeypatch.setattr(planner, "OPENAI_API_KEY", "")
    monkeypatch.setattr(planner, "_complete", lambda user: pytest.fail("called"))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is missing"):
        run_campaign_planner(QUERY, SOURCES)


def test_no_candidates_means_unsupported_and_carries_the_reason(llm):
    replies, _ = llm
    replies.append(answer(unsupported="The paper is about image segmentation."))
    with pytest.raises(CampaignUnsupported, match="image segmentation"):
        run_campaign_planner(QUERY, SOURCES)
    assert replies == []


def test_unsupported_without_a_reason_still_says_something(llm):
    replies, _ = llm
    replies.append(answer())
    with pytest.raises(CampaignUnsupported, match="no claim a campaign can test"):
        run_campaign_planner(QUERY, SOURCES)


def test_invalid_json_and_a_wrong_shape_are_reported(llm):
    replies, _ = llm
    replies.append("not json")
    with pytest.raises(RuntimeError, match="invalid JSON"):
        run_campaign_planner(QUERY, SOURCES)
    for wrong in (json.dumps({"candidates": "nope"}), json.dumps([1, 2])):
        for _ in range(MAX_PLAN_ATTEMPTS):
            replies.append(wrong)
        with pytest.raises(RuntimeError, match="did not return candidates"):
            run_campaign_planner(QUERY, SOURCES)
        assert replies == []


def test_a_quote_that_is_not_in_the_source_rejects_the_candidate_and_the_error_is_fed_back(llm):
    replies, prompts = llm
    invented = candidate(title="Invented", claims=[claim(source_quote="trees are always better than every neural network ever built")])
    replies.append(answer(candidate(title="Good one"), candidate(title="Good two", claims=[claim(metrics=["roc_auc"])]), invented))
    replies.append(answer(candidate(title="Replacement", claims=[claim(metrics=["f1"])])))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert [item["spec"]["title"] for item in plan] == ["Good one", "Good two", "Replacement"]
    assert "candidate 3:" in prompts[1] and "does not appear in the source text" in prompts[1]


def test_a_quote_is_matched_ignoring_case_and_whitespace(llm):
    replies, _ = llm
    messy = "  TREE-BASED models   remain\nstate-of-the-art on medium-sized DATA "
    replies.append(answer(candidate(claims=[claim(source_quote=messy)])))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert plan[0]["evidence"][0]["quote"] == messy.strip()


def test_a_short_or_missing_quote_is_refused(llm):
    replies, _ = llm
    for bad in ("trees win", "", None, 5):
        for _ in range(MAX_PLAN_ATTEMPTS):
            replies.append(answer(candidate(claims=[claim(source_quote=bad)])))
        with pytest.raises(RuntimeError, match="no valid campaign"):
            run_campaign_planner(QUERY, SOURCES)


def test_a_quote_from_another_source_does_not_count(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(source_index=2)))
    with pytest.raises(RuntimeError, match="does not appear in the source text"):
        run_campaign_planner(QUERY, SOURCES)


def test_the_second_source_is_used_when_the_index_says_so(llm):
    replies, _ = llm
    replies.append(answer(candidate(source_index=2, claims=[claim(source_quote=QUOTE_TWO, subject=["gradient boosted trees"], other=["neural networks"])])))
    plan = run_campaign_planner(QUERY, SOURCES)
    spec = plan[0]["spec"]
    assert spec["source"] == {"title": "Ensembles on small tables", "deviations": spec["source"]["deviations"]}
    assert spec["claims"][0]["subject"] == ["HistGradientBoosting"] and spec["claims"][0]["other"] == ["MLP"]
    assert any("gradient boosted trees was represented" in note for note in spec["source"]["deviations"])
    assert any("neural networks was represented" in note for note in spec["source"]["deviations"])


def test_a_claim_taken_from_the_query_has_no_source_paper(llm):
    replies, _ = llm
    quoted = "Random forests are also better than linear models in my experience"
    replies.append(answer(candidate(source_index=0, claims=[claim(source_quote=quoted, subject=["RandomForest"], other=["linear models"])])))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert "title" not in plan[0]["spec"]["source"] and plan[0]["spec"]["source"]["deviations"]
    assert plan[0]["evidence"][0]["source"] == "user query"


def test_a_query_claim_must_be_quoted_from_the_query(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(source_index=0)))
    with pytest.raises(RuntimeError, match="does not appear in the source text"):
        run_campaign_planner(QUERY, SOURCES)


@pytest.mark.parametrize("index", [3, -1, "1", None, 1.0, True])
def test_a_bad_source_index_is_refused(llm, index):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(source_index=index)))
    with pytest.raises(RuntimeError, match="source_index must be a whole number from 0 to 2"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_model_the_engine_cannot_run_is_named_and_never_guessed(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(subject=["TabNet", "RandomForest"])])))
    with pytest.raises(RuntimeError, match="cannot be run by the campaign engine: TabNet"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_deep_architecture_becomes_the_mlp_with_a_deviation_note(llm):
    replies, _ = llm
    replies.append(answer(candidate(claims=[claim(subject=["RandomForest"], other=["ResNet", "FT-Transformer"])])))
    spec = run_campaign_planner(QUERY, SOURCES)[0]["spec"]
    assert spec["models"] == ["RandomForest", "MLP"] and spec["claims"][0]["other"] == ["MLP"]
    notes = spec["source"]["deviations"]
    assert "ResNet was represented by scikit-learn's MLPClassifier." in notes and "FT-Transformer was represented by scikit-learn's MLPClassifier." in notes


def test_two_groups_that_map_to_the_same_estimator_are_refused(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(subject=["ResNet", "RandomForest"], other=["MLP"])])))
    with pytest.raises(RuntimeError, match="compares a model with itself"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_single_estimator_on_both_sides_is_refused_as_too_few_models(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(subject=["ResNet"], other=["MLP"])])))
    with pytest.raises(RuntimeError, match="needs at least two models"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_string_instead_of_a_list_is_accepted_for_a_group(llm):
    replies, _ = llm
    replies.append(answer(candidate(claims=[claim(subject="RandomForest", other="MLP")])))
    assert run_campaign_planner(QUERY, SOURCES)[0]["spec"]["claims"][0]["subject"] == ["RandomForest"]


@pytest.mark.parametrize("group", [[], "", [""], [1], None, 5])
def test_an_empty_or_malformed_group_is_refused(llm, group):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(subject=group)])))
    with pytest.raises(RuntimeError, match="claim subject must be a model name or a list of model names"):
        run_campaign_planner(QUERY, SOURCES)


def test_an_unknown_metric_is_refused_by_the_spec_validation(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(metrics=["accuracy"])])))
    with pytest.raises(RuntimeError, match="metrics must come from"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_statement_and_a_title_are_required(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(statement=None)])))
    with pytest.raises(RuntimeError, match="statement"):
        run_campaign_planner(QUERY, SOURCES)
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(title="  ")))
    with pytest.raises(RuntimeError, match="title"):
        run_campaign_planner(QUERY, SOURCES)


def test_the_pool_all_gives_ten_datasets_and_core_alone_lacks_power(llm):
    replies, _ = llm
    replies.append(answer(candidate(pool="all")))
    assert run_campaign_planner(QUERY, SOURCES)[0]["spec"]["datasets"] == benchmark_keys() + core_keys()[:1]
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(pool="core")))
    with pytest.raises(RuntimeError, match="5 datasets cannot reach"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_missing_pool_means_the_benchmark_and_an_unknown_one_is_refused(llm):
    replies, _ = llm
    replies.append(answer({k: v for k, v in candidate().items() if k != "pool"}))
    assert run_campaign_planner(QUERY, SOURCES)[0]["spec"]["datasets"] == benchmark_keys()
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(pool="everything")))
    with pytest.raises(RuntimeError, match="pool must be one of: benchmark, core, all"):
        run_campaign_planner(QUERY, SOURCES)


@pytest.mark.parametrize("claims", [[], [claim(), claim(), claim()], "nope", None])
def test_a_candidate_needs_one_or_two_claims(llm, claims):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=claims)))
    with pytest.raises(RuntimeError, match="needs one to 2 claims"):
        run_campaign_planner(QUERY, SOURCES)


def test_malformed_items_are_refused_without_crashing(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer("text", candidate(claims=["text"])))
    with pytest.raises(RuntimeError, match="each candidate must be an object.*each claim must be an object"):
        run_campaign_planner(QUERY, SOURCES)


def test_duplicate_candidates_are_returned_once(llm):
    replies, _ = llm
    replies.append(answer(candidate(title="A"), candidate(title="B"), candidate(title="C", claims=[claim(metrics=["f1"])])))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert [item["spec"]["title"] for item in plan] == ["A", "C"]


def test_two_valid_candidates_without_errors_are_returned_without_asking_again(llm):
    replies, prompts = llm
    replies.append(answer(candidate(title="A"), candidate(title="C", claims=[claim(metrics=["f1"])])))
    assert len(run_campaign_planner(QUERY, SOURCES)) == 2 and len(prompts) == 1


def test_only_the_first_three_candidates_are_considered(llm):
    replies, _ = llm
    extra = [candidate(title=f"T{n}", claims=[claim(statement=f"claim number {n}")]) for n in range(5)]
    replies.append(answer(*extra))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert [item["spec"]["title"] for item in plan] == ["T0", "T1", "T2"] and len(plan) == CANDIDATES


def test_every_attempt_failing_reports_all_errors_after_the_attempt_limit(llm):
    replies, prompts = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(pool="nope")))
    with pytest.raises(RuntimeError, match="candidate 1: pool must be one of"):
        run_campaign_planner(QUERY, SOURCES)
    assert len(prompts) == MAX_PLAN_ATTEMPTS and "pool must be one of" in prompts[1]


def test_a_rejected_candidate_never_makes_the_good_ones_fail(llm):
    replies, _ = llm
    replies.append(answer(candidate(title="Good"), candidate(pool="nope")))
    for _ in range(MAX_PLAN_ATTEMPTS - 1):
        replies.append(answer(candidate(pool="nope")))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert [item["spec"]["title"] for item in plan] == ["Good"]


def test_a_source_without_a_link_gets_no_url(llm):
    replies, _ = llm
    replies.append(answer(candidate(source_index=2, claims=[claim(source_quote=QUOTE_TWO, subject=["gradient boosted trees"], other=["neural networks"])])))
    assert "url" not in run_campaign_planner(QUERY, SOURCES)[0]["spec"]["source"]


def test_the_planner_works_without_any_source_paper(llm):
    replies, prompts = llm
    quoted = "Random forests are also better than linear models in my experience"
    replies.append(answer(candidate(source_index=0, claims=[claim(source_quote=quoted, subject=["RandomForest"], other=["linear models"])])))
    run_campaign_planner(QUERY, [])
    assert "No source paper was found." in prompts[0]


def test_a_quote_that_is_short_but_really_in_the_source_is_still_refused(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(source_quote="tree-based models")])))
    with pytest.raises(RuntimeError, match="source_quote of at least 20 characters"):
        run_campaign_planner(QUERY, SOURCES)


def test_padding_does_not_make_a_short_quote_long_enough(llm):
    replies, _ = llm
    padded = "tree-based" + " " * 40
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(source_quote=padded)])))
    with pytest.raises(RuntimeError, match="source_quote of at least 20 characters"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_note_shared_by_two_claims_is_written_once(llm):
    replies, _ = llm
    first = claim(subject=["RandomForest"], other=["ResNet"])
    second = claim(statement="Boosting beats the ResNet", subject=["HistGradientBoosting"], other=["ResNet"])
    replies.append(answer(candidate(claims=[first, second])))
    notes = run_campaign_planner(QUERY, SOURCES)[0]["spec"]["source"]["deviations"]
    assert notes.count("ResNet was represented by scikit-learn's MLPClassifier.") == 1


def test_the_evidence_of_a_two_claim_candidate_follows_the_claim_ids(llm):
    replies, _ = llm
    replies.append(three())
    plan = run_campaign_planner(QUERY, SOURCES)
    assert [item["claim"] for item in plan[2]["evidence"]] == ["C1", "C2"]
    assert plan[2]["evidence"][1]["quote"] == QUOTE_ONE


def test_the_model_is_asked_deterministically_for_json(monkeypatch):
    seen = {}

    class Completions:
        def create(self, **kwargs):
            seen.update(kwargs)
            message = type("Message", (), {"content": "{}"})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    class Client:
        def __init__(self, api_key):
            seen["key"] = api_key
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(planner, "OpenAI", Client)
    assert planner._complete("hello") == "{}"
    assert seen["temperature"] == 0 and seen["response_format"] == {"type": "json_object"} and seen["model"] == planner.MODEL
    assert seen["key"] == "key"
    assert seen["messages"] == [{"role": "system", "content": planner.SYSTEM_PROMPT}, {"role": "user", "content": "hello"}]


def test_the_feedback_tells_the_model_what_to_do_with_the_rejections(llm):
    replies, prompts = llm
    replies.append(answer(candidate(title="Good"), candidate(pool="nope")))
    replies.append(answer(candidate(title="Other", claims=[claim(metrics=["f1"])])))
    run_campaign_planner(QUERY, SOURCES)
    assert "were rejected, propose replacements:\n- candidate 2: pool must be one of" in prompts[1]
    assert "rejected" not in prompts[0]


def test_the_final_error_lists_only_the_last_attempt(llm):
    replies, _ = llm
    replies.append(answer(candidate(pool="nope")))
    for _ in range(MAX_PLAN_ATTEMPTS - 1):
        replies.append(answer(candidate(claims=[claim(metrics=["accuracy"])])))
    with pytest.raises(RuntimeError) as caught:
        run_campaign_planner(QUERY, SOURCES)
    assert "metrics must come from" in str(caught.value) and "pool must be one of" not in str(caught.value)


def test_the_prompt_lets_the_planner_take_a_claim_from_the_query_itself():
    prompt = planner.SYSTEM_PROMPT
    assert "When the user query itself states a comparison claim" in prompt
    assert "propose that claim with source_index 0 and quote the query" in prompt
    assert "prefer a source paper only when its abstract states the claim" in prompt
    assert "Never invent a claim that the sources and the query do not state" in prompt


def test_an_answer_without_a_candidates_list_is_asked_for_again_with_the_reason(llm):
    replies, prompts = llm
    replies.append(json.dumps({"unsupported": "the query itself states a claim, but I returned no list"}))
    replies.append(three())
    plan = run_campaign_planner(QUERY, SOURCES)
    assert len(plan) == 3 and len(prompts) == 2
    assert "must be a JSON object with a candidates list" in prompts[1] and "rejected" in prompts[1]
    assert "rejected" not in prompts[0]


def test_the_prompt_requires_the_candidates_key_in_every_answer():
    assert "The key candidates is required in every answer; fill unsupported only when candidates is an empty list." in planner.SYSTEM_PROMPT


def test_an_empty_candidates_list_with_a_reason_is_still_unsupported_without_a_retry(llm):
    replies, prompts = llm
    replies.append(json.dumps({"unsupported": "about images", "candidates": []}))
    with pytest.raises(CampaignUnsupported, match="about images"):
        run_campaign_planner(QUERY, SOURCES)
    assert len(prompts) == 1


QUERY_CLAIM = "Random forests are also better than linear models in my experience"


def test_a_quote_taken_from_the_query_is_never_credited_to_the_paper_the_model_pointed_at(llm):
    replies, _ = llm
    replies.append(answer(candidate(source_index=1, claims=[claim(source_quote=QUERY_CLAIM, subject=["RandomForest"], other=["linear models"])])))
    plan = run_campaign_planner(QUERY, SOURCES)
    spec = plan[0]["spec"]
    assert "title" not in spec["source"] and "url" not in spec["source"] and spec["source"]["deviations"]
    assert plan[0]["evidence"][0]["source"] == "user query"


def test_a_quote_found_in_the_chosen_paper_keeps_the_paper_as_the_source(llm):
    replies, _ = llm
    replies.append(answer(candidate(source_index=1)))
    plan = run_campaign_planner(QUERY + " " + QUOTE_ONE, SOURCES)
    assert plan[0]["spec"]["source"]["title"] == SOURCES[0]["title"]
    assert plan[0]["evidence"][0]["source"] == SOURCES[0]["title"]


def test_claims_quoted_from_different_origins_cannot_share_a_candidate(llm):
    replies, _ = llm
    mixed = candidate(source_index=1, claims=[claim(), claim(statement="Boosting beats linear models", subject=["HistGradientBoosting"], other=["LogisticRegression"], source_quote=QUERY_CLAIM)])
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(mixed))
    with pytest.raises(RuntimeError, match="must all be quoted from the same origin"):
        run_campaign_planner(QUERY, SOURCES)


def test_two_claims_from_the_query_share_an_origin_and_are_accepted(llm):
    replies, _ = llm
    first = claim(source_quote="Check whether tree-based models beat the ResNet on tabular data", subject=["RandomForest"], other=["ResNet"])
    second = claim(statement="Random forests beat linear models", source_quote=QUERY_CLAIM, subject=["RandomForest"], other=["linear models"])
    replies.append(answer(candidate(source_index=0, claims=[first, second])))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert [item["source"] for item in plan[0]["evidence"]] == ["user query", "user query"]


def test_the_planner_tries_three_times(llm):
    assert MAX_PLAN_ATTEMPTS == 3


@pytest.mark.parametrize(
    "decorated",
    [QUOTE_ONE + ".", f'"{QUOTE_ONE}"', QUOTE_ONE + "...", QUOTE_ONE + "…", f"“{QUOTE_ONE}”", f"  {QUOTE_ONE};  ", f"'{QUOTE_ONE}!'"],
)
def test_punctuation_around_a_quote_does_not_make_it_fail(llm, decorated):
    replies, _ = llm
    replies.append(answer(candidate(claims=[claim(source_quote=decorated)])))
    plan = run_campaign_planner(QUERY, SOURCES)
    assert plan[0]["evidence"][0]["quote"] == QUOTE_ONE


def test_punctuation_does_not_make_a_short_quote_long_enough(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(answer(candidate(claims=[claim(source_quote="tree-based models........................")])))
    with pytest.raises(RuntimeError, match="source_quote of at least 20 characters"):
        run_campaign_planner(QUERY, SOURCES)


def test_a_model_that_only_refuses_gets_three_chances_and_its_reason_is_kept(llm):
    replies, prompts = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(json.dumps({"unsupported": "The paper is not among the sources."}))
    with pytest.raises(CampaignUnsupported, match="The paper is not among the sources."):
        run_campaign_planner(QUERY, SOURCES)
    assert len(prompts) == MAX_PLAN_ATTEMPTS and replies == []


def test_a_refusal_followed_by_candidates_is_accepted(llm):
    replies, _ = llm
    replies.append(json.dumps({"unsupported": "no list"}))
    replies.append(three())
    assert len(run_campaign_planner(QUERY, SOURCES)) == 3


def test_a_blank_refusal_is_not_a_reason(llm):
    replies, _ = llm
    for _ in range(MAX_PLAN_ATTEMPTS):
        replies.append(json.dumps({"unsupported": "   "}))
    with pytest.raises(RuntimeError, match="did not return candidates") as caught:
        run_campaign_planner(QUERY, SOURCES)
    assert not isinstance(caught.value, CampaignUnsupported)


def test_the_prompt_says_irrelevant_sources_are_no_reason_to_refuse():
    prompt = planner.SYSTEM_PROMPT
    assert "irrelevant sources are no reason to answer unsupported" in prompt
    assert "Use unsupported only when neither the sources nor the query state any comparison" in prompt


def test_the_prompt_asks_for_variations_when_fewer_than_three_claims_exist():
    prompt = planner.SYSTEM_PROMPT
    assert "If the sources and the query allow fewer than three different claims" in prompt
    assert "vary the model groups, the metrics or the comparison" in prompt


def test_the_prompt_maps_unrunnable_architectures_instead_of_refusing_them():
    prompt = planner.SYSTEM_PROMPT
    assert "transformers, ResNet or other deep networks, are mapped to the MLP stand-in" in prompt
    assert "never answer unsupported because of an architecture that is not in the list" in prompt


def test_the_prompt_never_inverts_a_negated_statement():
    prompt = planner.SYSTEM_PROMPT
    assert "A negated statement such as 'X does not outperform Y' is not the claim that Y outperforms X" in prompt
    assert "propose the affirmative claim 'X outperforms Y'" in prompt and "never invert the direction" in prompt
