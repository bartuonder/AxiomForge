import pytest

from app.agents.experiment import PROMPT_VERSION, SYSTEM_PROMPT, split_contract_error
from app.seeds import SPLIT_SEEDS

STRATIFIED = """
from sklearn.model_selection import train_test_split
for seed in [42, 100]:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)
"""


def test_a_stratified_split_passes():
    assert split_contract_error(STRATIFIED) == ""


def test_the_split_may_be_called_through_its_module():
    code = "a = sklearn.model_selection.train_test_split(X, y, stratify=y, random_state=1)\n"
    assert split_contract_error(code) == ""


def test_an_unstratified_split_is_rejected():
    code = STRATIFIED.replace(", stratify=y", "")
    assert "stratify=y" in split_contract_error(code)


def test_stratify_none_does_not_count():
    code = STRATIFIED.replace("stratify=y", "stratify=None")
    assert "stratify=y" in split_contract_error(code)


def test_every_split_call_must_be_stratified():
    code = STRATIFIED + "\nextra = train_test_split(X, y, random_state=3)\n"
    assert "stratify=y" in split_contract_error(code)


def test_a_script_without_train_test_split_is_rejected():
    code = "from sklearn.model_selection import KFold\nfolds = KFold(5)\n"
    assert "train_test_split" in split_contract_error(code)


def test_a_syntax_error_is_left_to_the_sandbox():
    assert split_contract_error("x = (") == ""


def test_ten_seeds_are_the_agreed_repeats():
    assert len(SPLIT_SEEDS) == 10
    assert len(set(SPLIT_SEEDS)) == 10
    assert list(SPLIT_SEEDS) == sorted(SPLIT_SEEDS)


def test_the_prompt_lists_every_seed_in_order_and_the_row_count():
    listing = ", ".join(str(seed) for seed in SPLIT_SEEDS)
    assert listing in SYSTEM_PROMPT
    assert "exactly 10 times" in SYSTEM_PROMPT
    assert "Beşli" not in SYSTEM_PROMPT
    assert "exactly five" not in SYSTEM_PROMPT


def test_the_prompt_demands_stratification():
    assert "stratify=y" in SYSTEM_PROMPT


def test_the_prompt_version_names_the_new_protocol():
    assert PROMPT_VERSION == "experiment-v8"


@pytest.mark.parametrize("seed", SPLIT_SEEDS)
def test_every_agreed_seed_is_a_plain_int(seed):
    assert isinstance(seed, int)


MODELS_HEADER = """
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
X, y = make_classification(n_samples=500, weights=[0.9, 0.1], class_sep=0.5, random_state=1)
models = {"SVM": SVC(), "KNN": KNeighborsClassifier()}
"""
UNSTRATIFIED_SCRIPT = MODELS_HEADER + "a = train_test_split(X, y, random_state=42)\n"
STRATIFIED_SCRIPT = MODELS_HEADER + "a = train_test_split(X, y, random_state=42, stratify=y)\n"

SANDBOX_OUTPUT = "\n".join(
    ["dataset=d samples=500 features=20 negative_ratio=0.9 positive_ratio=0.1"]
    + [
        f"model={name} accuracy=0.9 f1=0.8 roc_auc=0.9 pr_auc=0.8 train_seconds=1.0 tn=50 fp=5 fn=5 tp=40"
        for name in ("SVM", "KNN")
    ]
)


@pytest.fixture
def experiment(monkeypatch):
    import app.experiments as experiments

    class Recorder:
        corrections = []
        runs = []

    recorder = Recorder()
    recorder.corrections = []
    recorder.runs = []

    def correct(code, error, prompt, schema, models, spec=None):
        recorder.corrections.append(error)
        return STRATIFIED_SCRIPT

    def run(code, schema):
        recorder.runs.append(code)
        return SANDBOX_OUTPUT

    monkeypatch.setattr(experiments, "generate_classification_code", lambda *args, **kwargs: UNSTRATIFIED_SCRIPT)
    monkeypatch.setattr(experiments, "correct_classification_code", correct)
    monkeypatch.setattr(experiments, "run_classification", run)
    recorder.run_experiment = lambda: experiments.execute_experiment(
        "Compare SVM and KNN", "age:float, churn:int", record_memory=False, track_run=False
    )
    return recorder


def test_an_unstratified_script_is_corrected_before_it_reaches_the_sandbox(experiment):
    result = experiment.run_experiment()
    assert len(experiment.corrections) == 1
    assert "stratify=y" in experiment.corrections[0]
    assert experiment.runs == [STRATIFIED_SCRIPT]
    assert result["status"] == "Finished"


def test_a_script_that_never_gets_stratified_fails_without_running(experiment, monkeypatch):
    import app.experiments as experiments

    monkeypatch.setattr(
        experiments,
        "correct_classification_code",
        lambda code, error, *args, **kwargs: (experiment.corrections.append(error), UNSTRATIFIED_SCRIPT)[1],
    )
    result = experiment.run_experiment()
    assert result["status"] == "Failed"
    assert "stratify=y" in result["error"]
    assert experiment.runs == []
    assert len(experiment.corrections) == experiments.MAX_RETRIES - 1
