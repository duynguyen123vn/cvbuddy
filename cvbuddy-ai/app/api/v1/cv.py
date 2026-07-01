from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.pipeline.analyze import run_cv_analyze
from app.pipeline.context_matrix import IndustryContextError
from app.pipeline.extract import ExtractMode, TargetLanguage, extract_cv_sections
from app.core.config import settings
from app.schemas.cv import (
    AnalyzeCvRequest,
    AnalyzeCvResponse,
    CvSections,
    LanguageMode,
    LlmModel,
)
from app.services.errors import LLMQuotaError, LLMUpstreamError

router = APIRouter(prefix="/cv")


def _resolve_analysis_language(
    target_language: TargetLanguage,
    sections: CvSections,
) -> LanguageMode:
    if target_language == TargetLanguage.EN:
        return LanguageMode.EN
    if target_language == TargetLanguage.VI:
        return LanguageMode.VI
    if target_language == TargetLanguage.BOTH:
        return LanguageMode.BOTH

    text = " ".join(
        item
        for values in sections.model_dump().values()
        for item in values
    ).lower()
    padded_text = f" {text} "
    vietnamese_marks = sum(text.count(char) for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    vietnamese_signals = sum(
        padded_text.count(word)
        for word in (" và ", " với ", " của ", " kinh nghiệm ", " học vấn ", " kỹ năng ", " phát triển ", " mục tiêu ")
    )
    english_signals = sum(
        padded_text.count(word)
        for word in (" the ", " and ", " with ", " developed ", " education ", " experience ", " skills ")
    )
    if vietnamese_signals > 0 and english_signals > 0:
        return LanguageMode.BOTH
    return LanguageMode.VI if vietnamese_signals > 0 or vietnamese_marks >= 6 else LanguageMode.EN


@router.post("/analyze", response_model=AnalyzeCvResponse)
async def analyze_cv(body: AnalyzeCvRequest) -> AnalyzeCvResponse:
    """Main endpoint; expects pre-extracted sections from web or prior extract call."""
    try:
        return await run_cv_analyze(body)
    except LLMQuotaError as exc:
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        raise HTTPException(
            status_code=429,
            detail="LLM quota exceeded. Please retry later.",
            headers=headers,
        ) from exc
    except LLMUpstreamError as exc:
        status = exc.status_code or 502
        raise HTTPException(status_code=status, detail="LLM upstream error. See server logs.") from exc
    except IndustryContextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/extract", response_model=dict)
async def extract_cv(
    file: UploadFile = File(...),
    mode: ExtractMode = Query(ExtractMode.HYBRID, description="local, ai, or hybrid section parser."),
    target_language: TargetLanguage = Query(
        TargetLanguage.AUTO,
        description="auto, en, vi, or both. AI parser uses this to avoid merging bilingual CV versions.",
    ),
    debug: bool = Query(False, description="Include a short normalized text preview for extraction QA."),
    llm_model: LlmModel | None = Query(
        None,
        description="Groq model override for AI parsing.",
    ),
) -> dict:
    """Extract PDF/DOCX text, parse CV sections, and compute local metrics."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    data = await file.read()
    effective_model = llm_model.value if llm_model else None
    if effective_model is None:
        if settings.llm_provider == "ollama":
            effective_model = settings.ollama_extract_model
        elif settings.llm_provider == "groq":
            effective_model = settings.groq_extract_model
    try:
        result = await extract_cv_sections(
            file.filename,
            data,
            mode=mode,
            target_language=target_language,
            llm_model=effective_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMQuotaError as exc:
        raise HTTPException(status_code=429, detail="LLM quota exceeded. Please retry later.") from exc
    except LLMUpstreamError as exc:
        status = exc.status_code or 502
        raise HTTPException(status_code=status, detail="AI provider is unavailable or timed out.") from exc

    response = {
        "sections": result.sections.model_dump(),
        "structured_document": result.structured_document.model_dump(),
        "coverage": result.coverage.model_dump(),
        "local_metrics": result.metrics.model_dump(),
        "meta": {
            "extract_mode": mode.value,
            "target_language": result.target_language.value,
            "analysis_language": _resolve_analysis_language(
                target_language,
                result.sections,
            ).value,
            "llm_model": effective_model,
            "parser_source": result.parser_source,
            "local_quality_score": result.quality.score,
            "fallback_reason": result.fallback_reason,
            "document": {
                "engine": result.document.engine,
                "page_count": result.document.page_count,
                "text_block_count": result.document.text_block_count,
                "image_count": result.document.image_count,
                "max_columns": result.document.max_columns,
                "needs_ocr": result.document.needs_ocr,
                "warnings": result.document.warnings,
            },
        },
        "normalized_text_length": len(result.normalized_text),
    }
    if debug:
        response["normalized_text_preview"] = result.normalized_text[:2000]
    return response


@router.post("/extract-and-analyze", response_model=AnalyzeCvResponse)
async def extract_and_analyze(
    file: UploadFile = File(...),
    industry_slug: str = "language",
    vertical_slug: str | None = None,
    company_model: str = "corporate",
    mode: ExtractMode = ExtractMode.HYBRID,
    target_language: TargetLanguage = TargetLanguage.AUTO,
    llm_model: LlmModel | None = None,
    strict_industry_match: bool = True,
) -> AnalyzeCvResponse:
    """Upload a file, parse sections, then analyze the parsed CV."""
    from app.schemas.cv import CompanyModel

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    data = await file.read()
    try:
        extract_result = await extract_cv_sections(
            file.filename,
            data,
            mode=mode,
            target_language=target_language,
            llm_model=llm_model.value if llm_model else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    request = AnalyzeCvRequest(
        sections=extract_result.sections,
        industry_slug=industry_slug,
        vertical_slug=vertical_slug,
        company_model=CompanyModel(company_model),
        local_metrics=extract_result.metrics,
        llm_model=llm_model,
        language=_resolve_analysis_language(target_language, extract_result.sections),
        strict_industry_match=strict_industry_match,
    )
    try:
        return await run_cv_analyze(request)
    except LLMQuotaError as exc:
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        raise HTTPException(
            status_code=429,
            detail="LLM quota exceeded. Please retry later.",
            headers=headers,
        ) from exc
    except LLMUpstreamError as exc:
        status = exc.status_code or 502
        raise HTTPException(status_code=status, detail="LLM upstream error. See server logs.") from exc
    except IndustryContextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
