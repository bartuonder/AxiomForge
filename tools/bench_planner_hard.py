import json

from app.agents.campaign_planner import CampaignUnsupported, run_campaign_planner
from app.campaign.hard_benchmark import HARD_PLAN_CASES, classify_plan, wilson_interval


def main() -> int:
    rows = []
    for case in HARD_PLAN_CASES:
        entry = {"id": case["id"], "query": case["query"]}
        try:
            candidates = run_campaign_planner(case["query"], [], None)
            entry.update(classify_plan(case, candidates))
        except CampaignUnsupported as exc:
            entry.update(classify_plan(case, [], unsupported=True))
            entry["detail"] = str(exc)[:200]
        except Exception as exc:
            entry.update({"outcome": "error", "accepted": False, "detail": f"{type(exc).__name__}: {str(exc)[:300]}"})
        rows.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    accepted = sum(1 for row in rows if row["accepted"])
    low, high = wilson_interval(accepted, len(rows))
    print("SUMMARY", json.dumps({"cases": len(rows), "accepted": accepted, "wilson95": [round(low, 2), round(high, 2)]}))
    return 0 if accepted == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
