import pytest

from app.core.config import settings
from app.services.llm import get_llm_service
from app.services.ollama import OllamaService, _parse_json


def test_parse_ollama_json_with_surrounding_text() -> None:
    assert _parse_json('Result:\n{"score": 80}\nDone') == {"score": 80}


def test_llm_factory_selects_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    service = get_llm_service(model_name="qwen3:8b")

    assert isinstance(service, OllamaService)
    assert service.model_name == "qwen3:8b"
    assert service.use_mock is True
