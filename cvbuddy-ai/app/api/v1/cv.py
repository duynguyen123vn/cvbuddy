from time import perf_counter

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.pipeline.analyze import run_cv_analyze
from app.pipeline.context_matrix import IndustryContextError
from app.pipeline.extract import ExtractMode, TargetLanguage, extract_cv_sections
from app.core.config import settings
from app.core.response_metadata import attach_provider_metadata
from app.schemas.cv import (
    AnalyzeCvRequest,
    AnalyzeCvResponse,
    CvSections,
    LanguageMode,
    LlmModel,
)

router = APIRouter(prefix="/cv")


def _has_extracted_content(sections: CvSections) -> bool:
    return any(
        item.strip()
        for values in sections.model_dump().values()
        for item in values
        if isinstance(item, str)
    )


def _effective_target_language(
    query_value: TargetLanguage,
    form_value: TargetLanguage | None,
) -> TargetLanguage:
    return form_value or query_value


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
    started = perf_counter()
    if not _has_extracted_content(body.sections):
        raise HTTPException(status_code=422, detail="No extracted CV content was provided.")
    try:
        result = await run_cv_analyze(body)
        meta = result.meta
        provider = meta.get("source", "groq") if isinstance(meta, dict) else "groq"
        model = meta.get("model", body.llm_model.value if body.llm_model else settings.groq_analyze_model) if isinstance(meta, dict) else settings.groq_analyze_model
        return attach_provider_metadata(
            result,
            provider=provider,
            model=model,
            source=provider,
            latency_ms=(perf_counter() - started) * 1000,
        )
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
    target_language_form: TargetLanguage | None = Form(None, alias="target_language"),
    debug: bool = Query(False, description="Include a short normalized text preview for extraction QA."),
    llm_model: LlmModel | None = Query(
        None,
        description="Groq model override for AI parsing.",
    ),
) -> dict:
    """Extract PDF/DOCX text, parse CV sections, and compute local metrics."""
    started = perf_counter()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    data = await file.read()
    target_language = _effective_target_language(target_language, target_language_form)
    effective_model = llm_model.value if llm_model else None
    if effective_model is None:
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

    if not result.normalized_text.strip() and not _has_extracted_content(result.sections):
        raise HTTPException(status_code=422, detail="No extractable CV content was found.")

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
            "llm_model": result.model_name,
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
    return attach_provider_metadata(
        response,
        provider=result.provider,
        model=result.model_name,
        source=(result.provider if result.provider in {"groq", "mock"} else result.parser_source),
        latency_ms=(perf_counter() - started) * 1000,
    )


@router.post("/extract-and-analyze", response_model=AnalyzeCvResponse)
async def extract_and_analyze(
    file: UploadFile = File(...),
    industry_slug: str = "language",
    vertical_slug: str | None = None,
    company_model: str = "corporate",
    mode: ExtractMode = ExtractMode.HYBRID,
    target_language: TargetLanguage = Query(TargetLanguage.AUTO),
    target_language_form: TargetLanguage | None = Form(None, alias="target_language"),
    llm_model: LlmModel | None = None,
    strict_industry_match: bool = False,
) -> AnalyzeCvResponse:
    """Upload a file, parse sections, then analyze the parsed CV."""
    from app.schemas.cv import CompanyModel

    started = perf_counter()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    data = await file.read()
    target_language = _effective_target_language(target_language, target_language_form)
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

    if not extract_result.normalized_text.strip() and not _has_extracted_content(extract_result.sections):
        raise HTTPException(status_code=422, detail="No extractable CV content was found.")
    if not _has_extracted_content(extract_result.sections):
        raise HTTPException(status_code=422, detail="No CV sections were extracted for analysis.")

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
        result = await run_cv_analyze(request)
        current = result.meta if isinstance(result.meta, dict) else {}
        provider = current.get("source", "groq")
        model = current.get("model", llm_model.value if llm_model else settings.groq_analyze_model)
        return attach_provider_metadata(
            result,
            provider=provider,
            model=model,
            source=provider,
            latency_ms=(perf_counter() - started) * 1000,
        )
    except IndustryContextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
