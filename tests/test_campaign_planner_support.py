import json

import pytest

import app.agents.campaign_planner as planner
from app.agents.campaign_planner import run_campaign_planner

ABSTRACT = "We show that tree-based models remain state-of-the-art on medium-sized data. It is much harder to tune neural networks than forests."
SOURCE = {"title": "Why do trees win", "abstract": ABSTRACT, "url": "https://arxiv.org/abs/2207.08815"}
QUOTE_GOOD = "tree-based models remain state-of-the-art on medium-sized data"
QUOTE_WEAK = "It is much harder to tune neural networks than forests"
QUERY = "Replicate the paper."
REAL_JUDGE = planner._judge_complete


def claim(quote=QUOTE_GOOD, **changes):
    base = {"statement": "Trees beat nets", "metrics": ["roc_auc"], "subject": ["Random Forest"], "other": ["MLP"], "source_quote": quote}
    return {**base, **changes}


def candidate(*claims, index=1, title="T"):
    return {"title": title, "source_index": index, "pool": "benchmark", "claims": list(claims) or [claim()]}


def answer(*candidates):
    return json.dumps({"unsupported": "", "candidates": list(candidates)})


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")


@pytest.fixture
def llm(monkeypatch):
    replies, prompts = [], []

    def complete(user):
        prompts.append(user)
        return replies.pop(0)

    monkeypatch.setattr(planner, "_complete", complete)
    return replies, prompts


@pytest.fixture
def judge(monkeypatch):
    replies, calls = [], []

    def complete(user):
        calls.append(user)
        return replies.pop(0)

    monkeypatch.setattr(planner, "_judge_complete", complete)
    return replies, calls


def verdicts(*items):
    return json.dumps({"verdicts": [{"id": number, "supports": supports, "reason": reason} for number, (supports, reason) in enumerate(items, start=1)]})


def run(llm, judge, candidates, verdict_replies, query=QUERY):
    llm[0].append(answer(*candidates))
    judge[0].extend(verdict_replies)
    return run_campaign_planner(query, [SOURCE])


def test_a_supported_claim_passes(llm, judge):
    result = run(llm, judge, [candidate()], [verdicts((True, "It states the comparison."))])
    assert len(result) == 1 and result[0]["spec"]["claims"][0]["quote"] == QUOTE_GOOD
    assert len(judge[1]) == 1


def test_the_judge_receives_the_claim_the_names_and_the_quote(llm, judge):
    run(llm, judge, [candidate(claim(statement="Trees beat nets", subject=["Random Forest", "XGBoost"], other=["Multilayer Perceptron"]))], [verdicts((True, "ok"))])
    payload = json.loads(judge[1][0])
    assert payload == {
        "claims": [
            {"id": 1, "statement": "Trees beat nets", "subject": ["Random Forest", "XGBoost"], "other": ["Multilayer Perceptron"], "quote": QUOTE_GOOD},
        ]
    }


def test_all_claims_of_a_candidate_are_judged_in_one_call(llm, judge):
    second = claim(QUOTE_WEAK, statement="Forests are easier to tune")
    run(llm, judge, [candidate(claim(), second)], [verdicts((True, "a"), (True, "b"))])
    payload = json.loads(judge[1][0])
    assert [item["id"] for item in payload["claims"]] == [1, 2] and len(judge[1]) == 1


def test_an_unsupported_claim_rejects_its_candidate_and_the_reason_reaches_the_retry(llm, judge):
    llm[0].append(answer(candidate(claim(QUOTE_WEAK, statement="Trees beat nets even when tuned"), title="Weak")))
    llm[0].append(answer(candidate(title="Good")))
    judge[0].extend([verdicts((False, "It speaks about tuning effort, not about scores.")), verdicts((True, "ok"))])
    result = run_campaign_planner(QUERY, [SOURCE])
    assert [item["spec"]["title"] for item in result] == ["Good"]
    assert "candidate 1:" in llm[1][1] and "claim C1" in llm[1][1] and "does not support the claim" in llm[1][1]
    assert "It speaks about tuning effort, not about scores." in llm[1][1]


def test_when_every_candidate_is_unsupported_the_planner_fails_with_the_reason(llm, judge):
    for _ in range(planner.MAX_PLAN_ATTEMPTS):
        llm[0].append(answer(candidate(claim(QUOTE_WEAK))))
        judge[0].append(verdicts((False, "Different topic.")))
    with pytest.raises(RuntimeError, match="Different topic"):
        run_campaign_planner(QUERY, [SOURCE])


def test_every_unsupported_claim_of_a_candidate_is_reported(llm, judge):
    llm[0].append(answer(candidate(claim(), claim(QUOTE_WEAK, statement="Another"), title="Weak")))
    llm[0].append(answer(candidate(title="Good")))
    judge[0].extend([verdicts((False, "First reason."), (False, "Second reason.")), verdicts((True, "ok"))])
    run_campaign_planner(QUERY, [SOURCE])
    assert "First reason." in llm[1][1] and "Second reason." in llm[1][1]


def test_a_claim_without_a_verdict_is_rejected(llm, judge):
    llm[0].append(answer(candidate(claim(), claim(QUOTE_WEAK, statement="Another"))))
    llm[0].append(answer(candidate()))
    judge[0].extend([verdicts((True, "ok")), verdicts((True, "ok"))])
    result = run_campaign_planner(QUERY, [SOURCE])
    assert len(result) == 1 and "claim C2" in llm[1][1] and "no verdict" in llm[1][1]


@pytest.mark.parametrize("flag", ["yes", 1, "true", None])
def test_only_a_boolean_true_counts_as_support(llm, judge, flag):
    llm[0].append(answer(candidate()))
    llm[0].append(answer(candidate(title="Second")))
    judge[0].extend([json.dumps({"verdicts": [{"id": 1, "supports": flag, "reason": "r"}]}), verdicts((True, "ok"))])
    result = run_campaign_planner(QUERY, [SOURCE])
    assert [item["spec"]["title"] for item in result] == ["Second"]


def test_a_claim_from_the_user_query_is_not_judged(llm, judge):
    quote = "Random forests beat the MLP on every dataset in my experience."
    result = run(llm, judge, [candidate(claim(quote), index=0)], [], query=f"{QUERY} {quote}")
    assert len(result) == 1 and judge[1] == []


def test_a_candidate_that_failed_earlier_checks_is_not_judged(llm, judge):
    llm[0].append(answer(candidate(claim("this quote is nowhere in the source text at all"))))
    llm[0].append(answer(candidate(claim("this quote is nowhere in the source text at all"))))
    llm[0].append(answer(candidate(claim("this quote is nowhere in the source text at all"))))
    with pytest.raises(RuntimeError):
        run_campaign_planner(QUERY, [SOURCE])
    assert judge[1] == []


@pytest.mark.parametrize("reply", ["not json", "[]", json.dumps({"verdicts": "x"}), json.dumps({"other": 1}), json.dumps({"verdicts": ["x"]})])
def test_a_broken_judge_answer_stops_the_planner(llm, judge, reply):
    llm[0].append(answer(candidate()))
    judge[0].append(reply)
    with pytest.raises(RuntimeError, match="support judge"):
        run_campaign_planner(QUERY, [SOURCE])


def test_a_long_reason_is_cut_in_the_feedback(llm, judge):
    llm[0].append(answer(candidate(title="Weak")))
    llm[0].append(answer(candidate(title="Good")))
    judge[0].extend([verdicts((False, "x" * 500)), verdicts((True, "ok"))])
    run_campaign_planner(QUERY, [SOURCE])
    assert "x" * 200 in llm[1][1] and "x" * 201 not in llm[1][1]


def test_a_missing_reason_is_tolerated(llm, judge):
    llm[0].append(answer(candidate(title="Weak")))
    llm[0].append(answer(candidate(title="Good")))
    judge[0].extend([json.dumps({"verdicts": [{"id": 1, "supports": False}]}), verdicts((True, "ok"))])
    assert run_campaign_planner(QUERY, [SOURCE])[0]["spec"]["title"] == "Good"
    assert "(no reason given)" in llm[1][1]


def test_the_judge_instruction_names_direction_and_unrelated_findings():
    prompt = planner.JUDGE_PROMPT
    assert "score higher" in prompt and "tuning effort" in prompt and "related finding" in prompt and "a different pair of model families, does not support the claim" in prompt and "opposite direction" in prompt
    assert 'Return only JSON: {"verdicts"' in prompt


def test_the_judge_asks_the_model_with_the_judge_prompt(monkeypatch):
    seen = {}

    class Message:
        content = json.dumps({"verdicts": []})

    class Choice:
        message = Message()

    class Completions:
        def create(self, **kwargs):
            seen.update(kwargs)
            return type("R", (), {"choices": [Choice()]})()

    class Client:
        def __init__(self, api_key):
            self.chat = type("C", (), {"completions": Completions()})()

    monkeypatch.setattr(planner, "OpenAI", Client)
    monkeypatch.setattr(planner, "_judge_complete", REAL_JUDGE)
    assert planner._judge_complete("payload") == json.dumps({"verdicts": []})
    assert seen["model"] == planner.MODEL and seen["temperature"] == 0 and seen["response_format"] == {"type": "json_object"}
    assert seen["messages"] == [{"role": "system", "content": planner.JUDGE_PROMPT}, {"role": "user", "content": "payload"}]
