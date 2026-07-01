"""LLM provider abstraction (Ollama / Groq / Mock)."""

from __future__ import annotations

from typing import Protocol

from app.core.config import settings
from app.services.groq import GroqService
from app.services.ollama import OllamaService


class LLMService(Protocol):
    provider_name: str
    model_name: str
    use_mock: bool

    async def generate_json(
        self,
        *,
        system_instruction: str,
        user_message: str,
    ) -> dict: ...


def get_llm_service(model_name: str | None = None) -> LLMService:
    """
    Returns an object with:
      - use_mock: bool
      - generate_json(system_instruction: str, user_message: str) -> dict
      - provider_name: str
    """
    provider = (settings.llm_provider or "ollama").strip().lower()
    if provider == "groq":
        return GroqService(model_name=model_name)
    if provider == "ollama":
        return OllamaService(model_name=model_name)
    if provider == "mock":
        s = OllamaService(model_name=settings.ollama_analyze_model)
        s.use_mock = True
        return s
    if provider == "ollama":
        return OllamaService(model_name=model_name)
    raise ValueError(f"Unsupported LLM provider: {provider}")

