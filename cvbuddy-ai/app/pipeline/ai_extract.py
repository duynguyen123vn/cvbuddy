"""AI-assisted CV section parsing from already-extracted text."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.pipeline.preprocess import _SECTION_PATTERNS, split_into_sections
from app.schemas.cv import CvSections
from app.services.errors import LLMQuotaError, LLMUpstreamError
from app.services.llm import get_llm_service

logger = logging.getLogger(__name__)

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


def _read_extract_prompt() -> str:
    path = PROMPTS_ROOT / "base" / "extract_sections.md"
    return path.read_text(encoding="utf-8").strip()


async def run_ai_extract_sections(
    normalized_text: str,
    *,
    target_language: str = "auto",
    llm_model: str | None = None,
) -> CvSections:
    """Parse extracted text into CvSections with the configured LLM provider."""
    selected_model = llm_model
    if selected_model is None:
        if settings.llm_provider == "ollama":
            selected_model = settings.ollama_extract_model
        elif settings.llm_provider == "groq":
            selected_model = settings.groq_extract_model
    service = get_llm_service(model_name=selected_model)
    if service.use_mock:
        return split_into_sections(normalized_text)

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
            "Primary Groq extraction model failed; retrying with %s",
            settings.groq_fallback_model,
        )
        service = get_llm_service(model_name=settings.groq_fallback_model)
        raw = await service.generate_json(
            system_instruction=system_instruction,
            user_message=user_message,
        )

    try:
        return _remove_section_heading_items(CvSections.model_validate(raw))
    except ValidationError:
        logger.warning("Invalid AI extract sections JSON: %s", raw)
        raise


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
