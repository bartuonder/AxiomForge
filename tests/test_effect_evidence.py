import json

from app.agents.report import SYSTEM_PROMPT, _brief
from app.graph.evidence import effect_sentences, evidence_sentences


def effect(model="RandomForest", metric="roc_auc", difference=0.0123, dz=0.8, p=0.0012, significant=True):
    return {
        "model": model,
        "params": {"n_estimators": 300},
        "metric": metric,
        "mean_difference": difference,
        "effect_size_dz": dz,
        "p_value": p,
        "adjusted_p_value": p,
        "significant": significant,
    }


def test_a_significant_gain_names_the_configured_and_the_default_model():
    [sentence] = effect_sentences([effect()])
    assert sentence == (
        "RandomForest with the listed parameters has a higher mean ROC-AUC than RandomForest with default parameters "
        "(mean difference 0.0123, adjusted p = 0.0012, dz = 0.80)."
    )


def test_a_significant_loss_says_lower_and_keeps_the_numbers_positive():
    [sentence] = effect_sentences([effect(difference=-0.05, dz=-1.4)])
    assert "has a lower mean ROC-AUC than" in sentence
    assert "mean difference 0.0500" in sentence
    assert "dz = 1.40" in sentence


def test_an_insignificant_effect_claims_nothing():
    [sentence] = effect_sentences([effect(significant=False, p=0.4)])
    assert sentence == (
        "No significant effect of the listed parameters on ROC-AUC was found for RandomForest "
        "compared with default parameters (adjusted p = 0.4)."
    )


def test_unknown_metrics_and_empty_input_are_skipped():
    assert effect_sentences([effect(metric="accuracy")]) == []
    assert effect_sentences([]) == []
    assert effect_sentences(None) == []


def test_the_effects_follow_the_performance_sentences():
    decision = {
        "performance": [
            {
                "metric": "f1",
                "a": "A",
                "b": "B",
                "mean_difference": 0.1,
                "effect_size_dz": 1.0,
                "adjusted_p_value": 0.001,
                "significant": True,
            }
        ],
        "parameter_effects": [effect(model="A")],
    }
    sentences = evidence_sentences(decision)
    assert sentences[0].startswith("A has a higher mean F1 than B")
    assert sentences[1].startswith("A with the listed parameters")


def test_the_brief_names_the_control_group_by_its_display_name():
    state = {
        "query": "q",
        "tested_models": ["RandomForest", "RandomForest__default", "XGBoost"],
        "model_results": [{"model": "RandomForest__default", "accuracy": 0.9}],
        "statistical_results": {"RandomForest__default": {"f1_mean": 0.9}, "statistical_conclusion": ""},
        "statistical_decision": {},
    }
    brief = _brief(state, [], "run")
    assert "RandomForest__default" not in brief
    assert json.dumps(["RandomForest", "RandomForest (default)", "XGBoost"]) in brief
    assert '"RandomForest (default)": {"f1_mean": 0.9}' in brief
    assert '"statistical_conclusion": ""' in brief


def test_the_writer_is_told_how_to_describe_the_control_group():
    assert "Model (default)" in SYSTEM_PROMPT
    assert "parameter_effects" in SYSTEM_PROMPT
    assert "kontrol grubu" in SYSTEM_PROMPT
