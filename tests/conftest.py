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
