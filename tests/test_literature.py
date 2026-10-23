import json
from types import SimpleNamespace

import pytest

import app.agents.literature as literature
from app.agents.spec import MODEL_PARAMS

THREE_MODELS = (
    "Compare Random Forest, Logistic Regression and KNN on credit card client default prediction. "
    "Use n_neighbors=5 for the KNN and n_estimators=100 for the Random Forest as the tuned settings."
)


def test_every_supported_model_has_a_search_name():
    assert set(literature.MODEL_SEARCH_NAMES) == set(MODEL_PARAMS)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["customer churn", "churn prediction"], ["customer churn", "churn prediction"]),
        (["n_neighbors=5", "customer churn"], ["customer churn"]),
        (["random forest", "credit default"], ["credit default"]),
        (["credit default 2020"], []),
        (["tuned settings", "hyperparameter tuning"], []),
        (["n_estimators", "kernel", "alpha"], []),
        (["one two three four"], []),
        (["Machine Learning", "classification", "prediction"], []),
        (["  Credit   Card  Default "], ["credit card default"]),
        (["customer churn", "customer churn"], ["customer churn"]),
        (["credit risk", "loan default", "fraud detection"], ["credit risk", "loan default"]),
        (["c value", "credit risk"], ["credit risk"]),
        ([5, None, ["x"]], []),
        ("customer churn", []),
        (None, []),
    ],
)
def test_topics_keep_only_the_domain(raw, expected):
    assert literature.clean_topics(raw) == expected


def test_the_plan_starts_with_the_topic_and_one_model_and_never_uses_more_than_two_phrases():
    plan = literature.search_plan(["RandomForest", "LogisticRegression", "KNN"], ["credit card default"])
    assert plan[0] == ["credit card default", "random forest"]
    assert plan[1] == ["credit card default", "logistic regression"]
    assert ["credit card default", "machine learning"] in plan
    assert ["random forest", "logistic regression"] in plan
    assert plan[-1] == ["credit card default"]
    assert all(1 <= len(item) <= 2 for item in plan)
    assert len(plan) <= literature.MAX_SEARCHES


def test_the_plan_falls_back_to_the_models_without_a_topic():
    plan = literature.search_plan(["RandomForest", "KNN"], [])
    assert plan == [["random forest", "k nearest neighbors"]]


def test_two_models_with_one_search_name_are_not_repeated():
    plan = literature.search_plan(["GradientBoosting", "HistGradientBoosting"], ["churn"])
    assert plan[0] == ["churn", "gradient boosting"]
    assert plan.count(["churn", "gradient boosting"]) == 1
    assert all(len(set(item)) == len(item) for item in plan)


def test_a_plan_without_anything_is_empty():
    assert literature.search_plan([], []) == []


def test_the_topics_only_plan_works_without_models():
    plan = literature.search_plan([], ["customer churn"])
    assert plan == [["customer churn", "machine learning"], ["customer churn"]]


def paper(number):
    return {"title": f"Paper {number}", "abstract": f"Abstract {number}"}


class Harness:
    def __init__(self, monkeypatch, topics, results, scores=None):
        self.searches = []
        self.sleeps = []
        self.embedding_inputs = None
        self.topics_payload = topics
        self.results = list(results)
        self.scores = scores

        harness = self

        class Completions:
            def create(self, **kwargs):
                harness.llm_messages = kwargs["messages"]
                content = harness.topics_payload if isinstance(harness.topics_payload, str) else json.dumps(harness.topics_payload)
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        class Embeddings:
            def create(self, model, input):
                harness.embedding_inputs = input
                size = len(input)
                scores = harness.scores or [0.9] * (size - 1)
                vectors = [[1.0, 0.0]] + [[score, (1 - score**2) ** 0.5] for score in scores]
                return SimpleNamespace(data=[SimpleNamespace(embedding=vector) for vector in vectors])

        fake = SimpleNamespace(chat=SimpleNamespace(completions=Completions()), embeddings=Embeddings())
        monkeypatch.setattr(literature, "OpenAI", lambda api_key: fake)
        monkeypatch.setattr(literature, "OPENAI_API_KEY", "key")
        monkeypatch.setattr(literature.time, "sleep", self.sleeps.append)

        def search(phrases, limit):
            harness.searches.append(list(phrases))
            return harness.results.pop(0) if harness.results else []

        monkeypatch.setattr(literature, "search_arxiv_phrases", search)


def test_the_three_failing_shapes_no_longer_put_parameters_into_a_search(monkeypatch):
    harness = Harness(
        monkeypatch,
        {"topics": ["n_neighbors=5", "credit card default", "n_estimators=100"]},
        [[paper(1), paper(2)]] * 5,
    )
    literature.run_literature_agent(THREE_MODELS)
    flat = [phrase for search in harness.searches for phrase in search]
    assert not any("=" in phrase or "_" in phrase or any(c.isdigit() for c in phrase) for phrase in flat)
    assert all(len(search) <= 2 for search in harness.searches)
    assert harness.searches[0] == ["credit card default", "random forest"]


def test_the_question_sent_to_the_model_is_the_original_one(monkeypatch):
    harness = Harness(monkeypatch, {"topics": ["credit card default"]}, [[paper(1)]] * 5)
    literature.run_literature_agent(THREE_MODELS)
    assert harness.llm_messages[1]["content"] == THREE_MODELS
    assert "Never include model or algorithm names" in harness.llm_messages[0]["content"]


def test_relevance_is_still_measured_against_the_original_question(monkeypatch):
    harness = Harness(monkeypatch, {"topics": ["credit card default"]}, [[paper(1)]] * 5)
    literature.run_literature_agent(THREE_MODELS)
    assert harness.embedding_inputs[0] == THREE_MODELS


def test_the_ladder_stops_once_there_are_enough_candidates(monkeypatch):
    first = [paper(number) for number in range(8)]
    second = [paper(number) for number in range(8, 16)]
    harness = Harness(monkeypatch, {"topics": ["credit card default"]}, [first, second, [paper(99)], [paper(100)]])
    literature.run_literature_agent(THREE_MODELS)
    assert len(harness.searches) == 2
    assert len(harness.sleeps) == 1


def test_an_empty_first_search_falls_through_to_the_next(monkeypatch):
    harness = Harness(monkeypatch, {"topics": ["credit card default"]}, [[], [], [paper(1)]])
    result = literature.run_literature_agent(THREE_MODELS)
    assert len(harness.searches) == literature.MAX_SEARCHES
    assert result == ["Paper 1: Abstract 1"]


def test_a_ladder_that_finds_nothing_ends_in_the_old_error(monkeypatch):
    harness = Harness(monkeypatch, {"topics": ["credit card default"]}, [])
    with pytest.raises(RuntimeError, match="arxiv returned no papers"):
        literature.run_literature_agent(THREE_MODELS)
    assert len(harness.searches) == literature.MAX_SEARCHES


def test_papers_below_the_relevance_threshold_are_still_rejected(monkeypatch):
    Harness(monkeypatch, {"topics": ["credit card default"]}, [[paper(1), paper(2)]] * 5, scores=[0.1, 0.2])
    with pytest.raises(RuntimeError, match="arxiv returned no relevant papers"):
        literature.run_literature_agent(THREE_MODELS)


def test_only_the_best_three_relevant_papers_are_kept(monkeypatch):
    Harness(
        monkeypatch,
        {"topics": ["credit card default"]},
        [[paper(number) for number in range(5)]] * 5,
        scores=[0.4, 0.9, 0.5, 0.8, 0.7],
    )
    result = literature.run_literature_agent(THREE_MODELS)
    assert [item.split(":")[0] for item in result] == ["Paper 1", "Paper 3", "Paper 4"]


def test_an_answer_without_any_usable_topic_still_searches_the_models(monkeypatch):
    harness = Harness(monkeypatch, {"topics": ["n_neighbors=5"]}, [[paper(1)]] * 5)
    literature.run_literature_agent(THREE_MODELS)
    assert harness.searches == [["random forest", "logistic regression"]]


def test_invalid_json_from_the_topic_step_is_reported(monkeypatch):
    Harness(monkeypatch, "not json", [])
    with pytest.raises(RuntimeError, match="literature agent returned invalid JSON"):
        literature.run_literature_agent(THREE_MODELS)


def test_a_missing_key_stops_before_any_call(monkeypatch):
    monkeypatch.setattr(literature, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is missing"):
        literature.run_literature_agent(THREE_MODELS)


def test_the_searches_are_spaced_for_arxiv(monkeypatch):
    harness = Harness(monkeypatch, {"topics": ["credit card default"]}, [])
    with pytest.raises(RuntimeError):
        literature.run_literature_agent(THREE_MODELS)
    assert harness.sleeps == [literature.ARXIV_DELAY_SECONDS] * (literature.MAX_SEARCHES - 1)


def test_a_long_plan_is_cut_at_the_search_limit():
    plan = literature.search_plan(["RandomForest", "KNN"], ["credit risk", "loan default"])
    assert len(plan) == literature.MAX_SEARCHES
    assert ["loan default"] not in plan


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["credit card default prediction"], ["credit card default"]),
        (["telecom customer churn analysis"], ["telecom customer churn"]),
        (["credit card fraud detection"], ["credit card fraud"]),
        (["very long four word topic"], []),
        (["census income prediction"], ["census income prediction"]),
        (["a b c d prediction extra"], []),
    ],
)
def test_a_four_word_topic_loses_a_generic_last_word_instead_of_being_dropped(raw, expected):
    assert literature.clean_topics(raw) == expected
