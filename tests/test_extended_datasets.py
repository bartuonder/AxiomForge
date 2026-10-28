import pytest

from app.campaign.vocabulary import DATASET_NAMES, pretty_dataset
from app.datasets import BENCHMARK_ID, BENCHMARK_ROWS, DATASETS, benchmark_keys, core_keys, dataset_menu, extended_keys, loader_code, research_pool

NEW = ["tb_bioresponse", "tb_diabetes", "tb_higgs", "tb_miniboone", "tb_covertype", "tb_creditcard", "tb_jannis"]


def test_the_seven_remaining_numeric_benchmark_sets_are_registered_in_their_own_group():
    assert extended_keys() == NEW
    assert all(DATASETS[key]["group"] == "extended" for key in NEW)


def test_the_default_benchmark_and_the_core_sets_do_not_change():
    assert len(benchmark_keys()) == 9 and not set(NEW) & set(benchmark_keys())
    assert not set(NEW) & set(core_keys())
    assert not any(key in dataset_menu() for key in NEW)


def test_the_research_pool_is_the_benchmark_plus_the_extended_sets_in_a_fixed_order():
    assert research_pool() == benchmark_keys() + NEW
    assert len(research_pool()) == 16 and len(set(research_pool())) == 16


@pytest.mark.parametrize("key,config,target,positive", [
    ("tb_bioresponse", "clf_num_Bioresponse", "target", 1),
    ("tb_diabetes", "clf_num_Diabetes130US", "readmitted", 1),
    ("tb_higgs", "clf_num_Higgs", "target", 1),
    ("tb_miniboone", "clf_num_MiniBooNE", "signal", True),
    ("tb_covertype", "clf_num_covertype", "Y", 1),
    ("tb_creditcard", "clf_num_default-of-credit-card-clients", "y", 1),
    ("tb_jannis", "clf_num_jannis", "class", 1),
])
def test_each_new_set_points_at_its_benchmark_config_and_target(key, config, target, positive):
    entry = DATASETS[key]
    assert entry["hf_id"] == BENCHMARK_ID and entry["config"] == config
    assert entry["target"] == target and entry["positive"] == positive
    assert entry["max_rows"] == (None if key == "tb_bioresponse" else BENCHMARK_ROWS) and entry["drop"] == [] and entry["clean"] == []


def test_the_loader_of_a_new_set_reads_its_config_and_samples_it_like_the_others():
    code = loader_code("tb_miniboone")
    assert 'load_dataset("inria-soda/tabular-benchmark", "clf_num_MiniBooNE", split="train")' in code
    assert f"sample(n={BENCHMARK_ROWS}, random_state=0)" in code
    assert '(frame["signal"] == True).astype(int)' in code


@pytest.mark.parametrize("language", ["tr", "en"])
def test_every_new_set_has_a_plain_name(language):
    for key in NEW:
        assert key in DATASET_NAMES[language] and pretty_dataset(key, language) != key


def test_the_small_set_uses_all_its_rows_and_its_loader_does_not_sample():
    assert "all rows used" in DATASETS["tb_bioresponse"]["summary"] and "rows sampled" not in DATASETS["tb_bioresponse"]["summary"]
    assert ".sample(n=" not in loader_code("tb_bioresponse")
    assert all("rows sampled" in DATASETS[key]["summary"] for key in NEW if key != "tb_bioresponse")


def test_every_new_set_has_a_summary_that_names_the_benchmark():
    for key in NEW:
        assert "Grinsztajn" in DATASETS[key]["summary"] and DATASETS[key]["topics"] == "benchmark"
