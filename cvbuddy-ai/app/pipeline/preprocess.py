"""Local-only document processing; files are never sent to the LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from app.schemas.cv import CvSections, LocalMetrics


@dataclass(frozen=True)
class DocumentTextBlock:
    block_id: str
    text: str
    page: int
    column: int = 1
    bbox: tuple[float, float, float, float] | None = None
    source_type: str = "text"


@dataclass(frozen=True)
class DocumentExtractResult:
    normalized_text: str
    engine: str
    page_count: int = 0
    text_block_count: int = 0
    image_count: int = 0
    max_columns: int = 1
    needs_ocr: bool = False
    warnings: list[str] = field(default_factory=list)
    blocks: list[DocumentTextBlock] = field(default_factory=list)


_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "summary",
        re.compile(
            r"^(profile|personal profile|profile summary|about me|summary|professional summary|"
            r"career objective|career objectives|career goal|career goals|objective|objectives|"
            r"gioi thieu|muc tieu|giới thiệu|mục tiêu|mục tiêu nghề nghiệp)\s*:?\s*$",
            re.I,
        ),
    ),
    (
        "experience",
        re.compile(
            r"^(experience|work experience|professional experience|employment history|"
            r"work history|professional background|career history|internship|internships|"
            r"activities|extracurricular activities|volunteer experience|volunteering|"
            r"leadership experience|research experience|"
            r"kinh nghiem|kinh nghiệm|hoạt động|hoat dong|thực tập|thuc tap|"
            r"kinh nghiệm làm việc|công tác xã hội|nghiên cứu)\s*:?\s*$",
            re.I,
        ),
    ),
    (
        "education",
        re.compile(
            r"^(education|educational background|academic background|academic qualifications|"
            r"qualifications|hoc van|học vấn|trình độ học vấn)\s*:?\s*$",
            re.I,
        ),
    ),
    (
        "skills",
        re.compile(
            r"^(skills|technical skills|soft skills|core skills|competencies|technical competencies|"
            r"technologies|technology stack|tech stack|tools|tools and technologies|"
            r"ky nang|kỹ năng|kĩ năng|kỹ năng khác|công nghệ|công cụ)\s*:?\s*$",
            re.I,
        ),
    ),
    (
        "projects",
        re.compile(
            r"^(project|projects|personal project|personal projects|academic project|academic projects|"
            r"selected project|selected projects|featured project|featured projects|relevant project|"
            r"relevant projects|portfolio project|portfolio projects|course project|course projects|"
            r"capstone project|final project|school project|school projects|selected work|"
            r"research project|research projects|du an|do an|dự án|đồ án|công trình nghiên cứu)\s*:?\s*$",
            re.I,
        ),
    ),
    (
        "certifications",
        re.compile(
            r"^(certifications|certificates|certificate information|courses|relevant coursework|"
            r"training|licenses|honors|awards|achievements|"
            r"chung chi|chứng chỉ|thông tin chứng chỉ|khóa học|đào tạo|giấy phép|"
            r"giải thưởng|giai thuong|thành tích)\s*:?\s*$",
            re.I,
        ),
    ),
]

_LAYOUT_MARKER = re.compile(r"^\[(?:Page|Column)\s+\d+\]$", re.I)

_HEADING_ALIASES: tuple[tuple[str, str], ...] = (
    ("Personal Profile", "Profile"),
    ("Profile Summary", "Summary"),
    ("About Me", "Summary"),
    ("Career Goals", "Career Goals"),
    ("Career Goal", "Career Goal"),
    ("Mục tiêu nghề nghiệp", "Mục tiêu nghề nghiệp"),
    ("Career Objective", "Career Objective"),
    ("Professional Summary", "Summary"),
    ("Summary", "Summary"),
    ("Objective", "Objective"),
    ("Học vấn", "Học vấn"),
    ("Education", "Education"),
    ("Educational Background", "Education"),
    ("Academic Background", "Education"),
    ("Academic Qualifications", "Education"),
    ("Qualifications", "Education"),
    ("Kinh nghiệm", "Kinh nghiệm"),
    ("Experience", "Experience"),
    ("Work Experience", "Work Experience"),
    ("Professional Experience", "Professional Experience"),
    ("Professional Background", "Professional Experience"),
    ("Employment History", "Employment History"),
    ("Work History", "Work Experience"),
    ("Career History", "Work Experience"),
    ("Volunteer Experience", "Experience"),
    ("Leadership Experience", "Experience"),
    ("Research Experience", "Experience"),
    ("Internship", "Internship"),
    ("Internships", "Internships"),
    ("Hoạt động", "Hoạt động"),
    ("Activities", "Activities"),
    ("Extracurricular Activities", "Extracurricular Activities"),
    ("Kỹ năng khác", "Kỹ năng khác"),
    ("Kỹ năng", "Kỹ năng"),
    ("Kĩ năng", "Kĩ năng"),
    ("Technical Skills", "Technical Skills"),
    ("Soft Skills", "Soft Skills"),
    ("Core Skills", "Core Skills"),
    ("Technical Competencies", "Technical Skills"),
    ("Competencies", "Skills"),
    ("Tools and Technologies", "Technical Skills"),
    ("Technology Stack", "Technical Skills"),
    ("Tech Stack", "Technical Skills"),
    ("Technologies", "Technical Skills"),
    ("Skills", "Skills"),
    ("Dự án", "Dự án"),
    ("Đồ án", "Đồ án"),
    ("Do an", "Do an"),
    ("Featured Projects", "Featured Projects"),
    ("Featured Project", "Featured Project"),
    ("Relevant Projects", "Relevant Projects"),
    ("Relevant Project", "Relevant Project"),
    ("Portfolio Projects", "Portfolio Projects"),
    ("Portfolio Project", "Portfolio Project"),
    ("Course Projects", "Course Projects"),
    ("Course Project", "Course Project"),
    ("Capstone Project", "Capstone Project"),
    ("Final Project", "Final Project"),
    ("School Projects", "School Projects"),
    ("School Project", "School Project"),
    ("Projects", "Projects"),
    ("Project", "Project"),
    ("Personal Projects", "Personal Projects"),
    ("Personal Project", "Personal Project"),
    ("Academic Projects", "Academic Projects"),
    ("Academic Project", "Academic Project"),
    ("Selected Projects", "Selected Projects"),
    ("Selected Project", "Selected Project"),
    ("Selected Work", "Selected Projects"),
    ("Research Projects", "Research Projects"),
    ("Research Project", "Research Project"),
    ("Thông tin chứng chỉ", "Thông tin chứng chỉ"),
    ("Chứng chỉ", "Chứng chỉ"),
    ("Certificates", "Certificates"),
    ("Certifications", "Certifications"),
    ("Awards", "Awards"),
    ("Achievements", "Achievements"),
    ("Relevant Coursework", "Certifications"),
    ("Courses", "Certifications"),
    ("Training", "Certifications"),
    ("Licenses", "Certifications"),
    ("Honors", "Certifications"),
    ("Giải thưởng", "Giải thưởng"),
    ("Thành tích", "Thành tích"),
)

_QUANT_PATTERN = re.compile(
    r"(\d+%|\d+\s*%|\$\d+|\d+\s*(users|clients|students|events|k|m|bn)|"
    r"tăng|giảm|increase|decrease|improved|reduced|roi|kpi)",
    re.I,
)


def repair_pdf_text(raw: str) -> str:
    """Repair common UTF-8 text that PDF extractors expose as cp1252/latin1."""
    mojibake_markers = ("Ã", "áº", "á»", "Ä", "Â", "â€")
    if not any(marker in raw for marker in mojibake_markers):
        return raw

    try:
        repaired = raw.encode("cp1252", errors="ignore").decode("utf-8", errors="ignore")
    except UnicodeError:
        return raw

    raw_markers = sum(raw.count(marker) for marker in mojibake_markers)
    repaired_markers = sum(repaired.count(marker) for marker in mojibake_markers)
    return repaired if repaired and repaired_markers < raw_markers else raw


def normalize_text(raw: str) -> str:
    text = repair_pdf_text(raw)
    text = text.replace("\x00", "fi")
    text = re.sub(r"[\uf000-\uf8ff]", " ", text)
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def mask_pii(text: str) -> str:
    """Optional redaction before any external LLM call."""
    text = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "[EMAIL]", text)
    text = re.sub(r"\b(0|\+84)\d{8,10}\b", "[PHONE]", text)
    return text


def split_into_sections(text: str) -> CvSections:
    lines = normalize_section_lines([ln.strip() for ln in text.split("\n")])
    current = "other"
    buckets: dict[str, list[str]] = {
        k: []
        for k in [
            "summary",
            "experience",
            "education",
            "skills",
            "projects",
            "certifications",
            "other",
        ]
    }

    for line in lines:
        if not line or _LAYOUT_MARKER.match(line):
            continue
        matched = False
        for name, pattern in _SECTION_PATTERNS:
            if pattern.match(line):
                current = name
                matched = True
                break
        if not matched:
            buckets[current].append(_clean_content_line(line))

    return CvSections(**buckets)


def normalize_section_lines(lines: list[str]) -> list[str]:
    """Split headings that PDF/DOCX extractors glue to neighboring text."""
    expanded: list[str] = []
    for line in lines:
        if not line:
            expanded.append(line)
            continue
        expanded.extend(_split_line_around_heading(line))
    return expanded


def _split_line_around_heading(line: str) -> list[str]:
    stripped = line.strip()
    for heading, canonical in sorted(_HEADING_ALIASES, key=lambda item: len(item[0]), reverse=True):
        heading_pattern = re.escape(heading)

        if re.fullmatch(rf"{heading_pattern}\s*:?", stripped, flags=re.I):
            return [canonical]

        start_match = re.match(rf"^({heading_pattern})\s*:?\s+(.+)$", stripped, flags=re.I)
        if start_match:
            return [canonical, start_match.group(2).strip()]

        # A sentence commonly ends with "project"; treating that word as an
        # inline heading truncates bullets such as "Built an AI project".
        if heading.casefold() == "project":
            continue

        end_match = re.match(rf"^(.+?)\s+({heading_pattern})\s*:?\s*$", stripped, flags=re.I)
        if end_match:
            return [end_match.group(1).strip(), canonical]

        middle_match = re.match(rf"^(.+?)\s+({heading_pattern})\s*:?\s+(.+)$", stripped, flags=re.I)
        if middle_match:
            return [middle_match.group(1).strip(), canonical, middle_match.group(3).strip()]

    return [stripped]


def _clean_content_line(line: str) -> str:
    line = re.sub(r"^[•·▪▫◦\-\u2013\u2014]\s*", "", line.strip())
    return line.strip()


def compute_local_metrics(sections: CvSections) -> LocalMetrics:
    all_bullets: list[str] = []
    for field in ("experience", "projects", "other"):
        all_bullets.extend(getattr(sections, field))

    quantified = sum(1 for b in all_bullets if _QUANT_PATTERN.search(b))
    lengths = [len(b) for b in all_bullets if b]
    filled_sections = sum(
        1
        for name in ("summary", "experience", "education", "skills", "projects", "certifications")
        if getattr(sections, name)
    )

    return LocalMetrics(
        bullet_count=len(all_bullets),
        quantified_bullet_count=quantified,
        has_quantified_bullets=quantified > 0,
        avg_bullet_length=(sum(lengths) / len(lengths)) if lengths else 0.0,
        section_count=filled_sections,
        detected_languages=[],
    )


def extract_text_from_pdf(data: bytes) -> str:
    return extract_pdf_document(data).normalized_text


def extract_pdf_document(data: bytes) -> DocumentExtractResult:
    try:
        return _extract_pdf_with_pymupdf(data)
    except Exception as exc:  # noqa: BLE001
        fallback = _extract_pdf_with_pdfplumber(data)
        return DocumentExtractResult(
            normalized_text=fallback.normalized_text,
            engine="pdfplumber_fallback",
            page_count=fallback.page_count,
            text_block_count=fallback.text_block_count,
            image_count=fallback.image_count,
            max_columns=fallback.max_columns,
            needs_ocr=fallback.needs_ocr,
            warnings=[f"PyMuPDF extraction failed: {exc}", *fallback.warnings],
            blocks=fallback.blocks,
        )


def _extract_pdf_with_pymupdf(data: bytes) -> DocumentExtractResult:
    import fitz

    parts: list[str] = []
    text_block_count = 0
    image_count = 0
    max_columns = 1
    source_blocks: list[DocumentTextBlock] = []

    with fitz.open(stream=data, filetype="pdf") as doc:
        page_count = doc.page_count
        for page_index, page in enumerate(doc, start=1):
            image_count += len(page.get_images(full=True))
            blocks = page.get_text("blocks", sort=False) or []
            text_blocks: list[tuple[float, float, float, float, str]] = []
            for block in blocks:
                if len(block) < 5:
                    continue
                text = str(block[4]).strip()
                if text:
                    text_blocks.append((block[0], block[1], block[2], block[3], text))

            text_block_count += len(text_blocks)
            if text_blocks:
                parts.append(f"[Page {page_index}]")
                column_groups, column_count = _group_pdf_blocks_by_column(
                    text_blocks,
                    float(page.rect.width),
                )
                max_columns = max(max_columns, column_count)
                for column_index, column_blocks in enumerate(column_groups, start=1):
                    if column_count > 1:
                        parts.append(f"[Column {column_index}]")
                    for x0, y0, x1, y1, text in column_blocks:
                        cleaned_text = normalize_text(text)
                        parts.append(cleaned_text)
                        source_blocks.append(
                            DocumentTextBlock(
                                block_id=f"p{page_index}-b{len(source_blocks) + 1}",
                                text=cleaned_text,
                                page=page_index,
                                column=column_index,
                                bbox=(float(x0), float(y0), float(x1), float(y1)),
                            )
                        )

    normalized_text = normalize_text("\n".join(parts))
    warnings: list[str] = []
    needs_ocr = _needs_ocr(normalized_text, text_block_count, image_count)
    if needs_ocr:
        warnings.append("This PDF appears scanned or image-heavy; OCR is required for reliable extraction.")

    return DocumentExtractResult(
        normalized_text=normalized_text,
        engine="pymupdf",
        page_count=page_count,
        text_block_count=text_block_count,
        image_count=image_count,
        max_columns=max_columns,
        needs_ocr=needs_ocr,
        warnings=warnings,
        blocks=source_blocks,
    )


def _extract_pdf_with_pdfplumber(data: bytes) -> DocumentExtractResult:
    import pdfplumber

    parts: list[str] = []
    image_count = 0
    page_count = 0
    source_blocks: list[DocumentTextBlock] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        page_count = len(pdf.pages)
        for page_index, page in enumerate(pdf.pages, start=1):
            image_count += len(getattr(page, "images", []) or [])
            candidates: list[str] = []
            layout_text = page.extract_text(layout=True, x_tolerance=1, y_tolerance=3)
            default_text = page.extract_text(x_tolerance=1, y_tolerance=3)
            for text in (layout_text, default_text):
                if text and text.strip():
                    candidates.append(text)

            page_text = max(candidates, key=_text_quality_score, default="")
            if page_text:
                parts.append(page_text)
                for line in (line.strip() for line in page_text.splitlines()):
                    if line:
                        source_blocks.append(
                            DocumentTextBlock(
                                block_id=f"p{page_index}-b{len(source_blocks) + 1}",
                                text=normalize_text(line),
                                page=page_index,
                                source_type="pdf_line",
                            )
                        )

            table_text = _extract_pdf_table_text(page)
            if table_text:
                parts.append(table_text)

    normalized_text = normalize_text("\n\n".join(parts))
    text_block_count = len([line for line in normalized_text.splitlines() if line.strip()])
    warnings: list[str] = []
    needs_ocr = _needs_ocr(normalized_text, text_block_count, image_count)
    if needs_ocr:
        warnings.append("This PDF appears scanned or image-heavy; OCR is required for reliable extraction.")

    return DocumentExtractResult(
        normalized_text=normalized_text,
        engine="pdfplumber",
        page_count=page_count,
        text_block_count=text_block_count,
        image_count=image_count,
        max_columns=1,
        needs_ocr=needs_ocr,
        warnings=warnings,
        blocks=source_blocks,
    )


def _extract_pdf_table_text(page) -> str:
    rows: list[str] = []
    try:
        tables = page.extract_tables() or []
    except Exception:
        return ""

    for table in tables:
        for row in table:
            cells = [str(cell).strip() for cell in row if cell and str(cell).strip()]
            if cells:
                rows.append(" | ".join(cells))
    return "\n".join(rows)


def _text_quality_score(text: str) -> tuple[int, int, int]:
    non_empty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    heading_hits = sum(
        1
        for line in non_empty_lines
        for _, pattern in _SECTION_PATTERNS
        if pattern.match(line)
    )
    return (heading_hits, len(non_empty_lines), len(text))


def _group_pdf_blocks_by_column(
    blocks: list[tuple[float, float, float, float, str]],
    page_width: float,
) -> tuple[list[list[tuple[float, float, float, float, str]]], int]:
    """Keep multi-column CV text contiguous instead of interleaving rows."""
    reading_order = lambda block: (block[1], block[0])
    if len(blocks) < 4 or page_width <= 0:
        return [sorted(blocks, key=reading_order)], 1

    x_positions = sorted({round(block[0], 1) for block in blocks})
    if len(x_positions) < 2:
        return [sorted(blocks, key=reading_order)], 1

    gaps = [
        (right - left, left, right)
        for left, right in zip(x_positions, x_positions[1:])
    ]
    largest_gap, left_edge, right_edge = max(gaps)
    if largest_gap < page_width * 0.12:
        return [sorted(blocks, key=reading_order)], 1

    split_x = (left_edge + right_edge) / 2
    left_column = [block for block in blocks if block[0] < split_x]
    right_column = [block for block in blocks if block[0] >= split_x]
    if len(left_column) < 2 or len(right_column) < 2:
        return [sorted(blocks, key=reading_order)], 1

    return [
        sorted(left_column, key=reading_order),
        sorted(right_column, key=reading_order),
    ], 2


def _needs_ocr(normalized_text: str, text_block_count: int, image_count: int) -> bool:
    if image_count <= 0:
        return False
    return len(normalized_text.strip()) < 300 or text_block_count < 5


def extract_text_from_docx(data: bytes) -> str:
    return extract_docx_document(data).normalized_text


def extract_docx_document(data: bytes) -> DocumentExtractResult:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(BytesIO(data))
    parts: list[str] = []
    source_blocks: list[DocumentTextBlock] = []

    for item in doc.iter_inner_content():
        if isinstance(item, Paragraph):
            candidates = [(item.text.strip(), "paragraph")]
        elif isinstance(item, Table):
            candidates = [
                ("\n".join(cell.text.strip() for cell in row.cells if cell.text.strip()), "table_row")
                for row in item.rows
            ]
        else:
            continue

        for text, source_type in candidates:
            if text:
                normalized = normalize_text(text)
                parts.append(normalized)
                source_blocks.append(
                    DocumentTextBlock(
                        block_id=f"d-b{len(source_blocks) + 1}",
                        text=normalized,
                        page=1,
                        source_type=source_type,
                    )
                )

    normalized_text = normalize_text("\n".join(parts))
    return DocumentExtractResult(
        normalized_text=normalized_text,
        engine="python-docx",
        text_block_count=len([line for line in normalized_text.splitlines() if line.strip()]),
        blocks=source_blocks,
    )


def extract_normalized_text(filename: str, data: bytes) -> str:
    """Extract normalized text from a supported CV file."""
    return extract_document_text(filename, data).normalized_text


def extract_document_text(filename: str, data: bytes) -> DocumentExtractResult:
    """Extract normalized text and metadata from a supported CV file."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_document(data)
    if suffix in (".docx", ".doc"):
        if suffix == ".doc":
            raise ValueError("Legacy .doc not supported; please upload .docx or .pdf")
        return extract_docx_document(data)
    raise ValueError(f"Unsupported file type: {suffix}")


def process_upload(filename: str, data: bytes, *, mask: bool = True) -> tuple[CvSections, LocalMetrics, str]:
    """Full local pipeline: bytes -> sections + metrics (+ normalized full text)."""
    raw = extract_normalized_text(filename, data)

    if not raw.strip():
        raise ValueError("No extractable text in document (scanned PDF may need OCR)")

    if mask:
        raw = mask_pii(raw)

    sections = split_into_sections(raw)
    metrics = compute_local_metrics(sections)
    return sections, metrics, raw
