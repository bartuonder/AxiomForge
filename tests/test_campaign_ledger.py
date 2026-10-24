import hashlib
import json

import pytest

from app.campaign.analysis import analyze_campaign
from app.campaign.ledger import build_ledger, find, script_digest
from app.datasets import DATASETS

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
SPEC = {
    "models": MODELS,
    "params": {"MLP": {"alpha": 0.01}},
    "claims": [
        {"id": "C1", "statement": "Trees beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc"],
         "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]},
    ],
}
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}
KEYS = ["tb_credit", "tb_california", "tb_electricity", "tb_magic", "tb_bank", "tb_heloc", "tb_house16h"]


def summary(shift):
    record = {name: {f"{metric}_mean": value + shift for metric in ("roc_auc", "pr_auc", "f1")} for name, value in BASE.items()}
    record["MLP__default"] = {f"{metric}_mean": 0.84 + shift for metric in ("roc_auc", "pr_auc", "f1")}
    record["statistical_conclusion"] = "text"
    return record


def outcome(keys=KEYS, failed=None):
    return {
        "order": list(keys) + list(failed or {}),
        "datasets": {
            key: {
                "summary": summary(0.001 * index),
                "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
                "seconds": 12.5,
                "attempts": 1,
                "script": f"script of {key}",
            }
            for index, key in enumerate(keys)
        },
        "failed": failed or {},
    }


def ledger_for(**kwargs):
    data = outcome(**kwargs)
    return build_ledger(SPEC, data, analyze_campaign(SPEC, data))


def test_ids_are_sequential_unique_and_typed():
    ledger = ledger_for()
    assert [entry["id"] for entry in ledger] == [f"E{index}" for index in range(1, len(ledger) + 1)]
    kinds = [entry["kind"] for entry in ledger]
    assert kinds.count("dataset") == 7
    assert kinds.count("claim") == 2
    assert kinds.count("friedman") == 3
    assert kinds.count("pairwise") == 18
    assert kinds.count("effect") == 3
    assert kinds.count("failure") == 0


def test_the_datasets_come_first_then_the_claims_then_the_tests():
    kinds = [entry["kind"] for entry in ledger_for()]
    assert kinds[:7] == ["dataset"] * 7
    assert kinds[7:9] == ["claim", "claim"]
    assert kinds[9:12] == ["friedman"] * 3
    assert kinds[-3:] == ["effect"] * 3


def test_a_dataset_entry_names_its_source_size_and_script():
    entry = find(ledger_for(), "dataset", "tb_credit")
    assert entry["source"] == "inria-soda/tabular-benchmark (clf_num_credit)"
    assert (entry["samples"], entry["features"], entry["positive_ratio"]) == (6000.0, 10.0, 0.5)
    assert entry["seconds"] == 12.5 and entry["attempts"] == 1
    assert entry["script_sha256"] == hashlib.sha256(b"script of tb_credit").hexdigest()
    assert set(entry["means"]) == set(MODELS)
    assert entry["means"]["RandomForest"] == {"roc_auc": 0.9, "pr_auc": 0.9, "f1": 0.9}


def test_a_core_dataset_has_no_configuration_in_its_source():
    data = outcome(["breast_cancer", "credit_default"])
    entry = find(build_ledger(SPEC, data, analyze_campaign(SPEC, data)), "dataset", "breast_cancer")
    assert entry["source"] == DATASETS["breast_cancer"]["hf_id"]


def test_the_controls_never_appear_in_the_dataset_means():
    assert "MLP__default" not in find(ledger_for(), "dataset", "tb_credit")["means"]


def test_a_claim_entry_carries_the_test_row_and_its_claim_id():
    entry = find(ledger_for(), "claim", "C1:roc_auc")
    assert entry["claim"] == "C1" and entry["metric"] == "roc_auc"
    assert entry["verdict"] == "replicated" and entry["wins"] == 7 and entry["significant"] is True
    assert entry["adjusted_p_value"] == pytest.approx(2 * 2 / 2**7)


def test_pairwise_friedman_and_effect_entries_are_addressed_by_key():
    ledger = ledger_for()
    assert find(ledger, "pairwise", "roc_auc:RandomForest:HistGradientBoosting")["losses"] == 7
    assert find(ledger, "friedman", "pr_auc")["mean_ranks"]["HistGradientBoosting"] == 1.0
    effect = find(ledger, "effect", "MLP:f1")
    assert effect["params"] == {"alpha": 0.01} and effect["wins"] == 7


def test_failures_are_recorded_and_the_analysis_still_follows():
    ledger = ledger_for(keys=KEYS, failed={"tb_pol": {"error": "x" * 400, "attempts": 2}})
    failure = find(ledger, "failure", "tb_pol")
    assert failure["attempts"] == 2 and len(failure["error"]) == 300
    assert [entry["kind"] for entry in ledger].count("claim") == 2


def test_a_campaign_where_nothing_finished_has_only_failures():
    failed = {"tb_credit": {"error": "e", "attempts": 2}, "tb_pol": {"error": "e", "attempts": 2}}
    data = {"order": list(failed), "datasets": {}, "failed": failed}
    ledger = build_ledger(SPEC, data, analyze_campaign(SPEC, data))
    assert [entry["kind"] for entry in ledger] == ["failure", "failure"]


def test_the_lookup_fails_loudly_for_a_missing_entry():
    with pytest.raises(KeyError, match="claim C9:roc_auc"):
        find(ledger_for(), "claim", "C9:roc_auc")


def test_the_ledger_is_plain_json_and_deterministic():
    first, second = ledger_for(), ledger_for()
    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_the_digest_is_the_sha256_of_the_script_text():
    assert script_digest("a") == hashlib.sha256(b"a").hexdigest()
    assert script_digest("a") != script_digest("b")


def test_the_lookup_distinguishes_kinds_that_share_a_key():
    ledger = [{"id": "E1", "kind": "dataset", "key": "x"}, {"id": "E2", "kind": "failure", "key": "x"}]
    assert find(ledger, "failure", "x")["id"] == "E2"
    assert find(ledger, "dataset", "x")["id"] == "E1"
