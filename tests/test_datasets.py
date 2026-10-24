import re
import sys
import types

import numpy as np
import pandas as pd
import pytest

from app.datasets import (
    BENCHMARK_ID,
    BENCHMARK_ROWS,
    DATASETS,
    SYNTHETIC_CALLS,
    benchmark_keys,
    core_keys,
    data_brief,
    dataset_code_error,
    dataset_keys,
    dataset_menu,
    describe,
    hf_ids,
    loader_code,
    pick_dataset,
)
from app.tracking.mlflow_logger import parse_dataset_profile

KEYS = list(DATASETS)

MODELS_TAIL = """
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
models = {"LogisticRegression": with_preprocessing(LogisticRegression(max_iter=500))}
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
"""


def fake_frame(key, rows=None):
    entry = DATASETS[key]
    size = rows or ((entry["max_rows"] or entry.get("keep_positives", 0) * 2) + 800 if entry["max_rows"] or entry.get("keep_positives") else 600)
    rng = np.random.default_rng(0)
    positive = entry["positive"]
    negative = "other" if isinstance(positive, str) else 0
    labels = [positive if index % 5 == 0 else negative for index in range(size)]
    data = {
        "f1": rng.normal(size=size),
        "f2": rng.normal(size=size),
        "cat": rng.choice(["a", "b", "c"], size=size),
        entry["target"]: labels,
    }
    for name in entry["drop"]:
        data[name] = np.arange(size) if name != "Unnamed: 32" else np.nan
    if key == "customer_churn":
        data["TotalCharges"] = [" " if index % 50 == 0 else str(10.0 + index) for index in range(size)]
    return pd.DataFrame(data)


@pytest.fixture
def hub(monkeypatch):
    calls = []

    def load_dataset(name, config=None, split=None):
        calls.append((name, config, split))
        key = next(
            candidate
            for candidate, entry in DATASETS.items()
            if entry["hf_id"] == name and entry.get("config") == config
        )
        frame = fake_frame(key)
        return types.SimpleNamespace(to_pandas=lambda: frame)

    monkeypatch.setitem(sys.modules, "datasets", types.SimpleNamespace(load_dataset=load_dataset))
    return calls


def run(key):
    namespace = {}
    exec(loader_code(key) + MODELS_TAIL, namespace)
    return namespace


def test_the_registry_is_made_of_real_hub_ids():
    assert len(KEYS) == 14
    assert dataset_keys() == KEYS
    assert len({(entry["hf_id"], entry.get("config")) for entry in DATASETS.values()}) == 14
    assert len(set(hf_ids())) == 6
    for entry in DATASETS.values():
        assert re.fullmatch(r"[\w.-]+/[\w.-]+", entry["hf_id"])


def test_the_core_and_the_benchmark_groups_split_the_registry():
    assert core_keys() == ["breast_cancer", "credit_default", "customer_churn", "adult_income", "credit_fraud"]
    assert len(benchmark_keys()) == 9
    assert set(core_keys()) | set(benchmark_keys()) == set(KEYS)
    assert not set(core_keys()) & set(benchmark_keys())


@pytest.mark.parametrize("key", benchmark_keys())
def test_every_benchmark_entry_names_its_hub_configuration(key):
    entry = DATASETS[key]
    assert entry["hf_id"] == BENCHMARK_ID
    assert re.fullmatch(r"clf_num_[\w-]+", entry["config"])
    assert entry["max_rows"] == BENCHMARK_ROWS
    assert "Grinsztajn" in entry["summary"]
    assert f'load_dataset("{BENCHMARK_ID}", "{entry["config"]}", split="train")' in loader_code(key)


def test_the_planner_menu_and_the_domain_pick_stay_on_the_core_group():
    menu = dataset_menu()
    assert all(f"- {key}:" in menu for key in core_keys())
    assert "tb_" not in menu
    for text in ("credit scoring delinquency", "California housing price", "gamma telescope", "benchmark", "electricity market"):
        assert pick_dataset(text) in core_keys()


def test_a_benchmark_key_is_a_valid_spec_dataset():
    from app.agents.spec import validate_spec

    spec = validate_spec(
        {"statement": "RandomForest has a higher ROC-AUC than KNN", "dataset": "tb_credit",
         "claim": {"kind": "performance", "metric": "roc_auc", "subject": "RandomForest", "other": "KNN"}},
        ["RandomForest", "KNN"],
    )
    assert spec["dataset"] == "tb_credit"


@pytest.mark.parametrize("key", KEYS)
def test_a_block_has_no_comments_and_names_its_source(key):
    text = loader_code(key)
    assert "#" not in text
    config = DATASETS[key].get("config")
    source = f'"{DATASETS[key]["hf_id"]}", "{config}", ' if config else f'"{DATASETS[key]["hf_id"]}", '
    assert f"load_dataset({source}split=\"train\")" in text
    compile(text, key, "exec")


@pytest.mark.parametrize("key", KEYS)
def test_a_block_runs_and_prints_a_profile_the_parser_reads(key, hub, capsys):
    namespace = run(key)
    profile = parse_dataset_profile(capsys.readouterr().out)
    assert profile["dataset"] == key
    assert profile["samples"] == float(len(namespace["y"]))
    assert profile["features"] == float(namespace["X"].shape[1])
    assert 0.0 < profile["positive_ratio"] < 1.0
    assert hub == [(DATASETS[key]["hf_id"], DATASETS[key].get("config"), "train")]


@pytest.mark.parametrize("key", KEYS)
def test_the_target_and_the_dropped_columns_leave_the_features(key, hub):
    namespace = run(key)
    columns = set(namespace["X"].columns)
    assert DATASETS[key]["target"] not in columns
    assert not columns & set(DATASETS[key]["drop"])
    assert set(np.unique(namespace["y"])) == {0, 1}


@pytest.mark.parametrize("key", KEYS)
def test_the_preprocessing_lives_in_the_pipeline_and_fits_on_the_training_part(key, hub):
    namespace = run(key)
    model = namespace["models"]["LogisticRegression"]
    assert [name for name, _ in model.steps] == ["prep", "model"]
    model.fit(namespace["X_train"], namespace["y_train"])
    assert model.predict_proba(namespace["X_test"]).shape[1] == 2


@pytest.mark.parametrize("key", [name for name, entry in DATASETS.items() if entry["max_rows"]])
def test_a_large_set_is_sampled_with_a_fixed_seed(key, hub):
    namespace = run(key)
    assert len(namespace["y"]) == DATASETS[key]["max_rows"]
    assert np.array_equal(namespace["y"], run(key)["y"])


def test_the_fraud_set_keeps_every_positive(hub):
    namespace = run("credit_fraud")
    expected_positives = int((fake_frame("credit_fraud")["Class"] == 1).sum())
    assert int(namespace["y"].sum()) == expected_positives
    assert len(namespace["y"]) - expected_positives == min(
        DATASETS["credit_fraud"]["keep_positives"], len(fake_frame("credit_fraud")) - expected_positives
    )


def test_blank_total_charges_become_missing_values_not_errors(hub):
    namespace = run("customer_churn")
    assert namespace["X"]["TotalCharges"].isna().any()
    assert "TotalCharges" in namespace["numeric"]


def test_the_menu_and_the_description_name_every_set():
    menu = dataset_menu()
    for key in core_keys():
        assert f"- {key}:" in menu
    for key in KEYS:
        assert DATASETS[key]["hf_id"] in describe(key)
        if DATASETS[key].get("config"):
            assert DATASETS[key]["config"] in describe(key)


SCRIPT = loader_code("customer_churn") + MODELS_TAIL


def test_a_script_with_the_pasted_block_passes():
    assert dataset_code_error(SCRIPT, "customer_churn") == ""
    assert dataset_code_error(SCRIPT, None) == ""


def test_the_block_may_be_reformatted_but_not_changed():
    loose = SCRIPT.replace('split="train"', "split='train'")
    assert dataset_code_error(loose, "customer_churn") == ""
    changed = SCRIPT.replace('split="train"', 'split="test"')
    assert "must be pasted unchanged" in dataset_code_error(changed, "customer_churn")


def test_another_dataset_block_does_not_satisfy_the_chosen_one():
    other = loader_code("breast_cancer") + MODELS_TAIL
    assert "customer_churn" in dataset_code_error(other, "customer_churn")
    assert dataset_code_error(other, None) == ""


def test_a_missing_block_is_reported_with_the_first_missing_statement():
    message = dataset_code_error(MODELS_TAIL, "credit_default")
    assert "credit_default" in message
    assert "must be pasted unchanged" in message


@pytest.mark.parametrize("call", sorted(SYNTHETIC_CALLS))
def test_every_synthetic_or_bundled_loader_is_rejected(call):
    message = dataset_code_error(SCRIPT + f"\nX2 = {call}()\n", "customer_churn")
    assert call in message
    assert "Hugging Face" in message


def test_a_dotted_synthetic_call_is_rejected_too():
    assert "make_classification" in dataset_code_error(SCRIPT + "\nimport sklearn.datasets as d\nd.make_classification()\n", None)


def test_a_syntax_error_is_left_to_the_sandbox():
    assert dataset_code_error("x = (", "customer_churn") == ""


@pytest.mark.parametrize("key", [name for name, entry in DATASETS.items() if not entry["max_rows"] and not entry.get("keep_positives")])
def test_the_positive_label_becomes_one(key, hub):
    namespace = run(key)
    frame = fake_frame(key)
    assert int(namespace["y"].sum()) == int((frame[DATASETS[key]["target"]] == DATASETS[key]["positive"]).sum())


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Compare SVM and RandomForest on tumour diagnosis", "breast_cancer"),
        ("credit card fraud detection with rare events", "credit_fraud"),
        ("Will the credit card client default on the loan", "credit_default"),
        ("customer churn in a telecom subscription", "customer_churn"),
        ("predict income from census demographics", "adult_income"),
        ("something with no known domain", "customer_churn"),
        ("", "customer_churn"),
    ],
)
def test_the_dataset_follows_the_domain_of_the_text(text, expected):
    assert pick_dataset(text) == expected


def test_the_brief_pastes_the_block_and_forbids_generators():
    brief = data_brief("adult_income")
    assert loader_code("adult_income") in brief
    assert "with_preprocessing" in brief
    assert "do not generate or simulate data" in brief


VERIFIED_BENCHMARK_TARGETS = {
    "tb_credit": ("clf_num_credit", "SeriousDlqin2yrs", 1),
    "tb_california": ("clf_num_california", "price_above_median", 1),
    "tb_electricity": ("clf_num_electricity", "class", "UP"),
    "tb_magic": ("clf_num_MagicTelescope", "class", "h"),
    "tb_bank": ("clf_num_bank-marketing", "Class", 2),
    "tb_heloc": ("clf_num_heloc", "RiskPerformance", 1),
    "tb_house16h": ("clf_num_house_16H", "binaryClass", "P"),
    "tb_pol": ("clf_num_pol", "binaryClass", "P"),
    "tb_eye": ("clf_num_eye_movements", "label", 1),
}


def test_the_benchmark_targets_are_the_ones_checked_in_the_real_sandbox():
    assert set(VERIFIED_BENCHMARK_TARGETS) == set(benchmark_keys())
    for key, (config, target, positive) in VERIFIED_BENCHMARK_TARGETS.items():
        entry = DATASETS[key]
        assert (entry["config"], entry["target"], entry["positive"]) == (config, target, positive)
