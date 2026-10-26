import mlflow
import pytest
from mlflow.tracking import MlflowClient

import app.campaign.tracking as tracking


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mlflow_paper")
    patch = pytest.MonkeyPatch()
    patch.chdir(folder)
    uri = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"
    patch.setattr(tracking, "MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield uri
    patch.undo()


def new_run(store):
    mlflow.set_experiment("paper-tests")
    with mlflow.start_run() as run:
        return run.info.run_id


def test_the_paper_is_stored_with_its_status_and_rewrites(store):
    run_id = new_run(store)
    assert tracking.log_meta_paper(run_id, "# Paper\n\nText.\n", "Completed", 2) is True
    client = MlflowClient(store)
    assert "paper.md" in [item.path for item in client.list_artifacts(run_id)]
    run = client.get_run(run_id)
    assert run.data.tags["paper_status"] == "Completed" and run.data.metrics["paper_rewrites"] == 2.0


def test_the_stored_text_is_the_paper(store):
    run_id = new_run(store)
    tracking.log_meta_paper(run_id, "# Paper\n\nText.\n", "NeedsReview", 0)
    path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="paper.md", tracking_uri=store)
    assert open(path, encoding="utf-8").read() == "# Paper\n\nText.\n"
    assert MlflowClient(store).get_run(run_id).data.tags["paper_status"] == "NeedsReview"


def test_an_empty_run_id_is_skipped(store, monkeypatch):
    monkeypatch.setattr(tracking, "MlflowClient", lambda *args, **kwargs: pytest.fail("MLflow was used"))
    assert tracking.log_meta_paper("", "# Paper", "Completed", 0) is False


def test_an_empty_paper_is_skipped(store, monkeypatch):
    monkeypatch.setattr(tracking, "MlflowClient", lambda *args, **kwargs: pytest.fail("MLflow was used"))
    assert tracking.log_meta_paper("abc", "", "Completed", 0) is False


def test_an_unknown_run_does_not_raise(store):
    assert tracking.log_meta_paper("does-not-exist", "# Paper", "Completed", 0) is False


def test_an_unreachable_server_does_not_raise(monkeypatch):
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "2")
    monkeypatch.setattr(tracking, "MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    assert tracking.log_meta_paper("abc", "# Paper", "Completed", 0) is False
