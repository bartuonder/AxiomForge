from types import SimpleNamespace

import pytest

import app.sandbox.e2b_runner as runner


class FakeSandbox:
    created = []
    runs = []

    def __init__(self, error=None, stdout=None):
        self.error = error
        self.stdout = stdout or ["line one", "line two"]
        self.killed = False
        self.written = {}
        self.files = SimpleNamespace(write=self.written.__setitem__)

    def run_code(self, code, timeout):
        FakeSandbox.runs.append(timeout)
        return SimpleNamespace(error=self.error, logs=SimpleNamespace(stdout=self.stdout))

    def kill(self):
        self.killed = True


@pytest.fixture
def sandbox(monkeypatch):
    FakeSandbox.created = []
    FakeSandbox.runs = []
    instances = []

    def create(api_key, timeout):
        FakeSandbox.created.append(timeout)
        instance = FakeSandbox(error=getattr(create, "error", None))
        instances.append(instance)
        return instance

    monkeypatch.setattr(runner, "E2B_API_KEY", "key")
    monkeypatch.setattr(runner, "Sandbox", SimpleNamespace(create=create))
    return SimpleNamespace(create=create, instances=instances)


def test_the_run_gets_enough_time_for_ten_splits_and_the_box_outlives_it(sandbox):
    runner.run_classification("print(1)", "age:float, churn:int")
    assert FakeSandbox.runs == [runner.RUN_TIMEOUT_SECONDS]
    assert FakeSandbox.created == [runner.SANDBOX_LIFETIME_SECONDS]
    assert runner.RUN_TIMEOUT_SECONDS >= 240
    assert runner.SANDBOX_LIFETIME_SECONDS > runner.RUN_TIMEOUT_SECONDS


def test_the_output_lines_are_joined(sandbox):
    assert runner.run_classification("print(1)", "age:float, churn:int") == "line one\nline two"


def test_the_data_file_is_uploaded_and_the_box_is_killed(sandbox):
    runner.run_classification("print(1)", "age:float, churn:int")
    instance = sandbox.instances[0]
    assert runner.DATA_PATH in instance.written
    assert instance.written[runner.DATA_PATH].splitlines()[0] == "age,churn"
    assert instance.killed is True


def test_a_code_error_is_raised_and_the_box_is_still_killed(sandbox):
    sandbox.create.error = SimpleNamespace(name="ValueError", value="bad", traceback="trace")
    with pytest.raises(runner.SandboxCodeError, match="ValueError: bad"):
        runner.run_classification("print(1)", "age:float, churn:int")
    assert sandbox.instances[0].killed is True


def test_a_missing_key_stops_before_any_box_is_created(monkeypatch):
    monkeypatch.setattr(runner, "E2B_API_KEY", "")
    with pytest.raises(RuntimeError, match="E2B_API_KEY is missing"):
        runner.run_classification("print(1)", "age:float, churn:int")


def test_the_csv_header_follows_the_schema():
    text = runner.build_csv("age:float, monthly_spend:float, tenure_months:int, churn:int")
    lines = text.splitlines()
    assert lines[0] == "age,monthly_spend,tenure_months,churn"
    assert len(lines) > 1


def test_a_column_without_a_type_is_a_float():
    assert runner.build_csv("a, b").splitlines()[0] == "a,b"


def test_a_schema_needs_features_and_a_target():
    with pytest.raises(ValueError, match="features and a target"):
        runner.build_csv("only")
