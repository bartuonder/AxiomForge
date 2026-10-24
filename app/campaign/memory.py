import logging
from typing import Any

from app.campaign.meta_evidence import VERDICT_TITLES, overall_leader
from app.memory.rag_memory import save_experiment, search_past_experiments

logger = logging.getLogger("axiomforge")

CAMPAIGN_OUTCOME = "campaign"
PAST_LIMIT = 5


def claim_signatures(spec: dict[str, Any]) -> set[tuple]:
    return {
        (tuple(sorted(claim["subject"])), tuple(sorted(claim["other"])), tuple(sorted(claim.get("metrics") or [claim.get("metric")])))
        for claim in spec.get("claims") or []
    }


def verdict_summary(analysis: dict[str, Any]) -> str:
    claims = analysis.get("claims") or []
    if not claims:
        return "no claim could be assessed"
    return "; ".join(f"{claim['id']} {VERDICT_TITLES[claim['verdict']].lower()}" for claim in claims)


def remember_campaign(spec: dict[str, Any], analysis: dict[str, Any], status: str) -> str:
    claims = "; ".join(str(claim["statement"]) for claim in spec.get("claims") or [])
    leader = overall_leader(analysis)
    return save_experiment(
        hypothesis=f"{spec['title']}: {claims}",
        code="",
        metric=verdict_summary(analysis),
        error_log="",
        is_success=True,
        outcome=CAMPAIGN_OUTCOME,
        finding=f"Review status {status}." + (f" {leader} ranked first overall." if leader else ""),
        spec=spec,
    )


def past_campaigns(query: str, limit: int = PAST_LIMIT) -> list[dict[str, Any]]:
    try:
        records = search_past_experiments(query, k=limit)
    except Exception:
        logger.exception("past campaigns could not be read from the memory")
        return []
    return [
        {"title": str((record.get("spec") or {}).get("title") or record.get("hypothesis", "")), "spec": record["spec"], "verdicts": record.get("metric", "")}
        for record in records
        if record.get("outcome") == CAMPAIGN_OUTCOME and record.get("spec")
    ]


def find_repeats(spec: dict[str, Any], past: list[dict[str, Any]]) -> list[str]:
    mine = claim_signatures(spec)
    return [item["title"] for item in past if mine & claim_signatures(item["spec"])]
