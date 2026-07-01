"""Validate and sanitize LLM JSON output locally."""

from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher

from pydantic import ValidationError

from app.schemas.cv import AnalyzeCvRequest, AnalyzeCvResponse, CvRewrite, LanguageMode

logger = logging.getLogger(__name__)


def clamp_score(value: int, *, max_cap: int | None = None) -> int:
    v = max(0, min(100, int(value)))
    if max_cap is not None:
        v = min(v, max_cap)
    return v


_STRONG_CLAIMS = {
    "deployed": "developed",
    "launched": "built",
    "managed": "contributed to",
    "led": "contributed to",
    "optimized": "improved",
    "scaled": "built",
    "productionized": "developed",
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


def _source_blob(request: AnalyzeCvRequest) -> str:
    return " ".join(
        line
        for lines in request.sections.model_dump().values()
        for line in (lines if isinstance(lines, list) else [])
    ).lower()


def _rewrite_grounded(rewrite: CvRewrite, request: AnalyzeCvRequest) -> CvRewrite:
    """Flag suggestions that introduce facts not found in source bullets."""
    source_blob = _source_blob(request)

    ref = rewrite.original_ref.lower().strip()
    if ref and ref not in source_blob:
        rewrite.needs_user_fact = True

    for field in ("suggested_vi", "suggested_en"):
        text = getattr(rewrite, field)
        if not text:
            continue
        # Heuristic: digits in suggestion but not in original_ref
        import re

        sug_nums = set(re.findall(r"\d+", text))
        ref_nums = set(re.findall(r"\d+", rewrite.original_ref or ""))
        if sug_nums - ref_nums:
            rewrite.needs_user_fact = True

    return rewrite


def _sanitize_suggested_bullets(response: AnalyzeCvResponse, request: AnalyzeCvRequest) -> None:
    source_blob = _source_blob(request)
    sanitized: list[str] = []
    for bullet in response.dimensions.keywords.suggested_bullets:
        cleaned = bullet
        for claim, replacement in _STRONG_CLAIMS.items():
            if re.search(rf"\b{claim}\b", cleaned, flags=re.I) and claim not in source_blob:
                cleaned = re.sub(rf"\b{claim}\b", replacement, cleaned, flags=re.I)
        sanitized.append(cleaned)
    response.dimensions.keywords.suggested_bullets = sanitized


def _normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9+#.]+", " ", without_marks).strip()


def _remove_present_missing_keywords(
    response: AnalyzeCvResponse,
    request: AnalyzeCvRequest,
) -> None:
    source = _normalize_search_text(_source_blob(request))
    response.dimensions.keywords.missing = [
        keyword
        for keyword in response.dimensions.keywords.missing
        if _normalize_search_text(keyword) not in source
    ]


def _remove_generic_feedback(response: AnalyzeCvResponse) -> None:
    def keep(value: str) -> bool:
        lowered = value.casefold()
        has_evidence = bool(re.search(r"[\"'“”‘’:\d]", value))
        return has_evidence or not any(
            phrase in lowered for phrase in _GENERIC_FEEDBACK_PHRASES
        )

    response.dimensions.layout_ats.issues = [
        item for item in response.dimensions.layout_ats.issues if keep(item)
    ]
    response.dimensions.layout_ats.fixes = [
        item for item in response.dimensions.layout_ats.fixes if keep(item)
    ]
    response.dimensions.language.issues = [
        item for item in response.dimensions.language.issues if keep(item)
    ]
    response.dimensions.language.fixes = [
        item for item in response.dimensions.language.fixes if keep(item)
    ]


def _normalize_missing_jd_fit(response: AnalyzeCvResponse, request: AnalyzeCvRequest) -> None:
    if request.jd_extract is not None:
        return

    jd_fit = response.dimensions.jd_fit
    jd_fit.score = max(clamp_score(jd_fit.score), 60)
    no_jd_pattern = re.compile(
        r"no job description|job description.*not provided|không.*mô tả công việc|chưa.*mô tả công việc",
        re.I,
    )
    jd_fit.gaps = [gap for gap in jd_fit.gaps if not no_jd_pattern.search(gap)]
    if request.language == LanguageMode.EN:
        message = "No job description was provided, so fit is assessed only against general role expectations."
    else:
        message = "Chưa có mô tả công việc, vì vậy mức độ phù hợp chỉ được đánh giá theo yêu cầu chung của vị trí."
    jd_fit.gaps.insert(0, message)


def _is_english_text(value: str) -> bool:
    lowered = value.casefold()
    tokens = re.findall(r"[a-zA-Z]+", lowered)
    signals = {
        "the", "and", "with", "for", "from", "should", "use", "remove", "add",
        "section", "skills", "experience", "project", "missing", "lack", "include",
        "developed", "implemented", "evaluated", "model", "data",
    }
    return len(set(tokens) & signals) >= 2 or (
        len(tokens) >= 8 and not _is_vietnamese_text(value)
    )


def _enforce_feedback_language(
    response: AnalyzeCvResponse,
    request: AnalyzeCvRequest,
) -> None:
    expected_vietnamese = request.language != LanguageMode.EN

    def keep(value: str) -> bool:
        if expected_vietnamese:
            return _is_vietnamese_text(value) or not _is_english_text(value)
        return not _is_vietnamese_text(value)

    response.dimensions.layout_ats.issues = [
        item for item in response.dimensions.layout_ats.issues if keep(item)
    ]
    response.dimensions.layout_ats.fixes = [
        item for item in response.dimensions.layout_ats.fixes if keep(item)
    ]
    response.dimensions.language.issues = [
        item for item in response.dimensions.language.issues if keep(item)
    ]
    response.dimensions.language.fixes = [
        item for item in response.dimensions.language.fixes if keep(item)
    ]
    response.dimensions.keywords.suggested_bullets = [
        item for item in response.dimensions.keywords.suggested_bullets if keep(item)
    ]
    response.dimensions.jd_fit.gaps = [
        item for item in response.dimensions.jd_fit.gaps if keep(item)
    ]
    if response.company_model_feedback and not keep(response.company_model_feedback):
        response.company_model_feedback = ""


def _enforce_rewrite_language(
    response: AnalyzeCvResponse,
    request: AnalyzeCvRequest,
) -> None:
    for rewrite in response.rewrites:
        if request.language == LanguageMode.EN:
            rewrite.suggested_vi = None
        elif request.language == LanguageMode.VI:
            rewrite.suggested_en = None


def _normalize_disclaimer(
    response: AnalyzeCvResponse,
    request: AnalyzeCvRequest,
) -> None:
    if request.language == LanguageMode.EN:
        response.disclaimer = "AI-assisted feedback only; not a hiring guarantee."
    else:
        response.disclaimer = "Phản hồi có sự hỗ trợ của AI; không đảm bảo kết quả tuyển dụng."


def _is_vietnamese_text(value: str) -> bool:
    lowered = value.casefold()
    marks = sum(
        lowered.count(char)
        for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    )
    tokens = set(re.findall(r"[a-zA-ZÀ-ỹ]+", lowered))
    vietnamese_tokens = {
        "và", "với", "của", "cho", "trong", "sinh", "viên", "thành", "phát",
        "triển", "xây", "dựng", "hệ", "thống", "kinh", "nghiệm", "kỹ", "năng",
        "nghiên", "cứu", "mô", "hình", "thực", "tập", "điểm", "danh",
    }
    token_hits = len(tokens & vietnamese_tokens)
    return marks >= 2 or token_hits >= 2 or "đ" in lowered


def _rewrite_similarity(original: str, suggested: str) -> float:
    original_normalized = _normalize_search_text(original)
    suggested_normalized = _normalize_search_text(suggested)
    if not original_normalized or not suggested_normalized:
        return 0.0
    return SequenceMatcher(None, original_normalized, suggested_normalized).ratio()


_TRANSLATION_ONLY_REASON = re.compile(
    r"\b(translat(?:e|ed|ion)|bilingual equivalent)\b|dịch|chuyển ngữ|chuyển sang tiếng",
    re.I,
)


def _remove_noop_rewrites(
    response: AnalyzeCvResponse,
    request: AnalyzeCvRequest,
) -> None:
    useful_rewrites: list[CvRewrite] = []
    for rewrite in response.rewrites:
        source_is_vietnamese = _is_vietnamese_text(rewrite.original_ref)
        if request.language == LanguageMode.VI and not source_is_vietnamese:
            continue
        if request.language == LanguageMode.EN and source_is_vietnamese:
            continue
        if _TRANSLATION_ONLY_REASON.search(rewrite.change_reason or ""):
            continue

        same_language_suggestion = (
            rewrite.suggested_vi if source_is_vietnamese else rewrite.suggested_en
        )
        if not same_language_suggestion:
            continue
        if _rewrite_similarity(rewrite.original_ref, same_language_suggestion) >= 0.90:
            continue
        useful_rewrites.append(rewrite)
    response.rewrites = useful_rewrites


def apply_rule_overlay(response: AnalyzeCvResponse, request: AnalyzeCvRequest) -> AnalyzeCvResponse:
    metrics = request.local_metrics
    if metrics and not metrics.has_quantified_bullets:
        kw = response.dimensions.keywords
        kw.score = clamp_score(kw.score, max_cap=65)

    _sanitize_suggested_bullets(response, request)
    _remove_present_missing_keywords(response, request)
    _remove_generic_feedback(response)
    _normalize_missing_jd_fit(response, request)
    _enforce_feedback_language(response, request)
    _enforce_rewrite_language(response, request)
    _normalize_disclaimer(response, request)
    _remove_noop_rewrites(response, request)
    response.rewrites = [_rewrite_grounded(r, request) for r in response.rewrites]
    response.overall_score = clamp_score(response.overall_score)
    return response


def parse_analyze_response(data: dict, request: AnalyzeCvRequest) -> AnalyzeCvResponse:
    normalized = dict(data)
    normalized.setdefault("confidence", 0.65)
    normalized.setdefault("company_model_feedback", "")
    normalized.setdefault("disclaimer", "AI-assisted feedback only; not a hiring guarantee.")
    try:
        parsed = AnalyzeCvResponse.model_validate(normalized)
    except ValidationError as exc:
        logger.warning("Invalid LLM JSON: %s", exc)
        raise
    return apply_rule_overlay(parsed, request)
