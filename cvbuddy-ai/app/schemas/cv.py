from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class CompanyModel(StrEnum):
    CORPORATE = "corporate"
    STARTUP_AGENCY = "startup_agency"


class LanguageMode(StrEnum):
    VI = "vi"
    EN = "en"
    BOTH = "both"


class UserTier(StrEnum):
    FREE = "free"
    SUBSCRIPTION = "subscription"


class LlmModel(StrEnum):
    QWEN_3_6_27B = "qwen/qwen3.6-27b"
    QWEN_3_32B = "qwen/qwen3-32b"


class CvSections(BaseModel):
    """Structured CV text sent to the configured LLM; raw files stay local."""

    summary: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)


class JdExtract(BaseModel):
    """Job description pre-parsed locally or by web tier."""

    role_title: str | None = None
    company_name: str | None = None
    required_keywords: list[str] = Field(default_factory=list)
    preferred_keywords: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)


class LocalMetrics(BaseModel):
    """Computed locally before LLM — grounds scoring in facts."""

    bullet_count: int = 0
    quantified_bullet_count: int = 0
    has_quantified_bullets: bool = False
    avg_bullet_length: float = 0.0
    section_count: int = 0
    detected_languages: list[str] = Field(default_factory=list)


class CvSourceBlock(BaseModel):
    block_id: str
    text: str
    page: int
    column: int = 1
    bbox: tuple[float, float, float, float] | None = None
    source_type: str = "text"


class CvStructuredRecord(BaseModel):
    raw_text: str
    date: str | None = None
    title: str | None = None
    role: str | None = None
    organization: str | None = None
    details: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)


class CvStructuredDocument(BaseModel):
    personal_info: dict[str, list[str]] = Field(default_factory=dict)
    summary: list[str] = Field(default_factory=list)
    experience: list[CvStructuredRecord] = Field(default_factory=list)
    projects: list[CvStructuredRecord] = Field(default_factory=list)
    education: list[CvStructuredRecord] = Field(default_factory=list)
    skills: dict[str, list[str]] = Field(default_factory=dict)
    certifications: list[CvStructuredRecord] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    activities: list[CvStructuredRecord] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)
    unclassified: list[CvSourceBlock] = Field(default_factory=list)
    raw_blocks: list[CvSourceBlock] = Field(default_factory=list)


class ExtractionCoverage(BaseModel):
    source_block_count: int = 0
    classified_block_count: int = 0
    unclassified_block_count: int = 0
    ignored_heading_count: int = 0
    retained_block_count: int = 0
    coverage_score: float = 0.0
    classification_rate: float = 0.0
    unclassified_block_ids: list[str] = Field(default_factory=list)


class AnalyzeCvRequest(BaseModel):
    """Contract: web/Node sends after local extract (or AI service extract in phase A)."""

    sections: CvSections
    industry_slug: str = Field(..., examples=["marketing", "language", "computer_science"])
    vertical_slug: str | None = Field(
        None,
        description="Sub-industry context, e.g. english_language vs hospitality_management",
        examples=["english_language", "hospitality_management"],
    )
    company_model: CompanyModel = CompanyModel.CORPORATE
    jd_extract: JdExtract | None = None
    language: LanguageMode = LanguageMode.BOTH
    tier: UserTier = UserTier.FREE
    local_metrics: LocalMetrics | None = None
    llm_model: LlmModel | None = Field(
        None,
        description="Allowed Groq model override. Uses GROQ_MODEL when omitted.",
    )
    strict_industry_match: bool = Field(
        False,
        description="Reject analysis when the CV has no evidence for the selected vertical.",
    )


class DimensionScore(BaseModel):
    score: int = Field(..., ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    fixes: list[str] = Field(default_factory=list)


class KeywordsDimension(BaseModel):
    score: int = Field(..., ge=0, le=100)
    missing: list[str] = Field(default_factory=list)
    suggested_bullets: list[str] = Field(default_factory=list)


class JdFitDimension(BaseModel):
    score: int = Field(..., ge=0, le=100)
    gaps: list[str] = Field(default_factory=list)


class CvDimensions(BaseModel):
    layout_ats: DimensionScore
    language: DimensionScore
    keywords: KeywordsDimension
    jd_fit: JdFitDimension


class CvRewrite(BaseModel):
    section: str
    original_ref: str = Field(..., description="Snippet from input sections — for FE diff/highlight")
    suggested_vi: str | None = None
    suggested_en: str | None = None
    change_reason: str = Field(
        "",
        description="Concrete explanation of what the rewrite improves; not a translation note.",
    )
    needs_user_fact: bool = Field(
        False,
        description="True when AI suggests metrics/facts not present in source text",
    )


class AnalyzeCvResponse(BaseModel):
    overall_score: int = Field(..., ge=0, le=100)
    dimensions: CvDimensions
    rewrites: list[CvRewrite] = Field(default_factory=list)
    company_model_feedback: str = ""
    confidence: float = Field(..., ge=0.0, le=1.0)
    disclaimer: str = "AI-assisted feedback only; not a hiring guarantee."
    meta: dict[str, str] = Field(
        default_factory=lambda: {"source": "groq"}
    )
