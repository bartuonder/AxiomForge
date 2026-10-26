import argparse
import json

from app.agents.consistency_meta import meta_issues
from app.agents.meta_report import compose, write_prose
from app.campaign import store
from app.campaign.benchmark import benchmark_spec
from app.campaign.hard_benchmark import wilson_interval
from app.graph.campaign_nodes import MAX_META_ROUNDS

QUERY = "Check ten known comparison claims between tabular classifiers: random forests, boosting, trees, naive Bayes, nearest neighbours and a neural network."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure how often the meta paper passes its gate within the rewrite rounds.")
    parser.add_argument("campaign", help="id of a stored benchmark campaign")
    parser.add_argument("samples", type=int)
    arguments = parser.parse_args(argv)
    spec = benchmark_spec()
    analysis = store.load_analysis(arguments.campaign)
    ledger = store.load_ledger(arguments.campaign)
    report = store.load_report(arguments.campaign)
    if analysis is None or ledger is None or report is None:
        print(f"campaign {arguments.campaign} has no stored analysis, ledger and report")
        return 2
    passed_at = []
    for number in range(arguments.samples):
        feedback, prose, result, issues = "", None, None, []
        for draft in range(MAX_META_ROUNDS + 1):
            prose = write_prose(QUERY, [], spec, analysis, ledger, feedback, prose if draft else None)
            issues = meta_issues(compose(spec, analysis, ledger, report, prose), spec, analysis, ledger, [])
            if not issues:
                result = draft + 1
                break
            feedback = " ".join(issues)
        passed_at.append(result)
        print(json.dumps({"sample": number + 1, "passed_at_draft": result, "last_issues": issues}, ensure_ascii=False), flush=True)
    passed = sum(1 for value in passed_at if value)
    low, high = wilson_interval(passed, len(passed_at))
    print("SUMMARY", json.dumps({"samples": len(passed_at), "passed": passed, "wilson95": [round(low, 2), round(high, 2)]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
