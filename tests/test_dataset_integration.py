from types import SimpleNamespace

import pytest

import app.agents.planner as planner
import app.experiments as experiments
from app.agents.experiment import PROMPT_VERSION, SYSTEM_PROMPT, _task, requested_models
from app.agents.report import SYSTEM_PROMPT as REPORT_PROMPT
from app.agents.report import _brief
from app.agents.spec import validate_spec
from app.datasets import DATASETS, dataset_menu, loader_code
from app.graph.verifier import LEAKAGE_PROMPT

MODELS = requested_models("Compare SVM and KNN")
SPEC_KEYS = ["SVM", "KNN"]
CLAIM = {"kind": "performance", "metric": "roc_auc", "subject": "SVM", "other": "KNN"}
STATEMENT = "SVM has a higher ROC-AUC than KNN"


def spec_for(dataset):
    return validate_spec(
        {"statement": STATEMENT, "claim": CLAIM, "dataset": dataset, "params": {}},
        SPEC_KEYS,
    )


def test_the_prompt_forbids_generated_data_and_demands_the_block():
    assert PROMPT_VERSION == "experiment-v9"
    assert "make_classification" not in SYSTEM_PROMPT
    assert "load_breast_cancer" not in SYSTEM_PROMPT
    assert "Hugging Face" in SYSTEM_PROMPT
    assert "paste it unchanged" in SYSTEM_PROMPT
    assert "with_preprocessing" in SYSTEM_PROMPT


@pytest.mark.parametrize("dataset", list(DATASETS))
def test_the_task_of_a_spec_carries_the_block_of_its_dataset(dataset):
    task = _task("Compare SVM and KNN", "a:float, y:int", MODELS, spec_for(dataset))
    assert loader_code(dataset) in task
    for other in DATASETS:
        if other != dataset:
            assert DATASETS[other]["hf_id"] not in task


def test_a_task_without_a_spec_picks_the_block_from_the_prompt():
    task = _task("Compare SVM and KNN on tumour diagnosis", "a:float, y:int", MODELS)
    assert loader_code("breast_cancer") in task
    default = _task("Compare SVM and KNN", "a:float, y:int", MODELS)
    assert loader_code("customer_churn") in default


def test_the_planner_sees_the_real_datasets_and_may_choose_among_them():
    for key in DATASETS:
        assert key in planner.SYSTEM_PROMPT
    assert "choose the real dataset whose domain fits the query" in planner.SYSTEM_PROMPT
    assert "no baseline" not in planner.SYSTEM_PROMPT
    assert "default controls" in planner.SYSTEM_PROMPT


def test_the_planner_prompt_lists_every_dataset_with_its_summary(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            raise RuntimeError("stop")

    monkeypatch.setattr(planner, "OpenAI", Client)
    monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")
    with pytest.raises(RuntimeError, match="stop"):
        planner.run_planner_agent("Compare SVM and KNN", [], [], MODELS)
    user = captured["messages"][1]["content"]
    assert dataset_menu() in user


def test_a_dataset_outside_the_registry_is_rejected():
    with pytest.raises(Exception, match="dataset must be one of"):
        validate_spec({"statement": STATEMENT, "claim": CLAIM, "dataset": "imbalanced"}, SPEC_KEYS)


def test_the_report_brief_names_the_hub_source_of_the_dataset():
    state = {
        "query": "q",
        "hypotheses": ["h"],
        "experiment_specs": [spec_for("credit_fraud")],
        "selected_hypothesis": 0,
    }
    brief = _brief(state, [], "run")
    assert "Dataset source: Hugging Face dataset David-Egea/Creditcard-fraud-detection" in brief
    assert "Hugging Face" in REPORT_PROMPT
    assert "sentetik" in REPORT_PROMPT


def test_a_report_without_a_known_dataset_says_so():
    brief = _brief({"query": "q", "hypotheses": [], "experiment_specs": []}, [], "run")
    assert "Dataset source: not recorded" in brief


def test_the_leakage_judge_is_told_that_pipeline_preprocessing_is_fine():
    assert "Pipeline" in LEAKAGE_PROMPT
    assert "ColumnTransformer" in LEAKAGE_PROMPT


SYNTHETIC_SCRIPT = """
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
X, y = make_classification(n_samples=500, weights=[0.9, 0.1], random_state=1)
models = {"SVM": SVC(), "KNN": KNeighborsClassifier()}
a = train_test_split(X, y, random_state=42, stratify=y)
"""
REAL_SCRIPT = loader_code("customer_churn") + """
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
models = {"SVM": with_preprocessing(SVC()), "KNN": with_preprocessing(KNeighborsClassifier())}
a = train_test_split(X, y, random_state=42, stratify=y)
"""
OUTPUT = "\n".join(
    ["dataset=customer_churn samples=7043 features=19 negative_ratio=0.73 positive_ratio=0.27"]
    + [
        f"model={name} accuracy=0.9 f1=0.8 roc_auc=0.9 pr_auc=0.8 train_seconds=1.0 tn=50 fp=5 fn=5 tp=40"
        for name in ("SVM", "KNN")
    ]
)


@pytest.fixture
def loop(monkeypatch):
    class Recorder:
        corrections = []
        runs = []

    recorder = Recorder()
    recorder.corrections = []
    recorder.runs = []

    def correct(code, error, prompt, schema, models, spec=None):
        recorder.corrections.append(error)
        return REAL_SCRIPT

    def run(code, schema):
        recorder.runs.append(code)
        return OUTPUT

    monkeypatch.setattr(experiments, "generate_classification_code", lambda *args, **kwargs: SYNTHETIC_SCRIPT)
    monkeypatch.setattr(experiments, "correct_classification_code", correct)
    monkeypatch.setattr(experiments, "run_classification", run)
    return recorder


def test_a_script_with_generated_data_is_corrected_before_it_reaches_the_sandbox(loop):
    result = experiments.execute_experiment(
        "Compare SVM and KNN", "a:float, y:int", record_memory=False, track_run=False
    )
    assert len(loop.corrections) == 1
    assert "make_classification" in loop.corrections[0]
    assert "Hugging Face" in loop.corrections[0]
    assert loop.runs == [REAL_SCRIPT]
    assert result["status"] == "Finished"


def test_a_spec_run_is_also_stopped_on_generated_data(loop):
    result = experiments.execute_experiment(
        "Compare SVM and KNN",
        "a:float, y:int",
        record_memory=False,
        track_run=False,
        models=MODELS,
        spec=spec_for("customer_churn"),
    )
    assert "make_classification" in loop.corrections[0]
    assert result["status"] == "Finished"


def test_a_script_that_never_uses_real_data_fails_without_running(loop, monkeypatch):
    monkeypatch.setattr(
        experiments,
        "correct_classification_code",
        lambda code, error, *args, **kwargs: (loop.corrections.append(error), SYNTHETIC_SCRIPT)[1],
    )
    result = experiments.execute_experiment(
        "Compare SVM and KNN", "a:float, y:int", record_memory=False, track_run=False
    )
    assert result["status"] == "Failed"
    assert "make_classification" in result["error"]
    assert loop.runs == []
