import pytest

import app.memory.rag_memory as rag_memory
import app.sandbox.e2b_runner as e2b_runner


@pytest.fixture(autouse=True)
def no_real_sandbox(monkeypatch):
    monkeypatch.setattr(e2b_runner, "E2B_API_KEY", "")


@pytest.fixture(autouse=True)
def no_real_memory(monkeypatch):
    def refuse():
        raise RuntimeError("the vector memory is not available in tests")

    monkeypatch.setattr(rag_memory, "_store", refuse)


@pytest.fixture(autouse=True)
def no_real_judge(monkeypatch):
    import app.agents.campaign_planner as campaign_planner

    def refuse(user):
        raise RuntimeError("the support judge is not available in tests")

    monkeypatch.setattr(campaign_planner, "_judge_complete", refuse)


@pytest.fixture
def approve_judge(monkeypatch):
    import json

    import app.agents.campaign_planner as campaign_planner

    def approve(user):
        claims = json.loads(user)["claims"]
        return json.dumps({"verdicts": [{"id": item["id"], "supports": True, "reason": "stub"} for item in claims]})

    monkeypatch.setattr(campaign_planner, "_judge_complete", approve)
