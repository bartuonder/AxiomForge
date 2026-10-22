from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.agents.experiment as experiment_module
import app.experiments as experiments
import app.main as main
from app.agents.experiment import (
    MIN_MODELS,
    QueryNamesTooFewModels,
    require_models,
    requested_models,
)
from app.graph.workflow import new_thread_id

ONE = "Evaluate XGBoost on an imbalanced fraud dataset"
TWO = "Compare Random Forest and XGBoost on an imbalanced fraud dataset"
NONE = "How does churn behave?"


def test_two_models_are_the_minimum():
    assert MIN_MODELS == 2


@pytest.mark.parametrize("query", [NONE, ONE, "SVM, svm and Support Vector Machine"])
def test_fewer_than_two_distinct_models_are_refused(query):
    with pytest.raises(QueryNamesTooFewModels, match="fewer than two models"):
        require_models(requested_models(query))


@pytest.mark.parametrize(
    "query",
    [TWO, "Compare SVM, KNN and Random Forest", "RF vs XGB"],
)
def test_two_or_more_models_are_accepted(query):
    require_models(requested_models(query))


@pytest.mark.parametrize("query", [NONE, ONE])
def test_no_thread_is_created_for_fewer_than_two_models(query):
    with pytest.raises(QueryNamesTooFewModels):
        new_thread_id(query)


def test_a_thread_is_created_for_two_models():
    assert new_thread_id(TWO)


@pytest.fixture
def no_llm(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(1)
        raise AssertionError("the LLM must not be called")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=forbidden)))
    monkeypatch.setattr(experiment_module, "OpenAI", lambda api_key: client)
    monkeypatch.setattr(experiment_module, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(experiments, "generate_classification_code", forbidden)
    monkeypatch.setattr(experiments, "correct_classification_code", forbidden)
    return calls


def test_code_generation_refuses_a_single_model_without_calling_the_llm(no_llm):
    models = requested_models(ONE)
    with pytest.raises(QueryNamesTooFewModels):
        experiment_module.generate_classification_code("prompt", "a:float, b:int", models)
    with pytest.raises(QueryNamesTooFewModels):
        experiment_module.correct_classification_code("code", "error", "prompt", "a:float, b:int", models)
    assert no_llm == []


def test_an_experiment_refuses_a_single_model_before_any_work(no_llm):
    with pytest.raises(QueryNamesTooFewModels):
        experiments.execute_experiment(ONE, "a:float, b:int")
    with pytest.raises(QueryNamesTooFewModels):
        experiments.execute_experiment("prompt", "a:float, b:int", models=requested_models(ONE))
    assert no_llm == []


@pytest.fixture
def client(monkeypatch):
    queued = []
    monkeypatch.setattr(main, "_enqueue", lambda task, *args: queued.append((task.name, args)))
    test_client = TestClient(main.app)
    test_client.queued = queued
    return test_client


@pytest.mark.parametrize("query", [NONE, ONE])
def test_starting_research_with_fewer_than_two_models_answers_422(client, query):
    response = client.post("/start_research", json={"query": query})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "fewer than two models" in detail
    assert "at least two models" in detail
    assert "SVM and Random Forest" in detail
    assert client.queued == []


def test_starting_research_with_two_models_queues_the_run(client):
    response = client.post("/start_research", json={"query": TWO})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert client.queued[0][0] == "axiomforge.run_research"
    assert client.queued[0][1][1] == TWO


def test_the_standalone_experiment_endpoint_refuses_a_single_model_too(client, no_llm):
    response = client.post("/experiments", json={"prompt": ONE, "csv_schema": "a:float, b:int"})
    assert response.status_code == 422
    assert "at least two models" in response.json()["detail"]
    assert no_llm == []


def test_the_old_one_model_wording_is_gone():
    detail = main._too_few_models_detail(QueryNamesTooFewModels())
    assert "at least one model" not in detail
    assert not hasattr(main, "_no_model_detail")
    assert not hasattr(experiment_module, "QueryNamesNoModel")
