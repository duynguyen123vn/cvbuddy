from __future__ import annotations

import re

from app.pipeline.preprocess import (
    DocumentExtractResult,
    DocumentTextBlock,
    _SECTION_PATTERNS,
    mask_pii,
)
from app.schemas.cv import (
    CvSections,
    CvSourceBlock,
    CvStructuredDocument,
    CvStructuredRecord,
    ExtractionCoverage,
)

_DATE_PREFIX = re.compile(
    r"^(?P<date>(?:\d{1,2}/)?\d{4}\s*(?:-|–|—|to)\s*(?:present|hiện tại|(?:\d{1,2}/)?\d{4}))\s*\|\s*",
    re.I,
)
_LINK = re.compile(r"(?:https?://|www\.|linkedin\.com|github\.com)\S+", re.I)
_LANGUAGE = re.compile(
    r"\b(english|vietnamese|japanese|korean|chinese|french|ielts|toeic|toefl|cefr|"
    r"tiếng anh|tiếng việt|tiếng nhật|tiếng hàn|tiếng trung|tiếng pháp)\b",
    re.I,
)


def build_structured_document(
    sections: CvSections,
    document: DocumentExtractResult,
) -> tuple[CvStructuredDocument, ExtractionCoverage]:
    blocks = [_to_source_block(block) for block in document.blocks]
    output_items = [
        item
        for values in sections.model_dump().values()
        for item in values
    ]
    output_blob = _normalize_for_match(" ".join(output_items))

    classified_ids: list[str] = []
    ignored_ids: list[str] = []
    unclassified: list[CvSourceBlock] = []
    for block in blocks:
        meaningful_lines = [
            line.strip()
            for line in block.text.splitlines()
            if line.strip() and not _is_heading(line.strip())
        ]
        if not meaningful_lines:
            ignored_ids.append(block.block_id)
            continue
        line_matches = [
            _normalize_for_match(line) in output_blob
            for line in meaningful_lines
            if _normalize_for_match(line)
        ]
        if line_matches and any(line_matches):
            classified_ids.append(block.block_id)
        else:
            unclassified.append(block)

    structured = CvStructuredDocument(
        personal_info=_personal_info(sections.other),
        summary=sections.summary,
        experience=[_record(item, blocks) for item in sections.experience],
        projects=[_record(item, blocks) for item in sections.projects],
        education=[_record(item, blocks) for item in sections.education],
        skills={"general": sections.skills},
        certifications=[_record(item, blocks) for item in sections.certifications],
        languages=[item for item in sections.skills if _LANGUAGE.search(item)],
        links=_links(output_items),
        other=sections.other,
        unclassified=unclassified,
        raw_blocks=blocks,
    )

    source_count = len(blocks)
    retained_count = len(classified_ids) + len(unclassified) + len(ignored_ids)
    classifiable_count = max(source_count - len(ignored_ids), 0)
    coverage = ExtractionCoverage(
        source_block_count=source_count,
        classified_block_count=len(classified_ids),
        unclassified_block_count=len(unclassified),
        ignored_heading_count=len(ignored_ids),
        retained_block_count=retained_count,
        coverage_score=round(retained_count / source_count, 4) if source_count else 0.0,
        classification_rate=(
            round(len(classified_ids) / classifiable_count, 4)
            if classifiable_count
            else 0.0
        ),
        unclassified_block_ids=[block.block_id for block in unclassified],
    )
    return structured, coverage


def _to_source_block(block: DocumentTextBlock) -> CvSourceBlock:
    return CvSourceBlock(
        block_id=block.block_id,
        text=mask_pii(block.text),
        page=block.page,
        column=block.column,
        bbox=block.bbox,
        source_type=block.source_type,
    )


def _record(raw_text: str, blocks: list[CvSourceBlock]) -> CvStructuredRecord:
    remaining = raw_text.strip()
    date: str | None = None
    match = _DATE_PREFIX.match(remaining)
    if match:
        date = match.group("date").strip()
        remaining = remaining[match.end() :].strip()

    parts = [part.strip() for part in remaining.split(" | ") if part.strip()]
    title = parts[0] if parts else remaining or None
    details = parts[1:] if len(parts) > 1 else []
    source_ids = [
        block.block_id
        for block in blocks
        if _texts_overlap(block.text, raw_text)
    ]
    return CvStructuredRecord(
        raw_text=raw_text,
        date=date,
        title=title,
        details=details,
        source_block_ids=source_ids,
    )


def _personal_info(items: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"contact": [], "links": [], "other": []}
    for item in items:
        if "[EMAIL]" in item or "[PHONE]" in item:
            result["contact"].append(item)
        elif _LINK.search(item):
            result["links"].append(item)
        else:
            result["other"].append(item)
    return {key: values for key, values in result.items() if values}


def _links(items: list[str]) -> list[str]:
    links: list[str] = []
    for item in items:
        links.extend(match.group(0).rstrip(".,)") for match in _LINK.finditer(item))
    return list(dict.fromkeys(links))


def _is_heading(line: str) -> bool:
    return any(pattern.match(line) for _, pattern in _SECTION_PATTERNS)


def _normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _texts_overlap(left: str, right: str) -> bool:
    left_normalized = _normalize_for_match(left)
    right_normalized = _normalize_for_match(right)
    if not left_normalized or not right_normalized:
        return False
    return left_normalized in right_normalized or right_normalized in left_normalized
