from typing import Any

from app.campaign.vocabulary import (
    GLOSSARY,
    LANGUAGES,
    METRIC_LABELS,
    STATUS_LABELS,
    VERDICTS,
    pretty_dataset,
    pretty_model,
)
from app.seeds import SPLIT_SEEDS

STATUS_TONES = {"completed": "positive", "needs_review": "warning", "failed": "negative", "running": "neutral", "queued": "muted"}
VERDICT_ORDER = ("replicated", "contradicted", "partially_replicated", "inconclusive", "not_testable")
AGREEING_SHARE = 0.8

CONFIDENCE = {
    "tr": {
        "high": ("Yüksek güven", "Tüm ölçütlerde ve veri setlerinin çoğunda aynı sonuç çıktı."),
        "medium": ("Orta güven", "Sonuç tek yönlü değil: bazı ölçütlerde ya da bazı veri setlerinde farklı çıktı."),
        "low": ("Düşük güven", "Bu iddia için yeterli kanıt bulunamadı."),
    },
    "en": {
        "high": ("High confidence", "All measures and most datasets gave the same result."),
        "medium": ("Medium confidence", "The result is not uniform: some measures or datasets differed."),
        "low": ("Low confidence", "There was not enough evidence for this claim."),
    },
}

TEXT = {
    "tr": {
        "claims_counted": "{count} iddia sınandı: {parts}",
        "datasets": "{count} gerçek veri setinde denendi.",
        "models": "{count} model aynı koşullarda eğitildi ve karşılaştırıldı.",
        "splits": "Her veri setinde veri {count} kez farklı biçimde eğitim (%80) ve test (%20) olarak bölündü; sonuçlar ortalandı.",
        "tuned": "Her modelin ayarları rastgele aramayla optimize edildi; ayar yapılmamış sürümle de karşılaştırıldı.",
        "default": "Modeller kütüphanelerin varsayılan ayarlarıyla çalıştırıldı.",
        "statistics": "Farklar veri setleri üzerinden Wilcoxon testi ve Holm düzeltmesiyle istatistiksel olarak sınandı.",
        "general": "Sonuçlar yalnızca denenen {count} veri seti için geçerlidir; başka veri türlerinde farklı çıkabilir.",
        "failed": "{count} veri seti tamamlanamadı ve sonuca dahil edilmedi.",
        "few": "Yeterli sayıda veri seti bitmediği için bazı iddialar test edilemedi.",
        "unclear": "“Kanıt yetersiz”, modellerin eşit olduğu anlamına gelmez; fark küçük olabilir ya da veri az olabilir.",
        "review": "Rapor otomatik denetimde bir sorun buldu; ayrıntılı rapora bakın.",
        "group": "{names} grubu",
        "group_from": "{names} grubundan",
        "model_from": "{name} modelinden",
        "and": " ve ",
        "replicated": "{subject}, {other_from} daha iyi çıktı",
        "contradicted": "Tersi doğru çıktı: {other}, {subject_from} daha iyi",
        "inconclusive": "{subject} ile {other} arasında net bir fark gösterilemedi",
        "partially_replicated": "{subject}, {other_from} yalnızca bazı ölçütlerde daha iyi çıktı",
        "not_testable": "{subject} ile {other} karşılaştırması için yeterli veri yok, sonuç çıkarılamadı",
    },
    "en": {
        "claims_counted": "{count} claims tested: {parts}",
        "datasets": "Tried on {count} real datasets.",
        "models": "{count} models were trained and compared under the same conditions.",
        "splits": "On each dataset the data was split {count} different ways into training (80%) and test (20%); the results were averaged.",
        "tuned": "The settings of every model were optimised by random search; they were also compared with the untuned version.",
        "default": "The models ran with the default settings of their libraries.",
        "statistics": "The differences across datasets were tested statistically with the Wilcoxon test and the Holm correction.",
        "general": "The results hold only for the {count} datasets that were tried; other kinds of data may behave differently.",
        "failed": "{count} dataset(s) did not finish and were left out of the result.",
        "few": "Too few datasets finished, so some claims could not be tested.",
        "unclear": "“Not enough evidence” does not mean the models are equal; the difference may be small or the data too little.",
        "review": "The automatic check found a problem in the report; see the detailed report.",
        "group": "{names} (as a group)",
        "group_from": "{names} (as a group)",
        "model_from": "{name}",
        "and": " and ",
        "replicated": "{subject} did better than {other_from}",
        "contradicted": "The opposite held: {other} did better than {subject_from}",
        "inconclusive": "No clear difference between {subject} and {other} could be shown",
        "partially_replicated": "{subject} did better than {other_from} on some measures only",
        "not_testable": "There was too little data to compare {subject} with {other}",
    },
}


def _joined(names: list[str], language: str) -> str:
    if len(names) == 1:
        return names[0]
    glue = TEXT[language]["and"]
    return ", ".join(names[:-1]) + glue + names[-1]


def _side(models: list[str], language: str) -> dict[str, str]:
    names = [pretty_model(model, language) for model in models]
    if len(names) == 1:
        return {"plain": names[0], "from": TEXT[language]["model_from"].format(name=names[0])}
    joined = _joined(names, language)
    return {"plain": TEXT[language]["group"].format(names=joined), "from": TEXT[language]["group_from"].format(names=joined)}


def _headline(verdict: str, subject: dict[str, str], other: dict[str, str], language: str) -> str:
    return TEXT[language][verdict].format(subject=subject["plain"], other=other["plain"], subject_from=subject["from"], other_from=other["from"])


def _direction(row: dict[str, Any], verdict: str) -> tuple[int, int]:
    return (row["losses"], row["wins"]) if verdict == "contradicted" else (row["wins"], row["losses"])


def _confidence(verdict: str, rows: list[dict[str, Any]], language: str) -> dict[str, str]:
    level = "low"
    if verdict in ("replicated", "contradicted", "partially_replicated"):
        level = "medium"
    if verdict in ("replicated", "contradicted"):
        testable = [row for row in rows if row["testable"]]
        agreeing = all(_direction(row, verdict)[0] / row["datasets"] >= AGREEING_SHARE for row in rows if row["datasets"])
        if testable and all(row["significant"] for row in testable) and agreeing:
            level = "high"
    label, reason = CONFIDENCE[language][level]
    return {"level": level, "label": label, "reason": reason}


def _metric_rows(rows: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    return [
        {
            "metric": row["metric"],
            "label": METRIC_LABELS[language][row["metric"]]["name"],
            "meaning": METRIC_LABELS[language][row["metric"]]["meaning"],
            "wins": row["wins"],
            "losses": row["losses"],
            "ties": row["ties"],
            "total": row["datasets"],
            "median_difference": row["median_difference"],
            "significant": row["significant"],
            "testable": row["testable"],
        }
        for row in rows
    ]


def _chart(claim: dict[str, Any], metric: str, subject: dict[str, str], other: dict[str, str], analysis: dict[str, Any], ledger: list[dict[str, Any]], language: str) -> dict[str, Any]:
    means = {entry["key"]: entry["means"] for entry in ledger if entry["kind"] == "dataset"}
    points = []
    for dataset in analysis["coverage"]["finished"]:
        scores = means[dataset]
        points.append(
            {
                "dataset": dataset,
                "label": pretty_dataset(dataset, language),
                "subject": max(scores[model][metric] for model in claim["subject"] if model in scores),
                "other": max(scores[model][metric] for model in claim["other"] if model in scores),
            }
        )
    return {"metric": metric, "metric_label": METRIC_LABELS[language][metric]["name"], "subject_label": subject["plain"], "other_label": other["plain"], "points": points}


def _claim(item: dict[str, Any], analysis: dict[str, Any], ledger: list[dict[str, Any]], language: str) -> dict[str, Any]:
    claim = item["claim"]
    verdict = item["verdict"]
    subject, other = _side(claim["subject"], language), _side(claim["other"], language)
    metric = claim["metric"]
    primary = next((row for row in item["rows"] if row["metric"] == metric), item["rows"][0])
    datasets_for, datasets_against = _direction(primary, verdict)
    entry = VERDICTS[verdict]
    return {
        "id": item["id"],
        "statement": item["statement"],
        "verdict": {"code": verdict, "label": entry[language]["label"], "tone": entry["tone"], "meaning": entry[language]["meaning"]},
        "headline": _headline(verdict, subject, other, language),
        "confidence": _confidence(verdict, item["rows"], language),
        "primary_metric": metric,
        "datasets_for": datasets_for,
        "datasets_against": datasets_against,
        "datasets_total": primary["datasets"],
        "metrics": _metric_rows(item["rows"], language),
        "chart": _chart(claim, metric, subject, other, analysis, ledger, language),
    }


def _ranking(analysis: dict[str, Any], language: str) -> list[dict[str, Any]]:
    tables = [result["mean_ranks"] for result in (analysis.get("friedman") or {}).values() if result.get("mean_ranks")]
    if not tables:
        return []
    average = {model: sum(table[model] for table in tables) / len(tables) for model in tables[0]}
    ordered = sorted(average, key=lambda model: (average[model], model))
    return [{"model": model, "label": pretty_model(model, language), "average_rank": average[model], "position": position} for position, model in enumerate(ordered, start=1)]


def _was_tuned(spec: dict[str, Any] | None, ledger: list[dict[str, Any]]) -> bool:
    if spec and spec.get("tuning"):
        return True
    return any((entry.get("tuning") or {}).get("models") for entry in ledger if entry["kind"] == "dataset")


def _method(spec: dict[str, Any] | None, analysis: dict[str, Any], ledger: list[dict[str, Any]], language: str) -> list[str]:
    text = TEXT[language]
    return [
        text["datasets"].format(count=len(analysis["coverage"]["finished"])),
        text["models"].format(count=len(analysis["models"])),
        text["splits"].format(count=len(SPLIT_SEEDS)),
        text["tuned"] if _was_tuned(spec, ledger) else text["default"],
        text["statistics"],
    ]


def _cautions(state: dict[str, Any], analysis: dict[str, Any], claims: list[dict[str, Any]], language: str) -> list[str]:
    text = TEXT[language]
    coverage = analysis["coverage"]
    cautions = [text["general"].format(count=len(coverage["finished"]))]
    if coverage["failed"]:
        cautions.append(text["failed"].format(count=len(coverage["failed"])))
    if not coverage.get("enough_for_tests", True):
        cautions.append(text["few"])
    if any(claim["verdict"]["code"] == "inconclusive" for claim in claims):
        cautions.append(text["unclear"])
    if state.get("status") == "needs_review":
        cautions.append(text["review"])
    return cautions


def _progress(state: dict[str, Any]) -> dict[str, int]:
    statuses = [item.get("status") for item in (state.get("datasets") or {}).values()]
    finished, failed, total = statuses.count("finished"), statuses.count("failed"), len(statuses)
    return {"finished": finished, "failed": failed, "total": total, "percent": round(100 * (finished + failed) / total) if total else 0}


def _counts(claims: list[dict[str, Any]]) -> dict[str, int]:
    return {code: sum(1 for claim in claims if claim["verdict"]["code"] == code) for code in VERDICT_ORDER}


def _headline_line(claims: list[dict[str, Any]], counts: dict[str, int], language: str) -> str:
    if not claims:
        return ""
    if len(claims) == 1:
        return claims[0]["headline"]
    parts = ", ".join(f"{counts[code]} {VERDICTS[code][language]['label'].lower()}" for code in VERDICT_ORDER if counts[code])
    return TEXT[language]["claims_counted"].format(count=len(claims), parts=parts)


def build_summary(state: dict[str, Any], spec: dict[str, Any] | None, analysis: dict[str, Any] | None, ledger: list[dict[str, Any]] | None, language: str = "tr") -> dict[str, Any]:
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of: {', '.join(LANGUAGES)}")
    ready = bool(analysis) and "error" not in analysis and ledger is not None
    claims = [_claim(item, analysis, ledger, language) for item in analysis["claims"]] if ready else []
    counts = _counts(claims)
    status = state.get("status", "queued")
    keys = list((state.get("datasets") or {})) or list(((analysis or {}).get("coverage") or {}).get("requested") or [])
    source = (spec or {}).get("source") or {}
    return {
        "language": language,
        "campaign_id": state["id"],
        "title": (spec or {}).get("title") or state.get("title", ""),
        "source": {"title": source["title"], "citation": source.get("citation", "")} if source.get("title") else None,
        "status": {"code": status, "label": STATUS_LABELS[language].get(status, status), "tone": STATUS_TONES.get(status, "neutral")},
        "progress": _progress(state),
        "headline": _headline_line(claims, counts, language),
        "verdict_counts": counts,
        "claims": claims,
        "ranking": _ranking(analysis, language) if ready else [],
        "method": _method(spec, analysis, ledger, language) if ready else [],
        "cautions": _cautions(state, analysis, claims, language) if ready else [],
        "datasets": [{"key": key, "label": pretty_dataset(key, language)} for key in keys],
        "glossary": GLOSSARY[language],
        "error": state.get("error") or None,
    }
