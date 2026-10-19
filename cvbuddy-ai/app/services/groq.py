"""Groq LLM client (OpenAI-compatible) — JSON-only output convention."""

from __future__ import annotations

import json
import logging
import math
import re

import httpx

from app.core.config import settings
from app.services.errors import LLMQuotaError, LLMUpstreamError, MockProhibitedError

logger = logging.getLogger(__name__)


class GroqService:
    provider_name = "groq"

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.groq_model
        self.use_mock = settings.use_mock_llm
        self._api_key = settings.groq_api_key.strip()
        self._base_url = "https://api.groq.com/openai/v1"

    async def generate_json(self, *, system_instruction: str, user_message: str) -> dict:
        if self.use_mock:
            if settings.is_production:
                raise MockProhibitedError()
            raise RuntimeError("generate_json called while MOCK_LLM is enabled")

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model_name,
            "temperature": 0.25,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_message},
            ],
        }
        if self.model_name.startswith("qwen/"):
            payload["reasoning_format"] = "hidden"
            payload["reasoning_effort"] = "none"
            # Free-tier TPM limits include the requested completion budget.
            payload["max_completion_tokens"] = (
                3072 if self.model_name == settings.groq_extract_model else 2048
            )
        else:
            payload["max_completion_tokens"] = 3072
        payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMUpstreamError(
                status_code=None,
                message="Provider request timed out",
                code="provider_timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMUpstreamError(status_code=None, message="Provider network request failed") from exc

        if r.status_code == 429:
            # Groq rate limit / quota. We map to quota error used by API handlers.
            retry_after = None
            if "retry-after" in r.headers:
                try:
                    parsed_retry_after = float(r.headers["retry-after"])
                    if math.isfinite(parsed_retry_after) and parsed_retry_after >= 0:
                        retry_after = min(math.ceil(parsed_retry_after), 3600)
                except (ValueError, OverflowError):
                    retry_after = None
            raise LLMQuotaError(message="Provider rate limited request", retry_after_seconds=retry_after)

        if r.status_code >= 400:
            error_code = "provider_timeout" if r.status_code in {408, 504} else "provider_unavailable"
            logger.warning(
                "Provider returned an error status",
                extra={"event": "provider_http_error", "model": self.model_name, "upstream_status": r.status_code},
            )
            raise LLMUpstreamError(
                status_code=r.status_code,
                message="Provider returned an error status",
                code=error_code,
            )

        try:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMUpstreamError(
                status_code=502,
                message="Provider response did not match the expected format",
                code="malformed_provider_response",
            ) from exc
        if not isinstance(content, str):
            raise LLMUpstreamError(
                status_code=502,
                message="Provider response content was not text",
                code="malformed_provider_response",
            )
        try:
            parsed = _parse_json_loose(content)
        except json.JSONDecodeError as exc:
            raise LLMUpstreamError(
                status_code=502,
                message="Provider response was not valid JSON",
                code="malformed_provider_response",
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMUpstreamError(
                status_code=502,
                message="Provider response JSON was not an object",
                code="malformed_provider_response",
            )
        return parsed


def _parse_json_loose(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed_objects: list[dict] = []
        for match in re.finditer(r"\{", text):
            try:
                candidate, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                parsed_objects.append(candidate)
        if parsed_objects:
            return parsed_objects[-1]
        raise

