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
        + performance_sentences(decision.get("performance"))
        + effect_sentences(decision.get("parameter_effects"))
        + instability_sentences(decision.get("instability"))
    )
