"""Hybrid CV extraction orchestration."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from enum import StrEnum

from app.pipeline.ai_extract import AiExtractResult, run_ai_extract_sections
from app.pipeline.preprocess import (
    compute_local_metrics,
    DocumentExtractResult,
    extract_document_text,
    mask_pii,
    split_into_sections,
)
from app.pipeline.structured_extract import build_structured_document
from app.core.config import settings
from app.schemas.cv import (
    CvSections,
    CvStructuredDocument,
    ExtractionCoverage,
    LocalMetrics,
)

logger = logging.getLogger(__name__)

_EN_HEADING = re.compile(
    r"^(summary|objective|education|experience|work experience|skills|technical skills|"
    r"projects|certifications|certificates)\s*:?\s*$",
    re.I,
)
_VI_HEADING = re.compile(
    r"^(mục tiêu|mục tiêu nghề nghiệp|học vấn|kinh nghiệm|kỹ năng|kĩ năng|"
    r"dự án|đồ án|chứng chỉ|giải thưởng)\s*:?\s*$",
    re.I,
)
_VI_CHARS = "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
_VI_PAGE_WORDS = {
    "và", "với", "của", "cho", "mục", "tiêu", "học", "vấn", "kinh", "nghiệm",
    "kỹ", "năng", "dự", "án", "phát", "triển", "xây", "dựng", "nghiên", "cứu",
}
_EN_PAGE_WORDS = {
    "and", "with", "for", "objective", "education", "experience", "skills",
    "projects", "developed", "built", "research", "student", "university",
}


class ExtractMode(StrEnum):
    LOCAL = "local"
    AI = "ai"
    HYBRID = "hybrid"


class TargetLanguage(StrEnum):
    AUTO = "auto"
    EN = "en"
    VI = "vi"
    BOTH = "both"


@dataclass(frozen=True)
class ParseQuality:
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class ExtractResult:
    sections: CvSections
    metrics: LocalMetrics
    document: DocumentExtractResult
    normalized_text: str
    parser_source: str
    quality: ParseQuality
    fallback_reason: str
    target_language: TargetLanguage
    structured_document: CvStructuredDocument
    coverage: ExtractionCoverage
    provider: str = "local"
    model_name: str = "local"


def assess_parse_quality(sections: CvSections, normalized_text: str) -> ParseQuality:
    useful_fields = ("summary", "experience", "education", "skills", "projects", "certifications")
    useful_sections = sum(1 for name in useful_fields if getattr(sections, name))
    total_items = sum(len(getattr(sections, name)) for name in (*useful_fields, "other"))
    other_chars = sum(len(item) for item in sections.other)
    total_chars = max(len(normalized_text), 1)
    other_ratio = other_chars / total_chars

    score = 1.0
    reasons: list[str] = []

    if useful_sections < 3:
        score -= 0.35
        reasons.append("Local parser found fewer than 3 useful sections.")

    if other_ratio > 0.45:
        score -= 0.35
        reasons.append("Local parser placed too much text in other.")

    if total_items < 3 and len(normalized_text) > 800:
        score -= 0.25
        reasons.append("Document is long but local parser found few items.")

    if not sections.experience and not sections.projects and len(normalized_text) > 500:
        score -= 0.20
        reasons.append("Local parser found no experience or projects.")

    page_count = len(re.findall(r"^\[Page \d+\]$", normalized_text, flags=re.M))
    if page_count > 1 and useful_sections < 4:
        score -= 0.15
        reasons.append("Multi-page document has too few recognized sections.")

    return ParseQuality(score=round(max(score, 0.0), 2), reasons=reasons)


def _normalize_item(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).strip()


def _item_is_present(item: str, output_items: list[str]) -> bool:
    normalized = _normalize_item(item)
    if not normalized:
        return True
    for output_item in output_items:
        candidate = _normalize_item(output_item)
        if not candidate:
            continue
        if normalized in candidate or candidate in normalized:
            return True
        if min(len(normalized), len(candidate)) >= 24:
            if SequenceMatcher(None, normalized, candidate).ratio() >= 0.88:
                return True
    return False


def _looks_bilingual(normalized_text: str) -> bool:
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    english_headings = sum(1 for line in lines if _EN_HEADING.match(line))
    vietnamese_headings = sum(1 for line in lines if _VI_HEADING.match(line))
    return english_headings >= 2 and vietnamese_headings >= 2


def select_pdf_language_pages(
    normalized_text: str,
    target_language: TargetLanguage,
) -> tuple[str, set[int] | None]:
    """Select one language version when a bilingual PDF stores versions on separate pages."""
    if target_language not in {TargetLanguage.VI, TargetLanguage.EN}:
        return normalized_text, None

    matches = list(re.finditer(r"^\[Page (\d+)\]\s*$", normalized_text, flags=re.M))
    if len(matches) < 2:
        return normalized_text, None

    pages: list[tuple[int, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized_text)
        page_number = int(match.group(1))
        page_text = normalized_text[match.end() : end].strip()
        lowered = page_text.casefold()
        tokens = set(re.findall(r"[a-zA-ZÀ-ỹ]+", lowered))
        vi_score = sum(lowered.count(char) for char in _VI_CHARS) + 3 * len(tokens & _VI_PAGE_WORDS)
        en_score = 3 * len(tokens & _EN_PAGE_WORDS)
        language = "vi" if vi_score >= max(4, en_score) else "en"
        pages.append((page_number, page_text, language))

    languages = {language for _, _, language in pages}
    if languages != {"vi", "en"}:
        return normalized_text, None

    wanted = target_language.value
    selected = [(number, text) for number, text, language in pages if language == wanted]
    if not selected:
        return normalized_text, None

    selected_text = "\n".join(f"[Page {number}]\n{text}" for number, text in selected)
    return selected_text.strip(), {number for number, _ in selected}


def reconcile_ai_sections(
    ai_sections: CvSections,
    local_sections: CvSections,
    normalized_text: str,
    target_language: TargetLanguage,
) -> tuple[CvSections, int]:
    """Restore source items omitted by AI without re-merging bilingual CV versions."""
    if target_language in {TargetLanguage.EN, TargetLanguage.VI}:
        return ai_sections, 0
    if target_language == TargetLanguage.AUTO and _looks_bilingual(normalized_text):
        return ai_sections, 0

    reconciled = ai_sections.model_dump()
    output_items = [
        item
        for values in reconciled.values()
        for item in values
    ]
    restored = 0
    for field, local_items in local_sections.model_dump().items():
        for item in local_items:
            if _item_is_present(item, output_items):
                continue
            reconciled[field].append(item)
            output_items.append(item)
            restored += 1
    return CvSections.model_validate(reconciled), restored


async def extract_cv_sections(
    filename: str,
    data: bytes,
    *,
    mode: ExtractMode = ExtractMode.HYBRID,
    target_language: TargetLanguage = TargetLanguage.AUTO,
    llm_model: str | None = None,
    mask: bool = True,
) -> ExtractResult:
    document = extract_document_text(filename, data)
    normalized_text = document.normalized_text
    if not normalized_text.strip():
        if document.needs_ocr:
            raise ValueError("No extractable text in document; this PDF appears to require OCR")
        raise ValueError("No extractable text in document (scanned PDF may need OCR)")

    if mask:
        normalized_text = mask_pii(normalized_text)

    normalized_text, selected_pages = select_pdf_language_pages(
        normalized_text,
        target_language,
    )
    if selected_pages is not None:
        selected_blocks = [
            block for block in document.blocks if block.page in selected_pages
        ]
        document = replace(
            document,
            normalized_text=normalized_text,
            text_block_count=len(selected_blocks),
            blocks=selected_blocks,
            warnings=[
                *document.warnings,
                f"Selected {target_language.value} CV pages: {sorted(selected_pages)}.",
            ],
        )

    local_sections = split_into_sections(normalized_text)
    quality = assess_parse_quality(local_sections, normalized_text)

    sections = local_sections
    parser_source = "local"
    parser_provider = "local"
    model_name = "local"
    fallback_reason = "; ".join(quality.reasons)

    should_use_ai = mode == ExtractMode.AI or (
        mode == ExtractMode.HYBRID
        and (quality.score < 0.70 or document.max_columns > 1)
    )
    if mode == ExtractMode.HYBRID and document.max_columns > 1:
        layout_reason = "Multi-column document uses AI parsing."
        fallback_reason = "; ".join(filter(None, (fallback_reason, layout_reason)))
    if should_use_ai:
        try:
            ai_result = await run_ai_extract_sections(
                normalized_text,
                target_language=target_language.value,
                llm_model=llm_model,
            )
            if isinstance(ai_result, AiExtractResult):
                ai_sections = ai_result.sections
                parser_provider = ai_result.provider
                model_name = ai_result.model_name
            else:
                ai_sections = ai_result
                parser_provider = "groq"
                model_name = llm_model or settings.groq_extract_model
            sections, restored_count = reconcile_ai_sections(
                ai_sections,
                local_sections,
                normalized_text,
                target_language,
            )
            parser_source = "ai"
            if restored_count:
                fallback_reason = "; ".join(
                    filter(
                        None,
                        (
                            fallback_reason,
                            f"Restored {restored_count} source items omitted by AI.",
                        ),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            if settings.is_production and mode == ExtractMode.AI:
                raise
            logger.warning(
                "AI extraction failed; using local parser",
                extra={"event": "local_extraction_fallback", "exception_type": type(exc).__name__},
            )
            parser_source = "local_fallback"
            parser_provider = "local"
            model_name = "local"
            sections = local_sections
            fallback_reason = "AI extraction failed; local parser output returned."

    structured_document, coverage = build_structured_document(sections, document)

    return ExtractResult(
        sections=sections,
        metrics=compute_local_metrics(sections),
        document=document,
        normalized_text=normalized_text,
        parser_source=parser_source,
        quality=quality,
        fallback_reason=fallback_reason,
        target_language=target_language,
        structured_document=structured_document,
        coverage=coverage,
        provider=parser_provider,
        model_name=model_name,
    )
