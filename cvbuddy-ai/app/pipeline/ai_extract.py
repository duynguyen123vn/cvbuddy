"""AI-assisted CV section parsing from already-extracted text."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.pipeline.preprocess import _SECTION_PATTERNS, split_into_sections
from app.schemas.cv import CvSections
from app.services.errors import LLMQuotaError, LLMUpstreamError
from app.services.llm import ensure_mock_allowed, get_llm_service

logger = logging.getLogger(__name__)

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class AiExtractResult:
    sections: CvSections
    provider: str
    model_name: str


def _read_extract_prompt() -> str:
    path = PROMPTS_ROOT / "base" / "extract_sections.md"
    return path.read_text(encoding="utf-8").strip()


async def run_ai_extract_sections(
    normalized_text: str,
    *,
    target_language: str = "auto",
    llm_model: str | None = None,
) -> AiExtractResult:
    """Parse extracted text into CvSections with Groq Qwen."""
    selected_model = llm_model or settings.groq_extract_model
    service = get_llm_service(model_name=selected_model)
    ensure_mock_allowed(service)
    if service.use_mock:
        return AiExtractResult(split_into_sections(normalized_text), "mock", "mock")

    system_instruction = _read_extract_prompt()
    user_message = json.dumps(
        {
            "task": "parse_cv_sections",
            "target_language": target_language,
            "schema": {
                "summary": [],
                "experience": [],
                "education": [],
                "skills": [],
                "projects": [],
                "certifications": [],
                "other": [],
            },
            "extracted_text": normalized_text,
        },
        ensure_ascii=False,
    )
    try:
        raw = await service.generate_json(
            system_instruction=system_instruction,
            user_message=user_message,
        )
    except (LLMQuotaError, LLMUpstreamError):
        if settings.llm_provider != "groq" or selected_model == settings.groq_fallback_model:
            raise
        logger.warning(
            "Primary Groq extraction model failed; retrying with configured fallback",
            extra={"event": "provider_fallback", "model": settings.groq_fallback_model},
        )
        service = get_llm_service(model_name=settings.groq_fallback_model)
        raw = await service.generate_json(
            system_instruction=system_instruction,
            user_message=user_message,
        )

    try:
        return AiExtractResult(
            _remove_section_heading_items(CvSections.model_validate(raw)),
            service.provider_name,
            service.model_name,
        )
    except ValidationError:
        logger.warning(
            "Provider output did not match extraction schema",
            extra={"event": "unsupported_schema"},
        )
        raise LLMUpstreamError(
            status_code=502,
            message="Provider output did not match the extraction schema",
            code="unsupported_schema",
        ) from None


def _remove_section_heading_items(sections: CvSections) -> CvSections:
    cleaned: dict[str, list[str]] = {}
    for field, items in sections.model_dump().items():
        cleaned[field] = [
            item
            for item in items
            if not any(pattern.match(item.strip()) for _, pattern in _SECTION_PATTERNS)
            and not item.strip().startswith(("[Page ", "[Column "))
        ]
    return CvSections(**cleaned)
