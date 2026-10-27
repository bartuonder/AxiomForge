import copy

import pytest

from app.campaign.analysis import analyze_campaign
from app.campaign.report import render_report
from app.campaign.summary import build_summary
from app.campaign.vocabulary import GLOSSARY, STATUS_LABELS
from app.datasets import benchmark_keys
from app.seeds import SPLIT_SEEDS

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [
    {"id": "C1", "statement": "Tree-based models beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"], "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    {"id": "C2", "statement": "The MLP beats logistic regression", "metric": "f1", "metrics": ["f1"], "subject": ["MLP"], "other": ["LogisticRegression"]},
]
SPEC = {"title": "Trees against networks", "models": MODELS, "params": {}, "tuning": {}, "claims": CLAIMS, "datasets": benchmark_keys(), "source": {"title": "Why do trees win", "citation": "Grinsztajn et al. (2022)"}}
KEYS = benchmark_keys()
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}
FLIPPED = {"RandomForest": 0.80, "HistGradientBoosting": 0.82, "MLP": 0.90, "LogisticRegression": 0.70}
EQUAL = {"RandomForest": 0.85, "HistGradientBoosting": 0.85, "MLP": 0.85, "LogisticRegression": 0.85}


def outcome(base=BASE, keys=KEYS, failed=None):
    datasets = {}
    for index, key in enumerate(keys):
        sign = 1 if index % 2 == 0 else -1
        summary = {name: {f"{metric}_mean": value + (0.001 * index if base is not EQUAL else 0.004 * sign * (1 if name == "RandomForest" else -1)) for metric in ("roc_auc", "pr_auc", "f1")} for name, value in base.items()}
        datasets[key] = {
            "summary": summary,
            "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
            "descriptors": {},
            "provenance": {},
            "tuning": {},
            "seconds": 5.0,
            "attempts": 1,
            "script": key,
        }
    return {"order": list(keys) + list(failed or {}), "datasets": datasets, "failed": failed or {}}


def world(base=BASE, spec=SPEC, keys=KEYS, failed=None):
    data = outcome(base, keys, failed)
    analysis = analyze_campaign(spec, data)
    _, ledger = render_report(spec, data, analysis)
    return copy.deepcopy(analysis), ledger


def state(**changes):
    base = {
        "id": "abc",
        "title": "Trees against networks",
        "status": "completed",
        "datasets": {key: {"status": "finished"} for key in KEYS},
        "issues": [],
    }
    return {**base, **changes}


def summary(base=BASE, language="tr", **kwargs):
    analysis, ledger = world(base, **{key: kwargs.pop(key) for key in ("spec", "keys", "failed") if key in kwargs})
    return build_summary(kwargs.pop("state", state()), kwargs.pop("spec_value", SPEC), analysis, ledger, language)


class TestTop:
    def test_the_top_level_fields(self):
        result = summary()
        assert result["language"] == "tr" and result["campaign_id"] == "abc" and result["title"] == "Trees against networks"
        assert set(result) >= {"status", "progress", "headline", "claims", "ranking", "method", "cautions", "glossary", "datasets", "verdict_counts"}

    def test_an_unknown_language_is_refused(self):
        analysis, ledger = world()
        with pytest.raises(ValueError, match="language"):
            build_summary(state(), SPEC, analysis, ledger, "de")

    def test_the_status_has_a_label_and_a_tone(self):
        assert summary()["status"] == {"code": "completed", "label": STATUS_LABELS["tr"]["completed"], "tone": "positive"}
        assert summary(state=state(status="needs_review"))["status"]["tone"] == "warning"
        assert summary(state=state(status="failed"))["status"]["tone"] == "negative"
        assert summary(state=state(status="running"))["status"]["tone"] == "neutral"
        assert summary(state=state(status="queued"))["status"]["tone"] == "muted"

    def test_the_english_status(self):
        assert summary(language="en")["status"]["label"] == "Completed"

    def test_the_title_comes_from_the_specification_then_the_state(self):
        assert summary(spec_value={**SPEC, "title": "From the spec"})["title"] == "From the spec"
        assert summary(spec_value=None)["title"] == "Trees against networks"

    def test_the_source_is_given_when_known(self):
        assert summary()["source"] == {"title": "Why do trees win", "citation": "Grinsztajn et al. (2022)"}
        assert summary(spec_value=None)["source"] is None

    def test_the_glossary_is_the_one_of_the_language(self):
        assert summary()["glossary"] == GLOSSARY["tr"] and summary(language="en")["glossary"] == GLOSSARY["en"]

    def test_the_datasets_are_listed_with_plain_names(self):
        datasets = summary()["datasets"]
        assert [item["key"] for item in datasets] == KEYS and datasets[0]["label"] == "Kredi riski"
        assert summary(language="en")["datasets"][0]["label"] == "Credit risk"


class TestHeadline:
    def test_several_claims_are_counted_in_one_line(self):
        result = summary()
        assert result["verdict_counts"] == {"replicated": 2, "contradicted": 0, "inconclusive": 0, "partially_replicated": 0, "not_testable": 0}
        assert result["headline"] == "2 iddia sınandı: 2 doğrulandı"

    def test_the_counts_mix_and_skip_empty_parts(self):
        result = summary(FLIPPED)
        assert result["verdict_counts"]["contradicted"] == 1 and result["verdict_counts"]["replicated"] == 1
        assert result["headline"] == "2 iddia sınandı: 1 doğrulandı, 1 çürütüldü"

    def test_one_claim_uses_its_own_headline(self):
        single = {**SPEC, "claims": CLAIMS[:1]}
        result = summary(spec=single, spec_value=single)
        assert result["headline"] == result["claims"][0]["headline"]

    def test_the_english_line(self):
        assert summary(language="en")["headline"] == "2 claims tested: 2 confirmed"

    def test_no_claims_no_headline(self):
        result = build_summary(state(status="running"), SPEC, None, None, "tr")
        assert result["headline"] == "" and result["claims"] == []


class TestClaims:
    def test_a_confirmed_claim(self):
        claim = summary()["claims"][0]
        assert claim["id"] == "C1" and claim["statement"] == "Tree-based models beat the MLP"
        assert claim["verdict"] == {"code": "replicated", "label": "Doğrulandı", "tone": "positive", "meaning": "İddia, test edilen veri setlerinde tutarlı biçimde doğru çıktı."}
        assert claim["headline"] == "Random Forest ve Histogram Gradient Boosting grubu, Yapay sinir ağı (MLP) modelinden daha iyi çıktı"

    def test_a_single_model_each_side(self):
        claim = summary()["claims"][1]
        assert claim["headline"] == "Yapay sinir ağı (MLP), Lojistik regresyon modelinden daha iyi çıktı"

    def test_the_english_headline(self):
        claim = summary(language="en")["claims"][0]
        assert claim["headline"] == "Random forest and Histogram gradient boosting (as a group) did better than Neural network (MLP)"
        assert claim["verdict"]["label"] == "Confirmed"

    def test_a_refuted_claim_says_the_opposite_held(self):
        claim = summary(FLIPPED)["claims"][0]
        assert claim["verdict"]["code"] == "contradicted" and claim["verdict"]["label"] == "Çürütüldü" and claim["verdict"]["tone"] == "negative"
        assert claim["headline"] == "Tersi doğru çıktı: Yapay sinir ağı (MLP), Random Forest ve Histogram Gradient Boosting grubundan daha iyi"
        assert summary(FLIPPED, language="en")["claims"][0]["headline"] == "The opposite held: Neural network (MLP) did better than Random forest and Histogram gradient boosting (as a group)"

    def test_a_claim_that_could_not_be_tested(self):
        claim = summary(EQUAL)["claims"][0]
        assert claim["verdict"]["code"] == "not_testable" and claim["verdict"]["label"] == "Test edilemedi" and claim["verdict"]["tone"] == "muted"
        assert claim["headline"] == "Random Forest ve Histogram Gradient Boosting grubu ile Yapay sinir ağı (MLP) karşılaştırması için yeterli veri yok, sonuç çıkarılamadı"

    @pytest.mark.parametrize(
        ("verdict", "headline"),
        [
            ("inconclusive", "Random Forest ve Histogram Gradient Boosting grubu ile Yapay sinir ağı (MLP) arasında net bir fark gösterilemedi"),
            ("partially_replicated", "Random Forest ve Histogram Gradient Boosting grubu, Yapay sinir ağı (MLP) modelinden yalnızca bazı ölçütlerde daha iyi çıktı"),
        ],
    )
    def test_the_other_verdicts_have_their_own_sentence(self, verdict, headline):
        analysis, ledger = world()
        analysis["claims"][0]["verdict"] = verdict
        claim = build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]
        assert claim["headline"] == headline and claim["verdict"]["code"] == verdict

    def test_the_measure_rows_carry_plain_labels(self):
        rows = summary()["claims"][0]["metrics"]
        assert [row["metric"] for row in rows] == ["roc_auc", "pr_auc", "f1"]
        assert rows[0]["label"] == "ROC-AUC" and rows[0]["meaning"].startswith("Modelin iki sınıfı")
        assert rows[0]["wins"] == 9 and rows[0]["losses"] == 0 and rows[0]["ties"] == 0 and rows[0]["total"] == 9
        assert rows[0]["significant"] is True and rows[0]["testable"] is True and rows[0]["median_difference"] > 0

    def test_the_dataset_counts_follow_the_direction_of_the_verdict(self):
        confirmed = summary()["claims"][0]
        assert (confirmed["datasets_for"], confirmed["datasets_against"], confirmed["datasets_total"]) == (9, 0, 9)
        refuted = summary(FLIPPED)["claims"][0]
        assert (refuted["datasets_for"], refuted["datasets_against"], refuted["datasets_total"]) == (9, 0, 9)

    def test_the_primary_measure_is_the_one_of_the_claim(self):
        assert summary()["claims"][0]["primary_metric"] == "roc_auc" and summary()["claims"][1]["primary_metric"] == "f1"


class TestConfidence:
    def test_all_measures_and_most_datasets_agree(self):
        confidence = summary()["claims"][0]["confidence"]
        assert confidence["level"] == "high" and confidence["label"] == "Yüksek güven"
        assert confidence["reason"] == "Tüm ölçütlerde ve veri setlerinin çoğunda aynı sonuç çıktı."

    def test_the_english_confidence(self):
        confidence = summary(language="en")["claims"][0]["confidence"]
        assert confidence["label"] == "High confidence" and confidence["reason"] == "All measures and most datasets gave the same result."

    def test_no_evidence_is_low(self):
        analysis, ledger = world(EQUAL)
        claims = build_summary(state(), SPEC, analysis, ledger, "tr")["claims"]
        assert [claim["verdict"]["code"] for claim in claims] == ["not_testable", "not_testable"]
        for claim in claims:
            assert claim["confidence"] == {"level": "low", "label": "Düşük güven", "reason": "Bu iddia için yeterli kanıt bulunamadı."}

    def test_a_partly_confirmed_claim_is_medium(self):
        analysis, ledger = world()
        analysis["claims"][0]["verdict"] = "partially_replicated"
        claim = build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]
        assert claim["confidence"]["level"] == "medium" and claim["confidence"]["label"] == "Orta güven"
        assert claim["confidence"]["reason"] == "Sonuç tek yönlü değil: bazı ölçütlerde ya da bazı veri setlerinde farklı çıktı."

    def test_few_winning_datasets_lower_a_confirmed_claim_to_medium(self):
        analysis, ledger = world()
        for row in analysis["claims"][0]["rows"]:
            row["wins"], row["losses"] = 6, 3
        assert build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]["confidence"]["level"] == "medium"

    def test_one_insignificant_measure_lowers_a_confirmed_claim_to_medium(self):
        analysis, ledger = world()
        analysis["claims"][0]["rows"][1]["significant"] = False
        assert build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]["confidence"]["level"] == "medium"

    def test_a_refuted_claim_is_judged_by_the_datasets_of_the_opposite(self):
        refuted = summary(FLIPPED)["claims"][0]
        assert refuted["verdict"]["code"] == "contradicted" and refuted["confidence"]["level"] == "high"
        assert (refuted["datasets_for"], refuted["datasets_against"]) == (9, 0)

    def test_a_refuted_claim_with_mixed_datasets_is_medium(self):
        analysis, ledger = world(FLIPPED)
        for row in analysis["claims"][0]["rows"]:
            row["wins"], row["losses"] = 3, 6
        refuted = build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]
        assert refuted["confidence"]["level"] == "medium" and (refuted["datasets_for"], refuted["datasets_against"]) == (6, 3)


class TestConfidenceEdges:
    def claim_with(self, mutate):
        analysis, ledger = world()
        mutate(analysis["claims"][0])
        return build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]

    def test_exactly_the_agreeing_share_is_still_high(self):
        def five_of_five_datasets(claim):
            for row in claim["rows"]:
                row["datasets"], row["wins"], row["losses"], row["ties"] = 5, 4, 1, 0

        assert self.claim_with(five_of_five_datasets)["confidence"]["level"] == "high"

    def test_without_a_testable_measure_a_confirmed_claim_is_not_high(self):
        def untestable(claim):
            for row in claim["rows"]:
                row["testable"] = False

        assert self.claim_with(untestable)["confidence"]["level"] == "medium"

    def test_a_measure_without_datasets_does_not_break_the_judgement(self):
        def empty_row(claim):
            claim["rows"][2].update({"datasets": 0, "wins": 0, "losses": 0, "ties": 0, "testable": False})

        assert self.claim_with(empty_row)["confidence"]["level"] == "high"

    def test_the_counts_come_from_the_measure_of_the_claim(self):
        def other_primary(claim):
            claim["claim"]["metric"] = "f1"
            claim["rows"][2].update({"wins": 5, "losses": 4})

        result = self.claim_with(other_primary)
        assert (result["datasets_for"], result["datasets_against"], result["primary_metric"]) == (5, 4, "f1")


class TestChartEdges:
    def test_the_best_member_of_the_other_side_is_used(self):
        analysis, ledger = world()
        analysis["claims"][0]["claim"]["other"] = ["MLP", "LogisticRegression"]
        first = build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]["chart"]["points"][0]
        assert first["other"] == pytest.approx(0.85)

    def test_a_failed_dataset_is_not_in_the_method_count(self):
        failed = {KEYS[-1]: {"error": "boom", "attempts": 2}}
        analysis, ledger = world(keys=KEYS[:-1], failed=failed)
        assert build_summary(state(), SPEC, analysis, ledger, "tr")["method"][0] == "8 gerçek veri setinde denendi."

    def test_without_ranks_there_is_no_ranking(self):
        analysis, ledger = world()
        analysis["friedman"] = {}
        assert build_summary(state(), SPEC, analysis, ledger, "tr")["ranking"] == []

    def test_a_running_campaign_lists_the_datasets_of_its_state(self):
        running = state(status="running", datasets={"tb_credit": {"status": "running"}, "tb_pol": {"status": "queued"}})
        result = build_summary(running, SPEC, None, None, "tr")
        assert [item["key"] for item in result["datasets"]] == ["tb_credit", "tb_pol"]

    def test_a_state_without_datasets_lists_the_requested_ones(self):
        analysis, ledger = world()
        result = build_summary({"id": "abc", "title": "T", "status": "completed"}, SPEC, analysis, ledger, "tr")
        assert [item["key"] for item in result["datasets"]] == KEYS


class TestChart:
    def test_the_points_compare_the_best_member_of_each_side(self):
        chart = summary()["claims"][0]["chart"]
        assert chart["metric"] == "roc_auc" and chart["metric_label"] == "ROC-AUC"
        assert chart["subject_label"] == "Random Forest ve Histogram Gradient Boosting grubu" and chart["other_label"] == "Yapay sinir ağı (MLP)"
        assert [point["dataset"] for point in chart["points"]] == KEYS
        first = chart["points"][0]
        assert first["label"] == "Kredi riski" and first["subject"] == pytest.approx(0.92) and first["other"] == pytest.approx(0.85)

    def test_the_points_follow_the_datasets_that_finished(self):
        failed = {KEYS[-1]: {"error": "boom", "attempts": 2}}
        analysis, ledger = world(keys=KEYS[:-1], failed=failed)
        chart = build_summary(state(), SPEC, analysis, ledger, "tr")["claims"][0]["chart"]
        assert [point["dataset"] for point in chart["points"]] == KEYS[:-1]

    def test_the_english_chart_labels(self):
        chart = summary(language="en")["claims"][0]["chart"]
        assert chart["points"][0]["label"] == "Credit risk" and chart["metric_label"] == "ROC-AUC"

    def test_a_claim_with_a_single_model_per_side(self):
        chart = summary()["claims"][1]["chart"]
        assert chart["metric"] == "f1" and chart["subject_label"] == "Yapay sinir ağı (MLP)"


class TestRanking:
    def test_the_models_are_ordered_by_their_average_rank(self):
        ranking = summary()["ranking"]
        assert [item["model"] for item in ranking] == ["HistGradientBoosting", "RandomForest", "MLP", "LogisticRegression"]
        assert [item["position"] for item in ranking] == [1, 2, 3, 4]
        assert ranking[0]["label"] == "Histogram Gradient Boosting" and ranking[0]["average_rank"] == pytest.approx(1.0)

    def test_the_english_labels(self):
        assert summary(language="en")["ranking"][1]["label"] == "Random forest"


class TestMethod:
    def test_the_steps_are_counted_from_the_run(self):
        assert summary()["method"] == [
            "9 gerçek veri setinde denendi.",
            "4 model aynı koşullarda eğitildi ve karşılaştırıldı.",
            f"Her veri setinde veri {len(SPLIT_SEEDS)} kez farklı biçimde eğitim (%80) ve test (%20) olarak bölündü; sonuçlar ortalandı.",
            "Modeller kütüphanelerin varsayılan ayarlarıyla çalıştırıldı.",
            "Farklar veri setleri üzerinden Wilcoxon testi ve Holm düzeltmesiyle istatistiksel olarak sınandı.",
        ]

    def test_the_english_steps(self):
        method = summary(language="en")["method"]
        assert method[0] == "Tried on 9 real datasets." and method[3] == "The models ran with the default settings of their libraries."

    def test_tuning_is_told_from_the_specification(self):
        tuned = {**SPEC, "tuning": {"iterations": 12, "folds": 3}}
        method = summary(spec_value=tuned)["method"]
        assert method[3] == "Her modelin ayarları rastgele aramayla optimize edildi; ayar yapılmamış sürümle de karşılaştırıldı."

    def test_tuning_is_told_from_the_ledger_when_the_specification_is_missing(self):
        analysis, ledger = world()
        for entry in ledger:
            if entry["kind"] == "dataset":
                entry["tuning"] = {"models": {"MLP": {"params": {}, "cv_roc_auc": 0.8}}}
        method = build_summary(state(), None, analysis, ledger, "tr")["method"]
        assert method[3].startswith("Her modelin ayarları")


class TestCautions:
    def test_the_general_caution_is_always_there(self):
        assert summary()["cautions"] == ["Sonuçlar yalnızca denenen 9 veri seti için geçerlidir; başka veri türlerinde farklı çıkabilir."]

    def test_failed_datasets_are_told(self):
        failed = {KEYS[-1]: {"error": "boom", "attempts": 2}}
        analysis, ledger = world(keys=KEYS[:-1], failed=failed)
        cautions = build_summary(state(), SPEC, analysis, ledger, "tr")["cautions"]
        assert "1 veri seti tamamlanamadı ve sonuca dahil edilmedi." in cautions

    def test_too_few_datasets_are_told(self):
        analysis, ledger = world(keys=KEYS[:4])
        cautions = build_summary(state(), SPEC, analysis, ledger, "tr")["cautions"]
        assert "Yeterli sayıda veri seti bitmediği için bazı iddialar test edilemedi." in cautions

    def test_missing_evidence_is_not_equality(self):
        analysis, ledger = world()
        analysis["claims"][0]["verdict"] = "inconclusive"
        cautions = build_summary(state(), SPEC, analysis, ledger, "tr")["cautions"]
        assert "“Kanıt yetersiz”, modellerin eşit olduğu anlamına gelmez; fark küçük olabilir ya da veri az olabilir." in cautions

    def test_a_report_under_review_is_told(self):
        cautions = summary(state=state(status="needs_review", issues=["E9 is cited but not in the ledger"]))["cautions"]
        assert "Rapor otomatik denetimde bir sorun buldu; ayrıntılı rapora bakın." in cautions

    def test_the_english_cautions(self):
        assert summary(language="en")["cautions"] == ["The results hold only for the 9 datasets that were tried; other kinds of data may behave differently."]


class TestProgress:
    def test_a_finished_campaign(self):
        assert summary()["progress"] == {"finished": 9, "failed": 0, "total": 9, "percent": 100}

    def test_a_running_campaign_without_results(self):
        running = state(status="running", datasets={**{key: {"status": "finished"} for key in KEYS[:3]}, **{key: {"status": "queued"} for key in KEYS[3:]}})
        result = build_summary(running, SPEC, None, None, "tr")
        assert result["progress"] == {"finished": 3, "failed": 0, "total": 9, "percent": 33}
        assert result["claims"] == [] and result["ranking"] == [] and result["method"] == [] and result["cautions"] == []

    def test_failed_datasets_count_as_done_in_the_percentage(self):
        mixed = state(datasets={"a": {"status": "finished"}, "b": {"status": "failed"}, "c": {"status": "running"}, "d": {"status": "queued"}})
        assert build_summary(mixed, None, None, None, "tr")["progress"] == {"finished": 1, "failed": 1, "total": 4, "percent": 50}

    def test_no_datasets_no_division_by_zero(self):
        assert build_summary(state(datasets={}), None, None, None, "tr")["progress"]["percent"] == 0


class TestErrors:
    def test_a_failed_campaign_without_analysis_keeps_the_error_text(self):
        failed = state(status="failed", error="RuntimeError: sandbox died")
        assert build_summary(failed, None, None, None, "tr")["error"] == "RuntimeError: sandbox died"

    def test_no_error_is_none(self):
        assert summary()["error"] is None

    def test_an_analysis_without_datasets_gives_no_claims(self):
        result = build_summary(state(), SPEC, {"coverage": {"requested": KEYS, "finished": [], "failed": {}}, "error": "no dataset finished"}, [], "tr")
        assert result["claims"] == [] and result["ranking"] == []
