import pytest

import app.graph.nodes as nodes
from app.agents.consistency import tuning_claim_issues, untuned_model_issues
from app.agents.report import SYSTEM_PROMPT, _brief
from app.graph.evidence import configuration_sentence

RUN_TWELVE = {
    "statement": "KNN with n_neighbors set to 10 has a higher PR-AUC than HistGradientBoosting with learning_rate set to 0.05",
    "dataset": "adult_income",
    "models": ["RandomForest", "LogisticRegression", "KNN", "HistGradientBoosting"],
    "params": {"KNN": {"n_neighbors": 10}, "HistGradientBoosting": {"learning_rate": 0.05}},
}

REAL_SENTENCES = [
    "The models were tuned for specific parameters: the number of trees for Random Forest.",
    "The parameters tuned were the number of trees for Random Forest.",
    "The parameters tuned were the regularization strength for Logistic Regression and the number of neighbors for KNN.",
]


def test_the_run_twelve_spec_gets_one_exact_sentence():
    assert configuration_sentence(RUN_TWELVE) == (
        "KNN (n_neighbors=10) and HistGradientBoosting (learning_rate=0.05) ran with the listed parameters; "
        "RandomForest and LogisticRegression ran with library default parameters."
    )


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ({"models": ["A", "B"], "params": {}}, "A and B ran with library default parameters."),
        ({"models": ["A", "B"]}, "A and B ran with library default parameters."),
        (
            {"models": ["A", "B"], "params": {"A": {"x": 1}, "B": {"y": 2}}},
            "A (x=1) and B (y=2) ran with the listed parameters.",
        ),
        (
            {"models": ["A", "B"], "params": {"A": {"class_weight": "balanced", "C": 2}}},
            "A (class_weight='balanced', C=2) ran with the listed parameters; B ran with library default parameters.",
        ),
        (
            {"models": ["A", "B", "C"], "params": {"B": {"x": None}}},
            "B (x=None) ran with the listed parameters; A and C ran with library default parameters.",
        ),
        (
            {"models": ["A", "B", "C"], "params": {"A": {"x": 1}, "B": {"y": 2}, "C": {"z": 3}}},
            "A (x=1), B (y=2) and C (z=3) ran with the listed parameters.",
        ),
        (
            {"models": ["A", "B", "C", "D"], "params": {"B": {"x": 1}}},
            "B (x=1) ran with the listed parameters; A, C and D ran with library default parameters.",
        ),
        ({"models": ["A", "B"], "params": {"A": {}}}, "A and B ran with library default parameters."),
    ],
)
def test_the_sentence_names_the_configured_models_and_the_rest(spec, expected):
    assert configuration_sentence(spec) == expected


def test_the_models_keep_the_order_of_the_spec():
    spec = {"models": ["Z", "A"], "params": {"A": {"x": 1}}}
    assert configuration_sentence(spec).startswith("A (x=1) ran with the listed parameters; Z ran")


@pytest.mark.parametrize("spec", [None, {}, {"models": []}])
def test_nothing_is_written_without_models(spec):
    assert configuration_sentence(spec) == ""


@pytest.mark.parametrize("sentence", REAL_SENTENCES)
def test_the_real_run_twelve_claims_are_still_caught(sentence):
    assert len(untuned_model_issues(f"# Methodology\n{sentence}\n", RUN_TWELVE)) >= 1


def test_the_prepared_sentence_raises_none_of_the_tuning_checks():
    sentence = configuration_sentence(RUN_TWELVE)
    paper = f"# Methodology\n{sentence}\n"
    assert untuned_model_issues(paper, RUN_TWELVE) == []
    assert tuning_claim_issues(paper, [], RUN_TWELVE) == []
    quiet = [{"model": "KNN", "metric": "f1", "significant": False}]
    assert tuning_claim_issues(paper, quiet, RUN_TWELVE) == []


def test_the_whole_gate_accepts_a_methodology_that_copies_it():
    decision = {"n_splits": 10, "parameter_effects": [], "instability": {"unstable": False, "flagged": []}}
    paper = (
        "# Abstract\nA.\n# Methodology\n"
        + configuration_sentence(RUN_TWELVE)
        + " The models were evaluated on 10 repeated stratified train/test splits.\n# Results\nR.\n# Conclusion\nC.\n"
    )
    state = {
        "paper_markdown": paper,
        "statistical_results": {},
        "statistical_decision": decision,
        "verification_status": "Passed",
        "hypotheses": ["h"],
        "experiment_specs": [RUN_TWELVE],
    }
    joined = " ".join(nodes._gate_issues(state))
    assert "spesifikasyonda parametre yok" not in joined
    assert "Methodology yöntemi" not in joined


def test_the_brief_carries_the_sentence_of_the_selected_hypothesis():
    other = {**RUN_TWELVE, "params": {"RandomForest": {"n_estimators": 150}}}
    state = {
        "query": "q",
        "hypotheses": ["first", "second"],
        "experiment_specs": [other, RUN_TWELVE],
        "selected_hypothesis": 1,
    }
    brief = _brief(state, [], "run")
    heading, _, rest = brief.partition("Configuration sentence")
    assert "Methodology" in rest.split("\n")[0]
    assert "NOT applied" in rest.split("\n")[0]
    assert configuration_sentence(RUN_TWELVE) in rest
    assert configuration_sentence(other) not in brief


def test_a_brief_without_a_spec_has_an_empty_line_under_the_heading():
    brief = _brief({"query": "q"}, [], "run")
    assert "Configuration sentence" in brief
    assert "\n- \n" in brief


def test_the_writer_is_told_to_copy_it_and_not_to_invent_tuning():
    assert "Methodology içinde 'Configuration sentence' cümlesini aynen kopyala" in SYSTEM_PROMPT
    assert "o cümlede olmayanlar uygulanmadı" in SYSTEM_PROMPT
