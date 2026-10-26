import re
from typing import Any

from app.campaign.descriptors import DESCRIPTOR_LABELS
from app.campaign.ledger import build_ledger, find
from app.campaign.meta_evidence import AGREEMENT
from app.campaign.provenance import environment_sentence, spec_digest
from app.campaign.tuning import TUNING_SHARE
from app.campaign.stats import ALPHA, METRICS, MIN_DATASETS, MIN_FRIEDMAN_DATASETS
from app.graph.evidence import METRIC_NAMES, configuration_sentence
from app.seeds import SPLIT_SEEDS

VERDICT_LABELS = {
    "replicated": "REPLICATED",
    "partially_replicated": "PARTIALLY REPLICATED",
    "contradicted": "CONTRADICTED (the opposite held)",
    "inconclusive": "NOT REPLICATED (inconclusive)",
    "not_testable": "NOT TESTABLE",
}
MAX_PAIR_SENTENCES = 20
MAX_MODERATOR_SENTENCES = 12
_REFERENCE = re.compile(r"\[E(\d+)\]")
_CLAIM_HEAD = re.compile(r"\*\*[A-Za-z][\w-]*\*\*")
_NAMES_WITH_DIGITS = re.compile(r"\bF1\b")


def _p(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3g}"


def _ref(ledger: list[dict[str, Any]], kind: str, key: str) -> str:
    return f"[{find(ledger, kind, key)['id']}]"


def _group(models: list[str]) -> str:
    return models[0] if len(models) == 1 else " and ".join(models) + " (best member of the family on each dataset)"


def _claim_lines(claim: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    lines = [f"**{claim['id']}** {claim['statement']}: **{VERDICT_LABELS[claim['verdict']]}**."]
    subject, other = _group(claim["claim"]["subject"]), _group(claim["claim"]["other"])
    for row in claim["rows"]:
        metric = METRIC_NAMES[row["metric"]]
        ref = _ref(ledger, "claim", f"{claim['id']}:{row['metric']}")
        if not row["testable"]:
            lines.append(
                f"On {metric}, {subject} beat {other} on {row['wins']} of {row['datasets']} datasets, but only "
                f"{row['datasets'] - row['ties']} datasets differ and a signed-rank test needs at least {MIN_DATASETS}, so this metric could not be tested {ref}."
            )
        else:
            lines.append(
                f"On {metric}, {subject} scored higher than {other} on {row['wins']} of {row['datasets']} datasets "
                f"(lower on {row['losses']}, tied on {row['ties']}); median difference {row['median_difference']:+.4f}, "
                f"Holm-adjusted p = {_p(row['adjusted_p_value'])}, rank-biserial r = {row['rank_biserial']:+.2f} {ref}."
            )
    return lines


def _tuned_lines(finished: list[str], ledger: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for dataset in finished:
        entry = find(ledger, "dataset", dataset)
        models = (entry.get("tuning") or {}).get("models") or {}
        if not models:
            continue
        described = "; ".join(
            f"{model} ({', '.join(f'{name}={value}' for name, value in found['params'].items()) or 'defaults'})" for model, found in models.items()
        )
        lines.append(f"- {dataset}: {described} {_ref(ledger, 'dataset', dataset)}")
    if not lines:
        return []
    return ["Selected configurations (best cross-validated ROC-AUC on the tuning set):", ""] + lines + [""]


def _effect_name(spec: dict[str, Any]) -> str:
    return "tuning" if spec.get("tuning") else "the listed parameters"


def _strict_effect_sentence(spec: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    effects = analysis.get("parameter_effects") or []
    significant = [row for row in effects if row["significant"]]
    if not significant or len({row["model"] for row in effects}) < 2:
        return []
    kept = sum(1 for row in significant if row["significant_all"])
    what = "tuning effects" if spec.get("tuning") else "parameter effects"
    return [f"Significant {what} within their model: {len(significant)}; of these, {kept} remain significant when the adjustment spans all models and metrics."]


def _treatment(row: dict[str, Any]) -> str:
    return "tuned by random search" if (row.get("params") or {}).get("tuned") else "with the listed parameters"


def _source_lines(spec: dict[str, Any], analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    source = spec.get("source") or {}
    quoted = [claim for claim in analysis.get("claims") or [] if claim["claim"].get("quote")]
    if not source.get("title") or not quoted:
        return []
    name = source["title"] + (f" ({source['citation']})" if source.get("citation") else "")
    lines = ["## Comparison with the source", "", f"Source of the claims: {name}.", ""]
    for claim in quoted:
        refs = " ".join(_ref(ledger, "claim", f"{claim['id']}:{row['metric']}") for row in claim["rows"])
        lines.append(f"- **{claim['id']}** The source states: “{claim['claim']['quote']}”. The campaign result {AGREEMENT[claim['verdict']]} {refs}.")
    return lines + [""]


def _moderator_lines(analysis: dict[str, Any], ledger: list[dict[str, Any]]) -> list[str]:
    rows = [row for row in analysis.get("moderators") or [] if row["testable"]]
    if not rows:
        return []
    claims = {claim["id"]: claim for claim in analysis["claims"]}
    lines = [
        "Exploratory moderator analysis (Spearman correlation between the per-dataset advantage of a claim and dataset descriptors, "
        "exploratory because the number of datasets is small):",
        "",
    ]
    significant = [row for row in rows if row["significant"]]
    if not significant:
        lines += ["No dataset descriptor was significantly related to the size of the advantage after Holm adjustment.", ""]
    for row in significant[:MAX_MODERATOR_SENTENCES]:
        claim = claims[row["claim"]]["claim"]
        movement = "grew" if row["rho"] > 0 else "shrank"
        lines.append(
            f"The advantage of {_group(claim['subject'])} over {_group(claim['other'])} on {METRIC_NAMES[row['metric']]} {movement} with "
            f"{DESCRIPTOR_LABELS[row['descriptor']]} (Spearman rho = {row['rho']:+.2f}, Holm-adjusted p = {_p(row['adjusted_p_value'])}, "
            f"{row['datasets']} datasets) {_ref(ledger, 'moderator', f"{row['claim']}:{row['metric']}:{row['descriptor']}")}."
        )
    if significant:
        lines.append("")
    return lines


def _table(spec: dict[str, Any], analysis: dict[str, Any], outcome: dict[str, Any], ledger: list[dict[str, Any]], metric: str) -> list[str]:
    models = list(spec["models"])
    header = "| Dataset | " + " | ".join(models) + " |"
    lines = [header, "|" + "---|" * (len(models) + 1)]
    for dataset in analysis["coverage"]["finished"]:
        means = find(ledger, "dataset", dataset)["means"]
        values = [means[model][metric] for model in models]
        best = max(values)
        cells = [f"**{value:.4f}**" if value == best else f"{value:.4f}" for value in values]
        lines.append(f"| {dataset} {_ref(ledger, 'dataset', dataset)} | " + " | ".join(cells) + " |")
    return lines


def render_report(spec: dict[str, Any], outcome: dict[str, Any], analysis: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    ledger = build_ledger(spec, outcome, analysis)
    coverage = analysis["coverage"]
    finished, failed = coverage["finished"], coverage["failed"]
    lines: list[str] = [f"# {spec['title']}", "", "## Summary", ""]
    dataset_refs = " ".join(_ref(ledger, "dataset", dataset) for dataset in finished)
    sentence = f"{len(finished)} of {len(coverage['requested'])} datasets finished {dataset_refs}".strip()
    if failed:
        sentence += "; failed: " + ", ".join(f"{name} {_ref(ledger, 'failure', name)}" for name in failed)
    lines += [sentence + ".", ""]
    if "error" in analysis:
        lines += [f"No claim could be assessed: {analysis['error']}.", ""]
    else:
        for claim in analysis["claims"]:
            lines += _claim_lines(claim, ledger) + [""]
        if not coverage["enough_for_tests"]:
            lines += [
                f"Only {len(finished)} datasets finished {dataset_refs}; the exact signed-rank test cannot reach p < {ALPHA} with fewer than {MIN_DATASETS} datasets, "
                "so no claim can be called replicated or contradicted.",
                "",
            ]
    lines += ["## Protocol", ""]
    source = spec.get("source") or {}
    if source:
        lines.append("Source: " + "; ".join(source[name] for name in ("title", "citation", "url") if name in source) + ".")
        lines.append("")
    if spec.get("revisions"):
        lines.append("Dataset revisions pinned in the specification: " + ", ".join(spec["revisions"]) + ".")
        lines.append("")
    tuning = spec.get("tuning") or {}
    if tuning:
        sentence = (
            f"Models and configuration: every model was tuned on each dataset by a random search of {tuning['iterations']} configurations "
            f"({tuning['folds']}-fold cross-validated ROC-AUC on a separate tuning set of {round(tuning.get('share', TUNING_SHARE) * 100)}% of the rows that was excluded from evaluation) "
            "and also ran once with library defaults as its control. Every other argument is fixed by the protocol."
        )
    else:
        sentence = "Models and configuration: " + configuration_sentence({"models": spec["models"], "params": spec.get("params") or {}})
        sentence += " Every other argument is fixed by the protocol."
        if spec.get("params"):
            sentence += " A configured model also runs once with library defaults as its control."
    lines.append(sentence)
    lines += [
        "",
        f"Procedure: on each dataset every model ran on {len(SPLIT_SEEDS)} repeated stratified 80/20 train/test splits "
        f"(split seeds {', '.join(str(seed) for seed in SPLIT_SEEDS)}); imputation, scaling and encoding sit in a pipeline fitted on the training part only.",
        "",
        "Statistics: each dataset contributes the mean over its splits for every model; datasets are the units of analysis. "
        f"Models and model families are compared with a two-sided exact Wilcoxon signed-rank test across datasets (at least {MIN_DATASETS} datasets "
        f"with a non-zero difference), Holm-adjusted within each family of tests; the Friedman test needs at least three models and {MIN_FRIEDMAN_DATASETS} datasets. "
        "A model family is scored by its best member on each dataset."
        + (f" The effect of {_effect_name(spec)} is adjusted across the metrics of each model." if analysis.get("parameter_effects") else ""),
        "",
        f"Specification: SHA-256 {spec_digest(spec)}, computed before the first dataset started.",
        "",
    ]
    if finished:
        lines += ["Datasets:", ""]
        for dataset in finished:
            entry = find(ledger, "dataset", dataset)
            revision = (entry.get("provenance") or {}).get("revision", "unknown")
            suffix = f", revision {revision[:10]}" if revision != "unknown" else ""
            evaluated = (entry.get("tuning") or {}).get("rows_eval")
            used = f" ({evaluated} used for evaluation)" if evaluated else ""
            lines.append(f"- {dataset}: {entry['source']}, {int(entry['samples'])} rows{used}, {int(entry['features'])} features{suffix} {_ref(ledger, 'dataset', dataset)}")
        lines.append("")
        lines += _tuned_lines(finished, ledger)
        environment = environment_sentence({dataset: (find(ledger, "dataset", dataset).get("provenance") or {}) for dataset in finished})
        if environment:
            lines += [environment, ""]
    if source.get("deviations"):
        lines += ["Deviations from the source:", ""] + [f"- {note}" for note in source["deviations"]] + [""]
    if "error" not in analysis:
        lines += ["## Results", ""]
        for metric in METRICS:
            lines += [f"Mean {METRIC_NAMES[metric]} per dataset (best in bold):", ""] + _table(spec, analysis, outcome, ledger, metric) + [""]
        for metric in METRICS:
            friedman = analysis["friedman"][metric]
            ranks = ", ".join(f"{name} {value:.2f}" for name, value in sorted(friedman["mean_ranks"].items(), key=lambda item: item[1]))
            ref = _ref(ledger, "friedman", metric)
            if friedman["testable"]:
                lines.append(
                    f"{METRIC_NAMES[metric]} mean ranks across {friedman['datasets']} datasets (1 = best): {ranks}; "
                    f"Friedman chi-square = {friedman['statistic']:.2f}, p = {_p(friedman['p_value'])} {ref}."
                )
            else:
                lines.append(f"{METRIC_NAMES[metric]} mean ranks across {friedman['datasets']} datasets (1 = best): {ranks}; the Friedman test was not run {ref}.")
            lines.append("")
        significant = [(metric, row) for metric in METRICS for row in analysis["pairwise"][metric] if row["significant"]]
        lines += ["Pairwise comparisons that were significant after Holm adjustment:" if significant else "No pairwise comparison was significant after Holm adjustment.", ""]
        for metric, row in significant[:MAX_PAIR_SENTENCES]:
            winner, loser = (row["a"], row["b"]) if row["median_difference"] > 0 else (row["b"], row["a"])
            lines.append(
                f"{winner} scored higher than {loser} on {METRIC_NAMES[metric]} on {max(row['wins'], row['losses'])} of {row['datasets']} datasets "
                f"(median difference {abs(row['median_difference']):.4f}, adjusted p = {_p(row['adjusted_p_value'])}) "
                f"{_ref(ledger, 'pairwise', f'{metric}:{row['a']}:{row['b']}')}."
            )
        if significant:
            lines.append("")
        for row in analysis["parameter_effects"]:
            ref = _ref(ledger, "effect", f"{row['model']}:{row['metric']}")
            if row["significant"]:
                direction = "higher" if row["median_difference"] > 0 else "lower"
                lines.append(
                    f"{row['model']} {_treatment(row)} scored {direction} than {row['model']} with default parameters on "
                    f"{METRIC_NAMES[row['metric']]} on {max(row['wins'], row['losses'])} of {row['datasets']} datasets "
                    f"(median difference {abs(row['median_difference']):.4f}, adjusted p = {_p(row['adjusted_p_value'])}) {ref}."
                )
            else:
                what = "tuning" if (row.get("params") or {}).get("tuned") else "the listed parameters"
                lines.append(f"No significant effect of {what} of {row['model']} on {METRIC_NAMES[row['metric']]} across datasets was found {ref}.")
        if analysis["parameter_effects"]:
            lines.append("")
        lines += _moderator_lines(analysis, ledger)
        lines += _source_lines(spec, analysis, ledger)
    lines += ["## Limitations", ""]
    limitations = [
        "Every conclusion concerns the datasets listed above; with a handful of datasets the tests have little power and a non-significant result is not evidence of equivalence.",
        "Within a dataset the repeated splits overlap, so they are summarised by their mean and never used as independent samples across datasets.",
        (
            "Tuning used a small random search over fixed discrete grids with one tuning set per dataset; a larger search could change the ranking."
            if spec.get("tuning")
            else "Only scikit-learn style estimators with the arguments fixed by the protocol were run; the listed parameters are single configurations, not the result of a search."
        ),
        "Datasets larger than the sampling limit were sampled with a fixed seed, which changes their size but not the class balance of the benchmark.",
    ]
    limitations += _strict_effect_sentence(spec, analysis)
    if failed:
        limitations.append("Datasets that failed were left out of every test: " + ", ".join(failed) + ".")
    lines += [f"- {text}" for text in limitations] + ["", "## Evidence ledger", "", "| Id | Kind | Key | Detail |", "|---|---|---|---|"]
    for entry in ledger:
        detail = {
            "dataset": lambda e: f"{e['source']}, script sha256 {e['script_sha256'][:12]}",
            "failure": lambda e: f"{e['attempts']} attempts: {e['error'][:80]}",
            "claim": lambda e: f"{e['verdict']}, {e['wins']}/{e['datasets']} wins",
            "friedman": lambda e: f"mean ranks over {e['datasets']} datasets",
            "pairwise": lambda e: f"{e['wins']} wins, {e['losses']} losses, {e['ties']} ties",
            "effect": lambda e: f"{e['wins']} wins, {e['losses']} losses, {e['ties']} ties",
            "moderator": lambda e: f"{e['descriptor']}, rho {e['rho']:+.2f}, n {e['datasets']}",
        }[entry["kind"]](entry)
        lines.append(f"| {entry['id']} | {entry['kind']} | {entry['key']} | {detail} |")
    return "\n".join(lines).rstrip() + "\n", ledger


def report_issues(markdown: str, ledger: list[dict[str, Any]], checked: tuple[str, ...] = ("Summary", "Results")) -> list[str]:
    known = {entry["id"] for entry in ledger}
    issues: list[str] = []
    for number in dict.fromkeys(_REFERENCE.findall(markdown)):
        if f"E{number}" not in known:
            issues.append(f"E{number} is cited but not in the ledger")
    section = ""
    for line in markdown.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section not in checked or not line.strip() or line.startswith("|---"):
            continue
        if re.search(r"\d", _NAMES_WITH_DIGITS.sub("", _CLAIM_HEAD.sub("", line))) and not _REFERENCE.search(line):
            issues.append(f"a numeric line in {section} has no evidence reference: {line[:80]}")
    cited = set(_REFERENCE.findall(markdown.split("## Evidence ledger")[0]))
    for entry in ledger:
        if entry["kind"] in {"dataset", "claim", "friedman", "failure"} and entry["id"][1:] not in cited:
            issues.append(f"{entry['id']} ({entry['kind']} {entry['key']}) is never cited")
    return issues
