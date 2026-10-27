import pytest

from app.campaign.protocol import ESTIMATORS
from app.campaign.stats import METRICS
from app.campaign.vocabulary import (
    DATASET_NAMES,
    GLOSSARY,
    LANGUAGES,
    METRIC_LABELS,
    MODEL_NAMES,
    STATUS_LABELS,
    VERDICTS,
    pretty_dataset,
    pretty_model,
)
from app.datasets import DATASETS


def test_the_languages():
    assert LANGUAGES == ("tr", "en") and LANGUAGES[0] == "tr"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_runnable_model_has_a_plain_name(language):
    assert set(ESTIMATORS) <= set(MODEL_NAMES[language])
    assert all(MODEL_NAMES[language][key].strip() for key in ESTIMATORS)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_dataset_has_a_plain_name(language):
    assert set(DATASETS) <= set(DATASET_NAMES[language])
    assert all(DATASET_NAMES[language][key].strip() for key in DATASETS)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_metric_has_a_label_and_an_explanation(language):
    for metric in METRICS:
        assert METRIC_LABELS[language][metric]["name"].strip() and METRIC_LABELS[language][metric]["meaning"].strip()


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_verdict_has_every_text(language):
    for verdict in ("replicated", "partially_replicated", "contradicted", "inconclusive", "not_testable"):
        entry = VERDICTS[verdict]
        assert entry["tone"] in {"positive", "negative", "neutral", "warning", "muted"}
        for field in ("label", "meaning"):
            assert entry[language][field].strip()


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_campaign_status_has_a_label(language):
    for status in ("queued", "running", "completed", "needs_review", "failed"):
        assert STATUS_LABELS[language][status].strip()


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_glossary_explains_the_terms_the_pages_use(language):
    terms = {"campaign", "claim", "dataset", "verdict", "roc_auc", "pr_auc", "f1", "tuned", "wilcoxon", "holm", "sandbox", "evidence", "confidence"}
    assert terms <= set(GLOSSARY[language])
    for entry in GLOSSARY[language].values():
        assert entry["term"].strip() and entry["explanation"].strip()


def test_both_languages_define_the_same_glossary_terms():
    assert set(GLOSSARY["tr"]) == set(GLOSSARY["en"])


def test_pretty_names_fall_back_to_the_key():
    assert pretty_model("RandomForest", "tr") == MODEL_NAMES["tr"]["RandomForest"]
    assert pretty_model("Unknown", "tr") == "Unknown"
    assert pretty_dataset("tb_credit", "en") == DATASET_NAMES["en"]["tb_credit"]
    assert pretty_dataset("nope", "en") == "nope"


def test_the_turkish_texts_do_not_leak_english_jargon_in_labels():
    assert VERDICTS["replicated"]["tr"]["label"] == "Doğrulandı"
    assert VERDICTS["contradicted"]["tr"]["label"] == "Çürütüldü"
    assert VERDICTS["inconclusive"]["tr"]["label"] == "Kanıt yetersiz"
    assert VERDICTS["partially_replicated"]["tr"]["label"] == "Kısmen doğrulandı"
    assert VERDICTS["not_testable"]["tr"]["label"] == "Test edilemedi"


def test_the_english_labels():
    assert VERDICTS["replicated"]["en"]["label"] == "Confirmed"
    assert VERDICTS["contradicted"]["en"]["label"] == "Refuted"
    assert VERDICTS["inconclusive"]["en"]["label"] == "Not enough evidence"
    assert VERDICTS["partially_replicated"]["en"]["label"] == "Partly confirmed"
    assert VERDICTS["not_testable"]["en"]["label"] == "Could not be tested"


def test_the_tones():
    assert [VERDICTS[v]["tone"] for v in ("replicated", "contradicted", "inconclusive", "partially_replicated", "not_testable")] == ["positive", "negative", "neutral", "warning", "muted"]
