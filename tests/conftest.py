import pytest

import app.sandbox.e2b_runner as e2b_runner


@pytest.fixture(autouse=True)
def no_real_sandbox(monkeypatch):
    monkeypatch.setattr(e2b_runner, "E2B_API_KEY", "")
