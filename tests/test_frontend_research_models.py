import re
from pathlib import Path

from app.campaign.protocol import ESTIMATORS
from app.campaign.tuning import MAX_ITERATIONS, MIN_ITERATIONS
from app.campaign.vocabulary import MODEL_NAMES

SOURCE = (Path(__file__).resolve().parents[1] / "frontend" / "lib" / "researchView.ts").read_text(encoding="utf-8")


def listed(name):
    body = re.search(rf"export const {name} = \[(.*?)\];", SOURCE, re.DOTALL).group(1)
    return re.findall(r'"([A-Za-z0-9_]+)"', body)


def test_the_console_offers_every_model_the_session_accepts():
    assert sorted(listed("RESEARCH_MODELS")) == sorted(ESTIMATORS)


def test_the_default_choice_is_part_of_the_list():
    assert set(listed("DEFAULT_RESEARCH_MODELS")) <= set(listed("RESEARCH_MODELS"))


def test_every_listed_model_has_a_plain_name_in_both_languages():
    for language in ("tr", "en"):
        assert set(listed("RESEARCH_MODELS")) <= set(MODEL_NAMES[language])


def test_the_tuning_choice_is_inside_the_allowed_range():
    value = int(re.search(r"export const TUNING_ITERATIONS = (\d+);", SOURCE).group(1))
    assert MIN_ITERATIONS <= value <= MAX_ITERATIONS


def test_the_minimum_number_of_models_matches_the_session():
    assert int(re.search(r"export const MIN_RESEARCH_MODELS = (\d+);", SOURCE).group(1)) == 2
