import argparse
import json
from typing import Any, Callable

from app.campaign import store
from app.campaign.benchmark import CASES
from app.campaign.hard_benchmark import near_cases

DEFAULT_MODEL = "gpt-4o"
VERDICTS = {"true": "replicated", "false": "contradicted", "unclear": "inconclusive"}
DECISIVE = ("replicated", "contradicted")


def prompt(query: str) -> str:
    return (
        "Judge the following claim about machine learning models using only what you already know, without running any experiment and without any data.\n"
        f"Claim: {query}\n"
        'Answer with JSON only: {"verdict": "true" | "false" | "unclear", "confidence": a number between 0 and 1}. '
        'Use "true" if the claim holds in general, "false" if the opposite holds in general, and "unclear" if neither direction is reliably the case.'
    )


def parse(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(cleaned)
    except ValueError:
        return "invalid"
    if not isinstance(value, dict):
        return "invalid"
    verdict = value.get("verdict")
    if not isinstance(verdict, str):
        return "invalid"
    return VERDICTS.get(verdict.strip().lower(), "invalid")


def cases(reference: dict[str, str]) -> list[dict[str, Any]]:
    result = [{"id": case["id"], "kind": "known", "query": case["query"], "reference": case["expected"]} for case in CASES]
    for case in near_cases():
        if case["id"] not in reference:
            raise ValueError(f"no reference verdict for {case['id']}")
        result.append({"id": case["id"], "kind": "near", "query": case["query"], "reference": reference[case["id"]], "pair": case["pair"]})
    return result


def evaluate(items: list[dict[str, Any]], complete: Callable[[str], str], repeats: int) -> dict[str, Any]:
    known = {"total": 0, "correct": 0, "wrong": 0, "abstained": 0}
    near = {"total": 0, "decisive": 0, "agree": 0, "false_certainty": 0, "pairs": 0, "both_true_pairs": 0}
    invalid = 0
    for _ in range(repeats):
        pair_answers: dict[int, list[str]] = {}
        for item in items:
            try:
                verdict = parse(complete(item["query"]))
            except Exception:
                verdict = "invalid"
            if verdict == "invalid":
                invalid += 1
            if item["kind"] == "known":
                known["total"] += 1
                known["correct"] += int(verdict == item["reference"])
                known["wrong"] += int(verdict in DECISIVE and verdict != item["reference"])
                known["abstained"] += int(verdict == "inconclusive")
                continue
            near["total"] += 1
            near["agree"] += int(verdict == item["reference"])
            if verdict in DECISIVE:
                near["decisive"] += 1
                near["false_certainty"] += int(item["reference"] == "inconclusive")
            pair_answers.setdefault(item["pair"], []).append(verdict)
        near["pairs"] += len(pair_answers)
        near["both_true_pairs"] += sum(1 for answers in pair_answers.values() if answers.count("replicated") == len(answers) and len(answers) == 2)
    known["accuracy"] = known["correct"] / known["total"] if known["total"] else 0.0
    return {"known": known, "near": near, "invalid": invalid}


def system_known(campaign_id: str) -> dict[str, Any]:
    analysis = store.load_analysis(campaign_id)
    if analysis is None:
        raise ValueError(f"campaign {campaign_id} has no stored analysis")
    verdicts = {claim["id"]: claim["verdict"] for claim in analysis.get("claims") or []}
    correct = sum(1 for case in CASES if verdicts.get(case["id"]) == case["expected"])
    return {"correct": correct, "total": len(CASES), "accuracy": correct / len(CASES)}


def reference_from(campaign_id: str) -> dict[str, str]:
    analysis = store.load_analysis(campaign_id)
    if analysis is None:
        raise ValueError(f"campaign {campaign_id} has no stored analysis")
    return {claim["id"]: claim["verdict"] for claim in analysis.get("claims") or []}


def make_complete(model: str) -> Callable[[str], str]:
    from openai import OpenAI

    from app.config import OPENAI_API_KEY

    client = OpenAI(api_key=OPENAI_API_KEY)

    def complete(query: str) -> str:
        response = client.chat.completions.create(model=model, temperature=0, response_format={"type": "json_object"}, messages=[{"role": "user", "content": prompt(query)}])
        return response.choices[0].message.content or ""

    return complete


def _report(model: str, llm: dict[str, Any], system: dict[str, Any]) -> str:
    near = llm["near"]
    known = llm["known"]
    return "\n".join(
        [
            f"model: {model}",
            f"known claims: LLM without data {known['correct']}/{known['total']} correct, {known['wrong']} wrong, {known['abstained']} abstained; the system on data {system['known']['correct']}/{system['known']['total']} correct",
            f"near-equal claims (data-based verdict is inconclusive for 10 of 14): the LLM called {near['decisive']}/{near['total']} claims true or false",
            f"false certainty (decisive answer where the data is inconclusive): {near['false_certainty']}/{near['total']}",
            f"pairs where the LLM called both directions true: {near['both_true_pairs']}/{near['pairs']}",
            f"agreement of the LLM with the data-based verdict on near-equal claims: {near['agree']}/{near['total']}",
            f"invalid answers: {llm['invalid']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask a language model the benchmark claims without data and compare it with the verdicts the system reached from data.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--known-campaign", default="benchmark-default")
    parser.add_argument("--near-campaign", default="near-default")
    parser.add_argument("--out")
    arguments = parser.parse_args(argv)
    if arguments.repeats < 1:
        print("repeats must be at least 1")
        return 2
    reference = reference_from(arguments.near_campaign)
    system = {"known": system_known(arguments.known_campaign), "near_reference": reference}
    llm = evaluate(cases(reference), make_complete(arguments.model), arguments.repeats)
    print(_report(arguments.model, llm, system))
    if arguments.out:
        with open(arguments.out, "w", encoding="utf-8") as stream:
            json.dump({"model": arguments.model, "repeats": arguments.repeats, "llm": llm, "system": system}, stream, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
