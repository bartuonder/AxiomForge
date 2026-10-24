from typing import Any

METRIC_NAMES = {"roc_auc": "ROC-AUC", "pr_auc": "PR-AUC", "f1": "F1"}
VERDICTS = ("supported", "contradicted", "inconclusive")


def _p(value: Any) -> str:
    return f"{float(value):.3g}"


def performance_sentences(performance: list[dict[str, Any]] | None) -> list[str]:
    sentences: list[str] = []
    for item in performance or []:
        metric = METRIC_NAMES.get(str(item.get("metric")))
        if metric is None:
            continue
        p_value = _p(item["adjusted_p_value"])
        if item.get("significant"):
            difference = float(item["mean_difference"])
            leader, trailer = (item["a"], item["b"]) if difference > 0 else (item["b"], item["a"])
            effect = abs(float(item["effect_size_dz"]))
            sentences.append(
                f"{leader} has a higher mean {metric} than {trailer} "
                f"(mean difference {abs(difference):.4f}, adjusted p = {p_value}, dz = {effect:.2f})."
            )
        else:
            sentences.append(
                f"No significant difference in {metric} was found between {item['a']} and {item['b']} "
                f"(adjusted p = {p_value})."
            )
    return sentences


def effect_sentences(effects: list[dict[str, Any]] | None) -> list[str]:
    sentences: list[str] = []
    for item in effects or []:
        metric = METRIC_NAMES.get(str(item.get("metric")))
        if metric is None:
            continue
        model = item["model"]
        p_value = _p(item["adjusted_p_value"])
        if item.get("significant"):
            difference = float(item["mean_difference"])
            direction = "higher" if difference > 0 else "lower"
            effect = abs(float(item["effect_size_dz"]))
            sentences.append(
                f"{model} with the listed parameters has a {direction} mean {metric} than {model} with default parameters "
                f"(mean difference {abs(difference):.4f}, adjusted p = {p_value}, dz = {effect:.2f})."
            )
        else:
            sentences.append(
                f"No significant effect of the listed parameters on {metric} was found for {model} "
                f"compared with default parameters (adjusted p = {p_value})."
            )
    return sentences


def _names(models: list[str]) -> str:
    if len(models) <= 1:
        return "".join(models)
    return ", ".join(models[:-1]) + " and " + models[-1]


def leader_sentences(leader: dict[str, Any] | None) -> list[str]:
    if not leader:
        return []
    metric = METRIC_NAMES.get(str(leader.get("metric")))
    if metric is None:
        return []
    sentence = f"{leader['model']} had the highest mean {metric} ({float(leader['mean']):.4f})"
    behind = [str(name) for name in leader.get("not_significant_against") or []]
    if behind:
        sentence += f", but its lead over {_names(behind)} is not statistically significant"
    return [sentence + "."]


def _metric_list(keys: list[str]) -> str:
    return _names([METRIC_NAMES[key] for key in keys])


def summary_sentences(decision: dict[str, Any] | None) -> dict[str, list[str]]:
    decision = decision or {}
    abstract: list[str] = []
    conclusion: list[str] = []
    leader = decision.get("leader")
    plain = leader_sentences(leader)
    if plain:
        metric = METRIC_NAMES[str(leader["metric"])]
        text = (
            f"Averaged over the ten splits, the strongest {metric} ({float(leader['mean']):.4f}) came from {leader['model']}"
        )
        behind = [str(name) for name in leader.get("not_significant_against") or []]
        if behind:
            text += f", although no statistically significant lead over {_names(behind)} was established"
        abstract.append(plain[0])
        conclusion.append(text + ".")
    grouped: dict[str, dict[bool, list[str]]] = {}
    for item in decision.get("parameter_effects") or []:
        key = str(item.get("metric"))
        if not item.get("significant") or key not in METRIC_NAMES:
            continue
        higher = float(item["mean_difference"]) > 0
        grouped.setdefault(str(item["model"]), {True: [], False: []})[higher].append(key)
    for model, directions in grouped.items():
        for higher, keys in directions.items():
            if not keys:
                continue
            metrics = _metric_list(keys)
            abstract.append(
                f"{model} with the listed parameters had a {'higher' if higher else 'lower'} mean {metrics} "
                f"than {model} with default parameters."
            )
            conclusion.append(
                f"Compared with default parameters, the listed parameters {'raised' if higher else 'lowered'} {model}'s {metrics}."
            )
    return {"Abstract": abstract, "Conclusion": conclusion}


def hypothesis_sentences(hypothesis: dict[str, Any] | None) -> list[str]:
    verdict = str((hypothesis or {}).get("verdict", ""))
    if verdict == "untested":
        return ["The hypothesis could not be tested with this data."]
    if verdict not in VERDICTS:
        return []
    claim = hypothesis.get("claim") or {}
    evidence = hypothesis.get("evidence") or {}
    subject, other = claim.get("subject", ""), claim.get("other", "")
    if claim.get("kind") == "stability":
        detail = (
            f"{subject} versus {other} on ROC-AUC variance: "
            f"variance {float(evidence['variance_subject']):.6f} against {float(evidence['variance_other']):.6f}, "
            f"adjusted p = {_p(evidence['adjusted_p_value'])}"
        )
    else:
        metric = METRIC_NAMES.get(str(claim.get("metric")), str(claim.get("metric")))
        detail = (
            f"{subject} versus {other} on {metric}: "
            f"mean difference {float(evidence['mean_difference']):.4f}, "
            f"adjusted p = {_p(evidence['adjusted_p_value'])}, dz = {float(evidence['effect_size_dz']):.2f}"
        )
    return [f"The hypothesis was {verdict} ({detail})."]


def instability_sentences(instability: dict[str, Any] | None) -> list[str]:
    if not instability or not instability.get("unstable"):
        return []
    threshold = float(instability.get("std_threshold", 0.0))
    return [
        f"{item['model']} shows high variance across splits "
        f"({METRIC_NAMES.get(str(item['metric']), str(item['metric']))} std = {float(item['std']):.3f}, "
        f"threshold {threshold:g})."
        for item in instability.get("flagged") or []
    ]


def evidence_sentences(decision: dict[str, Any] | None) -> list[str]:
    decision = decision or {}
    return (
        hypothesis_sentences(decision.get("hypothesis"))
        + leader_sentences(decision.get("leader"))
        + performance_sentences(decision.get("performance"))
        + effect_sentences(decision.get("parameter_effects"))
        + instability_sentences(decision.get("instability"))
    )
