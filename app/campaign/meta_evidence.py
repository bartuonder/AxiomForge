from typing import Any

from app.campaign.descriptors import DESCRIPTOR_LABELS
from app.campaign.ledger import find
from app.campaign.stats import METRICS
from app.graph.evidence import METRIC_NAMES

VERDICT_TITLES = {
    "replicated": "Replicated",
    "partially_replicated": "Partially replicated",
    "contradicted": "Contradicted",
    "inconclusive": "Inconclusive",
    "not_testable": "Not testable",
}


AGREEMENT = {
    "replicated": "agrees with the source",
    "partially_replicated": "agrees with the source on some metrics only",
    "contradicted": "disagrees with the source, the opposite held",
    "inconclusive": "neither confirms nor refutes the source",
    "not_testable": "could not test the claim of the source",
}


def metric_leaders(analysis: dict[str, Any]) -> dict[str, str]:
    leaders: dict[str, str] = {}
    for metric, result in (analysis.get("friedman") or {}).items():
        ranks = result.get("mean_ranks") or {}
        if ranks:
            leaders[metric] = min(ranks, key=lambda model: (ranks[model], model))
    return leaders


def average_ranks(analysis: dict[str, Any]) -> dict[str, float]:
    tables = [result["mean_ranks"] for result in (analysis.get("friedman") or {}).values() if result.get("mean_ranks")]
    if not tables:
        return {}
    return {model: sum(table[model] for table in tables) / len(tables) for model in sorted(tables[0])}


def overall_leader(analysis: dict[str, Any]) -> str | None:
    average = average_ranks(analysis)
    return min(average, key=lambda model: (average[model], model)) if average else None


def _ref(ledger: list[dict[str, Any]], kind: str, key: str) -> str:
    return f"[{find(ledger, kind, key)['id']}]"


def _names(metrics: list[str]) -> str:
    names = [METRIC_NAMES[metric] for metric in metrics]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _family(models: list[str]) -> str:
    return models[0] if len(models) == 1 else "the best of " + " and ".join(models)


def verdict_sentences(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    sentences = []
    for claim in analysis.get("claims") or []:
        refs = " ".join(_ref(ledger, "claim", f"{claim['id']}:{row['metric']}") for row in claim["rows"])
        by_verdict: dict[str, list[str]] = {}
        for row in claim["rows"]:
            by_verdict.setdefault(row["verdict"], []).append(row["metric"])
        head = f"**{claim['id']}** ({claim['statement']})"
        title = VERDICT_TITLES[claim["verdict"]]
        if len(by_verdict) == 1:
            metrics = next(iter(by_verdict.values()))
            sentences.append(f"{head} was **{title}** on {_names(metrics)} {refs}.")
        else:
            detail = "; ".join(f"{VERDICT_TITLES[verdict]} on {_names(metrics)}" for verdict, metrics in by_verdict.items())
            sentences.append(f"{head} was **{title}**: {detail} {refs}.")
    return sentences


def comparison_sentences(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    sentences = []
    for claim in analysis.get("claims") or []:
        if not claim["claim"].get("quote"):
            continue
        refs = " ".join(_ref(ledger, "claim", f"{claim['id']}:{row['metric']}") for row in claim["rows"])
        sentences.append(f"**{claim['id']}** ({claim['statement']}) was stated by the source and the campaign result {AGREEMENT[claim['verdict']]} {refs}.")
    return sentences


def _scores(ledger: list[dict[str, Any]], dataset: str, models: list[str], metric: str) -> float:
    means = find(ledger, "dataset", dataset)["means"]
    return max(means[model][metric] for model in models)


def _gaps(claim: dict[str, Any], metric: str, analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[tuple[str, float, float]]:
    subject, other = claim["claim"]["subject"], claim["claim"]["other"]
    return [
        (dataset, _scores(ledger, dataset, subject, metric), _scores(ledger, dataset, other, metric))
        for dataset in analysis["coverage"]["finished"]
    ]


def exception_sentences(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    sentences = []
    for claim in analysis.get("claims") or []:
        subject, other = _family(claim["claim"]["subject"]), _family(claim["claim"]["other"])
        for row in claim["rows"]:
            metric = row["metric"]
            ref = _ref(ledger, "claim", f"{claim['id']}:{metric}")
            gaps = _gaps(claim, metric, analysis, ledger)
            failures = [item for item in gaps if item[1] <= item[2]]
            if not failures:
                sentences.append(f"On {METRIC_NAMES[metric]}, {subject} scored higher than {other} on every dataset tested ({len(gaps)} of {len(gaps)}) {ref}.")
                continue
            details = []
            for dataset, first, second in failures:
                dataset_ref = _ref(ledger, "dataset", dataset)
                if first == second:
                    details.append(f"{dataset} (tied at {first:.4f}) {dataset_ref}")
                else:
                    details.append(f"{dataset} ({other} {second:.4f} against {subject} {first:.4f}) {dataset_ref}")
            sentences.append(
                f"On {METRIC_NAMES[metric]}, {subject} did not score higher than {other} on {len(failures)} of {len(gaps)} datasets: "
                + "; ".join(details)
                + f" {ref}."
            )
    return sentences


def margin_sentences(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    sentences = []
    for claim in analysis.get("claims") or []:
        subject, other = _family(claim["claim"]["subject"]), _family(claim["claim"]["other"])
        for row in claim["rows"]:
            gaps = _gaps(claim, row["metric"], analysis, ledger)
            dataset, first, second = max(gaps, key=lambda item: (item[1] - item[2], item[0]))
            if first - second <= 0:
                continue
            sentences.append(
                f"The largest advantage of {subject} over {other} on {METRIC_NAMES[row['metric']]} was on {dataset} "
                f"({first - second:+.4f}) {_ref(ledger, 'dataset', dataset)}."
            )
    return sentences


def leader_sentence(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    average = average_ranks(analysis)
    if not average:
        return []
    ordered = sorted(average, key=lambda model: (average[model], model))
    refs = " ".join(_ref(ledger, "friedman", metric) for metric in METRICS if metric in (analysis.get("friedman") or {}))
    ranks = ", ".join(f"{model} {average[model]:.2f}" for model in ordered)
    return [f"Averaged over the metrics, the mean ranks (1 = best) were {ranks}; {ordered[0]} ranked first overall {refs}."]


def moderator_sentences(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    claims = {claim["id"]: claim for claim in analysis.get("claims") or []}
    sentences = []
    for row in analysis.get("moderators") or []:
        if not row["significant"]:
            continue
        claim = claims[row["claim"]]["claim"]
        movement = "grew" if row["rho"] > 0 else "shrank"
        sentences.append(
            f"The advantage of {_family(claim['subject'])} over {_family(claim['other'])} on {METRIC_NAMES[row['metric']]} {movement} with "
            f"{DESCRIPTOR_LABELS[row['descriptor']]} across the datasets {_ref(ledger, 'moderator', f"{row['claim']}:{row['metric']}:{row['descriptor']}")}."
        )
    return sentences


def effect_sentences(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    sentences = []
    for row in analysis.get("parameter_effects") or []:
        if not row["significant"]:
            continue
        treatment = "tuned by random search" if (row.get("params") or {}).get("tuned") else "with the listed parameters"
        direction = "higher" if row["median_difference"] > 0 else "lower"
        sentences.append(
            f"{row['model']} {treatment} scored {direction} than {row['model']} with library defaults on {METRIC_NAMES[row['metric']]} across the datasets "
            f"{_ref(ledger, 'effect', f"{row['model']}:{row['metric']}")}."
        )
    return sentences


def discussion_facts(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    if "error" in analysis:
        return []
    return verdict_sentences(analysis, ledger) + leader_sentence(analysis, ledger) + exception_sentences(analysis, ledger) + margin_sentences(analysis, ledger) + effect_sentences(analysis, ledger) + moderator_sentences(analysis, ledger) + comparison_sentences(analysis, ledger)
