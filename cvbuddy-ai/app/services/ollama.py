"""Local Ollama client using the native JSON chat API."""

from __future__ import annotations

import json
import logging
import re

import httpx

from app.core.config import settings
from app.services.errors import LLMUpstreamError

logger = logging.getLogger(__name__)


class OllamaService:
    provider_name = "ollama"

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.ollama_analyze_model
        self.use_mock = settings.use_mock_llm
        self._base_url = settings.ollama_base_url.rstrip("/")

    async def generate_json(self, *, system_instruction: str, user_message: str) -> dict:
        if self.use_mock:
            raise RuntimeError("generate_json called while MOCK_LLM is enabled")
        is_extraction = "parse extracted cv text" in system_instruction.casefold()
        payload = {
            "model": self.model_name,
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": "0s" if is_extraction else "10m",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_message},
            ],
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
                "num_predict": 4096 if is_extraction else 1536,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LLMUpstreamError(
                status_code=503,
                message=f"Ollama is unavailable at {self._base_url}: {exc}",
            ) from exc

        if response.status_code >= 400:
            raise LLMUpstreamError(
                status_code=response.status_code,
                message=response.text,
            )

        content = (response.json().get("message") or {}).get("content", "")
        try:
            return _parse_json(content)
        except json.JSONDecodeError as exc:
            logger.error("Ollama returned invalid JSON: %s", content[:500])
            raise LLMUpstreamError(
                status_code=502,
                message=f"Ollama model {self.model_name} returned invalid JSON",
            ) from exc


def _parse_json(value: str) -> dict:
    text = (value or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed: list[dict] = []
        for match in re.finditer(r"\{", text):
            try:
                candidate, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                parsed.append(candidate)
        if parsed:
            return parsed[-1]
        raise
