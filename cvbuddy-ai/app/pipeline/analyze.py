"""Orchestrate: context matrix → configured LLM → postprocess."""

from __future__ import annotations

import logging
import re

from app.core.config import settings
from app.pipeline.context_matrix import ContextMatrixBuilder
from app.pipeline.postprocess import parse_analyze_response
from app.schemas.cv import AnalyzeCvRequest, AnalyzeCvResponse
from app.services.llm import LLMService, get_llm_service
from app.services.errors import LLMQuotaError, LLMUpstreamError
from app.services.mock_llm import mock_analyze_cv

logger = logging.getLogger(__name__)

_VIETNAMESE_CHARS = "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
_VIETNAMESE_WORDS = {
    "và", "với", "của", "cần", "nên", "không", "được", "trong", "cho",
    "kinh", "nghiệm", "kỹ", "năng", "công", "việc", "mục", "tiêu", "thiếu",
}
_ENGLISH_WORDS = {
    "the", "and", "with", "should", "use", "include", "missing", "experience",
    "skills", "job", "description", "provided", "improve", "section", "clear",
}
_GENERIC_FEEDBACK_PHRASES = (
    "thiếu tiêu đề chuyên ngành cụ thể",
    "ngày tháng không thống nhất",
    "thiếu tính cụ thể",
    "cung cấp thông tin cụ thể",
    "sử dụng từ ngữ chuyên nghiệp",
    "từ ngữ không chuyên nghiệp",
    "sử dụng tiêu đề chuyên ngành cụ thể",
    "be more specific",
    "provide more specific information",
    "use professional language",
    "lacks specificity",
)

ANALYZE_RESPONSE_SCHEMA_HINT = """
Return ONLY valid JSON matching this shape:
{
  "overall_score": 0-100,
  "dimensions": {
    "layout_ats": {"score": 0-100, "issues": [], "fixes": []},
    "language": {"score": 0-100, "issues": [], "fixes": []},
    "keywords": {"score": 0-100, "missing": [], "suggested_bullets": []},
    "jd_fit": {"score": 0-100, "gaps": []}
  },
  "rewrites": [{"section": "", "original_ref": "", "suggested_vi": "", "suggested_en": "", "change_reason": "", "needs_user_fact": false}],
  "company_model_feedback": "",
  "confidence": 0.0-1.0
}
Do not invent experience, employers, tools, dates, or metrics.
For keywords.suggested_bullets, use only tools, techniques, and outcomes that appear in cv_sections or jd_extract.
Do not use strong claims like deployed, launched, managed, led, optimized, scaled, productionized, or improved unless the source text supports that claim.
If a suggested keyword is missing from the CV, list it in keywords.missing; do not turn it into an accomplishment bullet.
Never insert made-up metrics into suggested_vi or suggested_en.
If the source lacks a useful metric, either keep the rewrite metric-free or use a clearly marked placeholder like [add measured accuracy].
Set needs_user_fact true only when the rewrite contains a placeholder or requires the candidate to verify/add a fact.
When jd_extract is null, set jd_fit.score to a neutral 60-70 range and use gaps to say that no job description was provided; do not treat missing JD as poor fit.
company_model_feedback must reference the requested company_model and must not say the CV is not tailored to a specific company model when company_model is provided.
Follow the request language exactly for all human-readable feedback.
If language is "vi", populate suggested_vi and set suggested_en to null.
If language is "en", populate suggested_en and set suggested_vi to null.
If language is "both", populate both suggested_vi and suggested_en, keeping them as faithful equivalents.
Use only industry_context.active_vertical for keyword and role-fit assessment. Do not use sibling verticals.
Every issue must cite concrete evidence from cv_sections: quote the exact phrase, name the missing section, or identify the exact date formats being compared.
Every fix must correspond to a cited issue and give a concrete replacement, target heading, date format, or rewritten example.
Do not claim dates are inconsistent unless you can quote at least two conflicting date formats from cv_sections.
Do not call wording unprofessional, vague, or insufficiently specific without quoting the exact problematic wording.
Never output filler such as "be more specific", "use professional language", "thiếu tính cụ thể", or "sử dụng từ ngữ chuyên nghiệp" by itself.
Return an empty issues/fixes list when there is no evidence-backed finding; do not manufacture advice to fill the schema.
keywords.missing must contain only active_vertical or jd_extract terms that are genuinely absent from cv_sections.
keywords.suggested_bullets must be rewrites of existing source content. If no grounded rewrite is possible, return an empty list.
rewrites are material CV improvements, not translations. Never add a rewrite merely to translate original_ref between Vietnamese and English.
Only add a rewrite when the source has a concrete weakness such as redundancy, unclear ownership, weak verb choice, poor ATS structure, or an unsupported/vague statement.
The suggested version must materially improve clarity, concision, evidence, or ATS readability while preserving all source facts.
If original_ref is already clear and ATS-ready, omit it from rewrites. Returning an empty rewrites list is correct.
For language "vi", select only Vietnamese original_ref entries. Never select an English original_ref merely to translate it into Vietnamese.
For language "en", select only English original_ref entries. Never select a Vietnamese original_ref merely to translate it into English.
For language "both", use only one original_ref from each duplicated bilingual pair. First improve it in its own source language, then provide faithful VI and EN equivalents of that improved statement.
For every rewrite, the suggestion matching original_ref's language must be materially different from original_ref. If only the other-language suggestion differs, omit the rewrite.
change_reason must name the exact weakness and improvement. Do not use generic reasons such as "more professional" or "clearer" without specifying what changed.
Never use translation, translated, dịch, chuyển ngữ, or language consistency as the sole change_reason.
"""


def _feedback_language(request: AnalyzeCvRequest) -> str:
    return "en" if request.language.value == "en" else "vi"


def _language_contract(request: AnalyzeCvRequest) -> str:
    feedback_language = _feedback_language(request)
    if request.language.value == "both":
        rewrite_rule = (
            "For rewrites only, fill both suggested_vi and suggested_en. "
            "All other feedback must be Vietnamese."
        )
    elif feedback_language == "vi":
        rewrite_rule = "Fill suggested_vi only and set suggested_en to null."
    else:
        rewrite_rule = "Fill suggested_en only and set suggested_vi to null."
    language_name = "Vietnamese" if feedback_language == "vi" else "English"
    return (
        f"MANDATORY OUTPUT LANGUAGE: Write every issue, fix, suggested bullet, gap, "
        f"and company_model_feedback in {language_name}. {rewrite_rule} "
        "Keep product names, technologies, certifications, and quoted original_ref unchanged."
    )


def _feedback_text(raw: dict) -> str:
    dimensions = raw.get("dimensions") or {}
    parts = [str(raw.get("company_model_feedback") or "")]
    for dimension in dimensions.values():
        if not isinstance(dimension, dict):
            continue
        for key in ("issues", "fixes", "suggested_bullets", "gaps"):
            values = dimension.get(key) or []
            if isinstance(values, list):
                parts.extend(str(value) for value in values)
    return " ".join(parts)


def _feedback_items(raw: dict) -> list[str]:
    dimensions = raw.get("dimensions") or {}
    items = [str(raw.get("company_model_feedback") or "")]
    for dimension in dimensions.values():
        if not isinstance(dimension, dict):
            continue
        for key in ("issues", "fixes", "suggested_bullets", "gaps"):
            values = dimension.get(key) or []
            if isinstance(values, list):
                items.extend(str(value) for value in values)
    return [item for item in items if item.strip()]


def _language_scores(text: str) -> tuple[int, int]:
    lowered = text.lower()
    tokens = re.findall(r"[a-zA-ZÀ-ỹ]+", lowered)
    vi_score = sum(lowered.count(char) for char in _VIETNAMESE_CHARS)
    vi_score += sum(3 for token in tokens if token in _VIETNAMESE_WORDS)
    en_score = sum(3 for token in tokens if token in _ENGLISH_WORDS)
    return vi_score, en_score


def _feedback_language_mismatch(raw: dict, expected_language: str) -> bool:
    wrong = 0
    classified = 0
    for item in _feedback_items(raw):
        vi_score, en_score = _language_scores(item)
        if max(vi_score, en_score) < 3:
            continue
        classified += 1
        if expected_language == "vi" and en_score > max(vi_score * 1.25, 2):
            wrong += 1
        elif expected_language == "en" and vi_score > max(en_score * 1.25, 2):
            wrong += 1
    if wrong >= 2 or (classified >= 2 and wrong / classified >= 0.4):
        return True

    vi_score, en_score = _language_scores(_feedback_text(raw))
    if expected_language == "vi":
        return en_score >= 9 and en_score > vi_score * 1.5
    return vi_score >= 9 and vi_score > en_score * 1.5


def _feedback_is_generic(raw: dict) -> bool:
    dimensions = raw.get("dimensions") or {}
    items = [str(raw.get("company_model_feedback") or "")]
    for dimension in dimensions.values():
        if not isinstance(dimension, dict):
            continue
        for key in ("issues", "fixes", "suggested_bullets", "gaps"):
            values = dimension.get(key) or []
            if isinstance(values, list):
                items.extend(str(value) for value in values)

    for item in items:
        lowered = item.casefold()
        has_evidence = bool(re.search(r"[\"'“”‘’:\d]", item))
        if not has_evidence and any(phrase in lowered for phrase in _GENERIC_FEEDBACK_PHRASES):
            return True
    return False


async def run_cv_analyze(
    request: AnalyzeCvRequest,
    *,
    llm_service: LLMService | None = None,
) -> AnalyzeCvResponse:
    if request.local_metrics is None:
        from app.pipeline.preprocess import compute_local_metrics

        request = request.model_copy(update={"local_metrics": compute_local_metrics(request.sections)})

    builder = ContextMatrixBuilder()
    builder.validate_industry_match(request)
    context = builder.build_for_analyze(request)
    user_payload = builder.to_prompt_payload(context)

    requested_model = request.llm_model.value if request.llm_model else None
    if requested_model is None:
        requested_model = settings.groq_analyze_model
    service = llm_service or get_llm_service(model_name=requested_model)
    if service.use_mock:
        raw = mock_analyze_cv(request)
        result = parse_analyze_response(raw, request)
        result.meta = {
            "source": "mock",
            "model": requested_model or "mock",
            "language": request.language.value,
        }
        return result

    language_contract = _language_contract(request)
    system = (
        context.get("system_instruction", "")
        + "\n\n"
        + language_contract
        + "\n\n"
        + ANALYZE_RESPONSE_SCHEMA_HINT
    )
    try:
        raw = await service.generate_json(
            system_instruction=system,
            user_message=user_payload,
        )
    except (LLMQuotaError, LLMUpstreamError):
        if (
            llm_service is not None
            or settings.llm_provider != "groq"
            or requested_model == settings.groq_fallback_model
        ):
            raise
        logger.warning(
            "Primary Groq analysis model failed; retrying with %s",
            settings.groq_fallback_model,
        )
        service = get_llm_service(model_name=settings.groq_fallback_model)
        raw = await service.generate_json(
            system_instruction=system,
            user_message=user_payload,
        )
    language_mismatch = _feedback_language_mismatch(raw, _feedback_language(request))
    generic_feedback = _feedback_is_generic(raw)
    provider_name = getattr(service, "provider_name", "")
    allow_quality_retry = provider_name != "groq" or llm_service is not None
    should_retry_language = language_mismatch
    if should_retry_language or (allow_quality_retry and generic_feedback):
        reasons = []
        if language_mismatch:
            reasons.append("wrong output language")
        if generic_feedback:
            reasons.append("generic feedback without evidence")
        logger.warning("LLM response quality issue (%s); retrying once", ", ".join(reasons))
        if (
            language_mismatch
            and llm_service is None
            and provider_name == "groq"
            and getattr(service, "model_name", "") != settings.groq_fallback_model
        ):
            service = get_llm_service(model_name=settings.groq_fallback_model)
        raw = await service.generate_json(
            system_instruction=(
                system
                + "\n\nYour previous response failed quality checks. Regenerate the entire JSON now. "
                + "Obey the mandatory language, cite exact CV evidence for every issue, provide concrete fixes, "
                + "and omit any generic or unrelated advice."
            ),
            user_message=user_payload,
        )
    result = parse_analyze_response(raw, request)
    result.meta = {
        "source": getattr(service, "provider_name", "groq"),
        "model": getattr(service, "model_name", requested_model or "unknown"),
        "language": request.language.value,
    }
    return result
