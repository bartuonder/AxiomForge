import pytest

import app.graph.nodes as nodes
from app.agents.consistency import leakage_description_issues
from app.agents.report import SYSTEM_PROMPT

METHODOLOGY = (
    "All features were standardized using StandardScaler fitted on the entire dataset before splitting "
    "into training and testing sets. The experiment included a control group with default parameters."
)
ABSTRACT = (
    "All features were standardized using StandardScaler before splitting the dataset into training "
    "and testing sets."
)


def paper(sentence):
    return f"# Abstract\nWe compare two models.\n# Methodology\n{sentence}\n# Results\nNone.\n"


@pytest.mark.parametrize(
    "sentence",
    [
        METHODOLOGY,
        ABSTRACT,
        "The features were scaled with StandardScaler on the whole dataset.",
        "Normalization was applied to the full data prior to the train-test split.",
        "Missing values were imputed before the split using all of the data.",
        "PCA was fitted ahead of partitioning the samples.",
    ],
)
def test_a_leaky_preprocessing_description_is_flagged_when_verification_passed(sentence):
    issues = leakage_description_issues(paper(sentence), "Passed")
    assert len(issues) == 1
    assert sentence[:40] in issues[0]


@pytest.mark.parametrize(
    "sentence",
    [
        "StandardScaler was fitted on the training split only and applied to the test split.",
        "Features were standardized after splitting the dataset into training and testing sets.",
        "Scaling was fitted after the train-test split, never on the entire dataset.",
        "The scaler was not fitted on the whole dataset before splitting.",
        "The scaler was fitted after the split on the training part, and the whole dataset was only used for the split.",
        "The dataset has 1000 samples and 3 features.",
        "The data were split before training the models.",
        "No data leakage or execution errors were detected during the experiment.",
    ],
)
def test_an_honest_description_passes(sentence):
    assert leakage_description_issues(paper(sentence), "Passed") == []


def test_a_failed_verification_may_describe_the_leak():
    assert leakage_description_issues(paper(METHODOLOGY), "Failed") == []
    assert leakage_description_issues(paper(METHODOLOGY), "") == []


def test_a_table_row_is_not_prose():
    table = "| Model | note |\n| --- | --- |\n| scaled on the entire dataset before splitting | x |\n"
    assert leakage_description_issues(table, "Passed") == []


STATE = {
    "paper_markdown": "",
    "statistical_results": {},
    "statistical_decision": {},
    "verification_status": "Passed",
}


def test_the_gate_sends_back_the_paper_of_the_real_run():
    issues = nodes._gate_issues({**STATE, "paper_markdown": paper(METHODOLOGY)})
    assert any("veri bölünmeden önce" in issue for issue in issues)


def test_the_gate_accepts_a_corrected_description():
    text = paper("StandardScaler was fitted on the training split only and applied to the test split.")
    issues = nodes._gate_issues({**STATE, "paper_markdown": text})
    assert not any("veri bölünmeden önce" in issue for issue in issues)


def test_the_writer_is_told_to_describe_the_final_code():
    assert "Final code ile aynı olmalı" in SYSTEM_PROMPT
    assert "yalnız eğitim bölümüne uydurulup" in SYSTEM_PROMPT
