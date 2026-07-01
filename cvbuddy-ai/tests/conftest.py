import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _mock_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never call a real LLM provider."""
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setattr(settings, "mock_llm", True)
