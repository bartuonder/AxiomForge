import pytest

from app.campaign.demos import DEMOS, GRINSZTAJN_2022, demo_names, demo_spec
from app.campaign.spec import CampaignSpecError, validate_campaign
from app.campaign.stats import MIN_DATASETS
from app.datasets import benchmark_keys


@pytest.mark.parametrize("name", sorted(DEMOS))
def test_every_demo_is_a_valid_campaign(name):
    spec = validate_campaign(demo_spec(name))
    assert spec["datasets"] == benchmark_keys() and len(spec["datasets"]) >= MIN_DATASETS
    assert spec["source"]["url"].startswith("https://arxiv.org/abs/")
    assert spec["source"]["deviations"]


def test_the_grinsztajn_demo_compares_trees_with_the_network_and_the_linear_model():
    spec = validate_campaign(demo_spec("grinsztajn-2022"))
    first, second = spec["claims"]
    assert first["subject"] == ["RandomForest", "HistGradientBoosting"] and first["other"] == ["MLP"]
    assert second["other"] == ["LogisticRegression"]
    assert first["metrics"] == second["metrics"] == ["roc_auc", "pr_auc", "f1"]
    assert spec["params"] == {}


def test_the_demo_is_honest_about_what_differs_from_the_paper():
    notes = " ".join(GRINSZTAJN_2022["source"]["deviations"])
    for fragment in ("hyperparameter search", "6000-row", "MLPClassifier", "nine"):
        assert fragment in notes


def test_a_demo_is_returned_as_a_copy_that_can_be_changed_freely():
    spec = demo_spec("grinsztajn-2022")
    spec["models"].append("KNN")
    spec["claims"][0]["subject"].append("KNN")
    assert demo_spec("grinsztajn-2022")["models"] == GRINSZTAJN_2022["models"]
    assert GRINSZTAJN_2022["claims"][0]["subject"] == ["RandomForest", "HistGradientBoosting"]


def test_an_unknown_demo_lists_the_available_ones():
    with pytest.raises(CampaignSpecError, match="available: grinsztajn-2022"):
        demo_spec("nope")
    assert demo_names() == ["grinsztajn-2022"]
