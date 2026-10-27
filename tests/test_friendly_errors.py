import httpx
import pytest
from openai import APIConnectionError, AuthenticationError, RateLimitError

from app.agents.campaign_planner import CampaignUnsupported
from app.agents.experiment import QueryNamesTooFewModels
from app.friendly_errors import CODES, classify, describe, explain_error, tag_error
from app.sandbox.e2b_runner import SandboxCodeError


def response(status):
    return httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


def quota():
    return RateLimitError("You exceeded your current quota", response=response(429), body={"code": "insufficient_quota"})


class TestClassify:
    def test_a_refusal_of_the_planner(self):
        assert classify(CampaignUnsupported("no claims")) == "planner_refused"

    def test_a_query_with_too_few_models(self):
        assert classify(QueryNamesTooFewModels()) == "too_few_models"

    def test_an_exhausted_quota(self):
        assert classify(quota()) == "openai_quota"

    def test_a_rate_limit_that_is_not_the_quota(self):
        assert classify(RateLimitError("Rate limit reached", response=response(429), body={"code": "rate_limit_exceeded"})) == "openai_busy"

    def test_a_rejected_key(self):
        assert classify(AuthenticationError("Incorrect API key", response=response(401), body=None)) == "openai_key"

    def test_a_network_problem(self):
        assert classify(APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))) == "openai_network"

    def test_a_sandbox_failure(self):
        assert classify(SandboxCodeError("NameError")) == "sandbox_error"

    @pytest.mark.parametrize(
        ("message", "code"),
        [
            ("OPENAI_API_KEY is missing", "openai_missing_key"),
            ("E2B_API_KEY is missing", "e2b_missing_key"),
            ("arxiv paper not found: 9999.99999", "arxiv_not_found"),
            ("arxiv request failed: timeout", "arxiv_unavailable"),
            ("arxiv returned no relevant papers", "no_sources"),
            ("campaign planner returned no valid campaign: candidate 1: x", "planner_invalid"),
            ("campaign planner returned invalid JSON", "ai_format"),
            ("meta reporter returned invalid JSON", "ai_format"),
            ("the research has reported no progress for 45 minutes; its worker may have stopped", "stale_worker"),
            ("the campaign has reported no progress for 21 minutes; its worker may have stopped", "stale_worker"),
            ("the OpenAI quota is exhausted; add credit before starting a research", "openai_quota"),
            ("the OpenAI key was rejected; check OPENAI_API_KEY", "openai_key"),
            ("campaign failed: RuntimeError: sandbox died", "campaign_failed"),
            ("the campaign report is missing", "report_missing"),
        ],
    )
    def test_a_known_message_is_recognised_by_its_text(self, message, code):
        assert classify(RuntimeError(message)) == code

    def test_an_unknown_error_has_no_class(self):
        assert classify(ValueError("something odd")) is None


class TestTag:
    def test_a_known_error_gets_a_code_prefix(self):
        assert tag_error(CampaignUnsupported("no claims")) == "[planner_refused] no claims"

    def test_an_unknown_error_keeps_its_text(self):
        assert tag_error(ValueError("something odd")) == "something odd"

    def test_an_error_without_text_keeps_its_class_name(self):
        assert tag_error(ValueError()) == "ValueError"

    def test_the_message_is_cut(self):
        assert len(tag_error(ValueError("x" * 5000))) == 2000

    def test_a_tag_is_not_added_twice(self):
        assert tag_error(RuntimeError("[planner_refused] already tagged")) == "[planner_refused] already tagged"


class TestExplain:
    def test_a_tagged_message_is_explained_in_turkish(self):
        info = explain_error("[planner_refused] The user query does not state any claim.", "tr")
        assert info["code"] == "planner_refused"
        assert info["title"] == "Sorunuzdan test edilebilir bir iddia çıkarılamadı"
        assert "iki model" in info["hint"]
        assert info["technical"] == "The user query does not state any claim."

    def test_the_english_text(self):
        info = explain_error("[planner_refused] reason", "en")
        assert info["title"] == "No testable claim could be taken from your question"

    def test_an_untagged_known_message_is_recognised(self):
        info = explain_error("OPENAI_API_KEY is missing", "tr")
        assert info["code"] == "openai_missing_key" and info["technical"] == "OPENAI_API_KEY is missing"

    def test_an_exhausted_quota_tells_what_to_do(self):
        info = explain_error("[openai_quota] Error code: 429 - insufficient_quota", "tr")
        assert info["title"] == "OpenAI kredisi bitmiş" and "kredi" in info["hint"]

    def test_an_unknown_message_gets_the_generic_explanation(self):
        info = explain_error("Traceback: boom", "tr")
        assert info["code"] == "unknown" and info["title"] == "Beklenmeyen bir hata oluştu" and info["technical"] == "Traceback: boom"

    def test_no_message_no_explanation(self):
        assert explain_error("", "tr") is None and explain_error(None, "tr") is None

    def test_an_unknown_language_falls_back_to_turkish(self):
        assert explain_error("[stale_worker] x", "de")["title"] == explain_error("[stale_worker] x", "tr")["title"]

    @pytest.mark.parametrize("language", ["tr", "en"])
    def test_every_code_has_a_title_a_message_and_a_hint(self, language):
        for code in CODES:
            info = explain_error(f"[{code}] detail", language)
            assert info["code"] == code
            assert info["title"].strip() and info["message"].strip() and info["hint"].strip()

    def test_the_codes_are_the_ones_the_classifier_can_return(self):
        assert {"planner_refused", "too_few_models", "openai_quota", "openai_busy", "openai_key", "openai_network", "sandbox_error", "openai_missing_key", "e2b_missing_key", "arxiv_not_found", "arxiv_unavailable", "no_sources", "planner_invalid", "ai_format", "stale_worker", "campaign_cancelled", "campaign_failed", "report_missing", "unknown"} == set(CODES)

    def test_describe_is_the_tagged_text_of_an_exception(self):
        assert describe(CampaignUnsupported("r")) == "[planner_refused] r"


class TestWiring:
    def test_the_recorded_text_of_an_exception_is_tagged(self):
        from app.graph.errors import describe_error

        assert describe_error(CampaignUnsupported("no claims")) == "[planner_refused] no claims"
        assert describe_error(ValueError("odd")) == "odd"

    def test_the_research_status_explains_a_recorded_error(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.main as main

        monkeypatch.setattr(main, "get_research", lambda thread_id: {"thread_id": thread_id, "status": "failed", "error": "[planner_refused] The query states no claim."})
        body = TestClient(main.app).get("/research/t-1").json()
        assert body["error"] == "[planner_refused] The query states no claim."
        assert body["error_info"]["title"] == "Sorunuzdan test edilebilir bir iddia çıkarılamadı" and body["error_info"]["technical"] == "The query states no claim."

    def test_the_language_of_the_explanation_can_be_chosen(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.main as main

        monkeypatch.setattr(main, "get_research", lambda thread_id: {"status": "failed", "error": "[openai_quota] x"})
        body = TestClient(main.app).get("/research/t-1", params={"lang": "en"}).json()
        assert body["error_info"]["title"] == "The OpenAI credit has run out"

    def test_a_run_without_an_error_has_no_explanation(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.main as main

        monkeypatch.setattr(main, "get_research", lambda thread_id: {"status": "running", "error": ""})
        assert TestClient(main.app).get("/research/t-1").json()["error_info"] is None

    def test_an_unknown_language_is_a_422(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.main as main

        monkeypatch.setattr(main, "get_research", lambda thread_id: {"status": "running", "error": ""})
        response = TestClient(main.app).get("/research/t-1", params={"lang": "de"})
        assert response.status_code == 422 and "language" in response.json()["detail"]

    def test_the_campaign_summary_explains_a_failed_campaign(self):
        from app.campaign.summary import build_summary

        failed = {"id": "x", "title": "T", "status": "failed", "error": "RuntimeError: E2B_API_KEY is missing", "datasets": {}}
        info = build_summary(failed, None, None, None, "tr")["error_info"]
        assert info["code"] == "e2b_missing_key" and info["technical"] == "RuntimeError: E2B_API_KEY is missing"

    def test_the_campaign_summary_has_no_explanation_without_an_error(self):
        from app.campaign.summary import build_summary

        assert build_summary({"id": "x", "title": "T", "status": "running", "datasets": {}}, None, None, None, "tr")["error_info"] is None


class TestMoreRules:
    @pytest.mark.parametrize(
        ("message", "code"),
        [
            ("Error code: 401 - invalid_api_key", "openai_key"),
            ("arxiv query is empty", "no_sources"),
            ("no arxiv identifier was given", "no_sources"),
            ("campaign planner did not return candidates", "planner_invalid"),
            ("campaign support judge returned an unusable answer", "ai_format"),
            ("meta reporter returned an empty introduction", "ai_format"),
            ("meta reporter did not return an object", "ai_format"),
        ],
    )
    def test_every_alternative_of_a_rule_is_recognised(self, message, code):
        assert classify(RuntimeError(message)) == code

    @pytest.mark.parametrize("message", ["the job reported no progress yet", "the campaign failed earlier", "the report is missing a table"])
    def test_a_loose_message_is_not_taken_for_a_known_error(self, message):
        assert classify(RuntimeError(message)) is None

    def test_a_forbidden_key_is_a_key_problem(self):
        from openai import PermissionDeniedError

        assert classify(PermissionDeniedError("no access", response=response(403), body=None)) == "openai_key"

    def test_an_already_tagged_exception_is_not_tagged_again(self):
        assert tag_error(CampaignUnsupported("[planner_refused] again")) == "[planner_refused] again"

    def test_a_tag_with_an_unknown_code_is_not_trusted(self):
        info = explain_error("[mystery] something", "tr")
        assert info["code"] == "unknown" and info["technical"] == "[mystery] something"

    def test_the_campaign_summary_explains_in_english_on_request(self):
        from app.campaign.summary import build_summary

        failed = {"id": "x", "title": "T", "status": "failed", "error": "E2B_API_KEY is missing", "datasets": {}}
        assert build_summary(failed, None, None, None, "en")["error_info"]["title"] == "The experiment environment key is not set"
