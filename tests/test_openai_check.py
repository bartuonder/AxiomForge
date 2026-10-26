import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError, AuthenticationError, RateLimitError

import app.main as main
import app.openai_check as check
from app.openai_check import OpenAIUnavailable, check_openai_access


def response(status):
    return httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


def quota_error():
    return RateLimitError("You exceeded your current quota", response=response(429), body={"code": "insufficient_quota", "type": "insufficient_quota"})


class Client:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return object()


def test_a_working_key_passes_with_one_tiny_call():
    client = Client()
    check_openai_access(client)
    assert len(client.calls) == 1 and client.calls[0]["max_tokens"] == 1 and client.calls[0]["model"] == check.CHECK_MODEL


def test_an_exhausted_quota_is_reported():
    with pytest.raises(OpenAIUnavailable, match="quota is exhausted"):
        check_openai_access(Client(quota_error()))


def test_a_plain_rate_limit_does_not_block():
    error = RateLimitError("Rate limit reached for requests", response=response(429), body={"code": "rate_limit_exceeded"})
    check_openai_access(Client(error))


def test_a_rejected_key_is_reported():
    error = AuthenticationError("Incorrect API key", response=response(401), body=None)
    with pytest.raises(OpenAIUnavailable, match="key was rejected"):
        check_openai_access(Client(error))


def test_a_network_problem_does_not_block():
    check_openai_access(Client(APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))))


def test_an_unexpected_error_does_not_block():
    check_openai_access(Client(ValueError("surprise")))


def test_without_a_key_and_a_client_nothing_is_called(monkeypatch):
    monkeypatch.setattr(check, "OPENAI_API_KEY", "")
    monkeypatch.setattr(check, "OpenAI", lambda **kwargs: pytest.fail("a client was built"))
    check_openai_access()


def test_the_real_client_is_built_with_a_short_timeout_and_no_retries(monkeypatch):
    seen = {}

    class Built(Client):
        def __init__(self, **kwargs):
            seen.update(kwargs)
            super().__init__()

    monkeypatch.setattr(check, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(check, "OpenAI", Built)
    check_openai_access()
    assert seen == {"api_key": "key", "timeout": check.CHECK_TIMEOUT_SECONDS, "max_retries": 0}


class TestEndpoint:
    @pytest.fixture
    def client(self, monkeypatch):
        self.queued = []
        monkeypatch.setattr(main, "_enqueue", lambda task, *args: self.queued.append(args))
        return TestClient(main.app)

    def test_an_exhausted_quota_stops_the_start_before_anything_is_queued(self, client, monkeypatch):
        def refuse():
            raise OpenAIUnavailable("the OpenAI quota is exhausted; add credit before starting a research")

        monkeypatch.setattr(main, "check_openai_access", refuse)
        result = client.post("/start_research", json={"query": "Compare RandomForest and SVM on churn data", "mode": "experiment"})
        assert result.status_code == 503 and "quota is exhausted" in result.json()["detail"] and self.queued == []

    def test_a_working_key_lets_the_research_start(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "check_openai_access", lambda: calls.append(1))
        result = client.post("/start_research", json={"query": "Compare RandomForest and SVM on churn data", "mode": "experiment"})
        assert result.status_code == 200 and calls == [1] and len(self.queued) == 1

    def test_a_query_with_too_few_models_is_refused_before_the_check(self, client, monkeypatch):
        monkeypatch.setattr(main, "check_openai_access", lambda: pytest.fail("checked too early"))
        result = client.post("/start_research", json={"query": "Study churn data", "mode": "experiment"})
        assert result.status_code == 422


def test_a_forbidden_key_is_reported():
    from openai import PermissionDeniedError

    error = PermissionDeniedError("Project does not have access to this model", response=response(403), body=None)
    with pytest.raises(OpenAIUnavailable, match="key was rejected"):
        check_openai_access(Client(error))


def test_the_check_is_cheap_and_quick():
    assert check.CHECK_MODEL == "gpt-4o" and check.CHECK_TIMEOUT_SECONDS == 10.0
