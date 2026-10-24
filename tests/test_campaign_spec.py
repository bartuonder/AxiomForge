import pytest

from app.campaign.spec import (
    MAX_NOTES,
    MAX_STATEMENT,
    MAX_TITLE,
    CampaignSpecError,
    validate_campaign,
)
from app.datasets import benchmark_keys

CLAIM = {
    "id": "C1",
    "statement": "Tree-based models beat the MLP",
    "metric": "roc_auc",
    "subject": ["RandomForest", "HistGradientBoosting"],
    "other": ["MLP"],
}


def raw(**overrides):
    base = {
        "title": "Trees against neural networks",
        "models": ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"],
        "datasets": ["tb_credit", "tb_california", "tb_electricity"],
        "claims": [dict(CLAIM)],
    }
    base.update(overrides)
    return base


def test_a_valid_campaign_is_normalised():
    spec = validate_campaign(raw(title="  Trees   against   neural networks "))
    assert spec["title"] == "Trees against neural networks"
    assert spec["models"] == ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
    assert spec["params"] == {}
    assert spec["datasets"] == ["tb_credit", "tb_california", "tb_electricity"]
    assert spec["source"] == {}
    assert spec["claims"] == [{**CLAIM, "metrics": ["roc_auc"]}]


def test_datasets_default_to_the_whole_benchmark_pool():
    data = raw()
    del data["datasets"]
    assert validate_campaign(data)["datasets"] == benchmark_keys()


def test_a_claim_gets_an_id_when_none_is_given():
    claim = {key: value for key, value in CLAIM.items() if key != "id"}
    second = {**claim, "subject": "MLP", "other": "LogisticRegression", "statement": "MLP beats LR"}
    spec = validate_campaign(raw(claims=[claim, second]))
    assert [item["id"] for item in spec["claims"]] == ["C1", "C2"]
    assert spec["claims"][1]["subject"] == ["MLP"]


def test_a_claim_may_name_several_metrics():
    spec = validate_campaign(raw(claims=[{**CLAIM, "metrics": ["roc_auc", "f1", "roc_auc"]}]))
    assert spec["claims"][0]["metrics"] == ["roc_auc", "f1"]
    assert spec["claims"][0]["metric"] == "roc_auc"


def test_parameters_are_checked_against_the_allowed_list_and_the_library_defaults():
    spec = validate_campaign(raw(params={"RandomForest": {"n_estimators": 300}, "MLP": {}}))
    assert spec["params"] == {"RandomForest": {"n_estimators": 300}}
    with pytest.raises(CampaignSpecError, match="does not allow parameter booster"):
        validate_campaign(raw(params={"RandomForest": {"booster": "gbtree"}}))
    with pytest.raises(CampaignSpecError, match="library default"):
        validate_campaign(raw(params={"RandomForest": {"n_estimators": 100}}))
    with pytest.raises(CampaignSpecError, match="does not run"):
        validate_campaign(raw(params={"KNN": {"n_neighbors": 7}}))
    with pytest.raises(CampaignSpecError, match="must be a number, a string or null"):
        validate_campaign(raw(params={"RandomForest": {"n_estimators": [1]}}))
    with pytest.raises(CampaignSpecError, match="must be a number, a string or null"):
        validate_campaign(raw(params={"RandomForest": {"n_estimators": True}}))
    with pytest.raises(CampaignSpecError, match="must be an object"):
        validate_campaign(raw(params={"RandomForest": 5}))
    with pytest.raises(CampaignSpecError, match="keyed by model name"):
        validate_campaign(raw(params=[1]))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"title": ""}, "title is missing"),
        ({"title": "x" * (MAX_TITLE + 1)}, "title is longer"),
        ({"models": "RandomForest"}, "list of model names"),
        ({"models": ["RandomForest"]}, "at least two models"),
        ({"models": ["RandomForest", "RandomForest"]}, "must not repeat"),
        ({"models": ["RandomForest", "Prophet"]}, "unknown models: Prophet"),
        ({"datasets": "tb_credit"}, "list of dataset keys"),
        ({"datasets": ["tb_credit"]}, "at least two datasets"),
        ({"datasets": ["tb_credit", "tb_credit"]}, "must not repeat"),
        ({"datasets": ["tb_credit", "mnist"]}, "unknown datasets: mnist"),
        ({"claims": []}, "at least one claim"),
        ({"claims": ["x"]}, "must be an object"),
        ({"claims": [{**CLAIM, "statement": ""}]}, "statement is missing"),
        ({"claims": [{**CLAIM, "statement": "x" * (MAX_STATEMENT + 1)}]}, "longer than"),
        ({"claims": [{**CLAIM, "metric": "accuracy"}]}, "metrics must come from"),
        ({"claims": [{**CLAIM, "metrics": ["roc_auc", "accuracy"]}]}, "metrics must come from"),
        ({"claims": [{**CLAIM, "subject": []}]}, "subject must be a model name"),
        ({"claims": [{**CLAIM, "subject": ["KNN"]}]}, "does not run: KNN"),
        ({"claims": [{**CLAIM, "other": ["RandomForest"]}]}, "compares a model with itself"),
        ({"claims": [{**CLAIM, "id": "1bad"}]}, "is not valid"),
        ({"claims": [CLAIM, CLAIM]}, "claim ids must be unique"),
    ],
)
def test_an_invalid_campaign_is_refused_with_the_reason(override, message):
    with pytest.raises(CampaignSpecError, match=message):
        validate_campaign(raw(**override))


def test_a_campaign_must_be_an_object():
    with pytest.raises(CampaignSpecError, match="JSON object"):
        validate_campaign([1])


def test_the_source_keeps_the_paper_and_its_deviations():
    spec = validate_campaign(
        raw(
            source={
                "title": "Why do tree-based models still outperform deep learning on tabular data?",
                "citation": "Grinsztajn et al., NeurIPS 2022",
                "url": "https://arxiv.org/abs/2207.08815",
                "deviations": ["no hyperparameter search", "6000 rows"],
                "ignored": "x",
            }
        )
    )
    assert spec["source"]["citation"] == "Grinsztajn et al., NeurIPS 2022"
    assert spec["source"]["deviations"] == ["no hyperparameter search", "6000 rows"]
    assert "ignored" not in spec["source"]


def test_the_deviation_list_is_bounded():
    with pytest.raises(CampaignSpecError, match="deviations"):
        validate_campaign(raw(source={"deviations": ["note"] * (MAX_NOTES + 1)}))
    with pytest.raises(CampaignSpecError, match="deviations"):
        validate_campaign(raw(source={"deviations": "one note"}))
    with pytest.raises(CampaignSpecError, match="must be an object"):
        validate_campaign(raw(source="paper"))
