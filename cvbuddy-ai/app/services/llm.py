"""LLM provider abstraction (Groq / Mock)."""

from __future__ import annotations

from typing import Protocol

from app.core.config import settings
from app.services.groq import GroqService


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


class MockLLMService:
    provider_name = "mock"
    model_name = "mock"
    use_mock = True

    async def generate_json(
        self,
        *,
        system_instruction: str,
        user_message: str,
    ) -> dict:
        raise RuntimeError("generate_json called while MOCK_LLM is enabled")


def get_llm_service(model_name: str | None = None) -> LLMService:
    """
    Returns an object with:
      - use_mock: bool
      - generate_json(system_instruction: str, user_message: str) -> dict
      - provider_name: str
    """
    provider = (settings.llm_provider or "groq").strip().lower()
    if provider == "groq":
        return GroqService(model_name=model_name)
    if provider == "mock":
        return MockLLMService()
    raise ValueError(f"Unsupported LLM provider: {provider}")

