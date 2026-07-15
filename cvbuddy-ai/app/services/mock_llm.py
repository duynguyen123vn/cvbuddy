"""Deterministic mock responses for web/FE integration without API key."""

from app.schemas.cv import (
    AnalyzeCvRequest,
    AnalyzeCvResponse,
    CvDimensions,
    CvRewrite,
    DimensionScore,
    JdFitDimension,
    KeywordsDimension,
)
from app.schemas.portfolio import PortfolioSuggestRequest, PortfolioSuggestResponse
from app.schemas.translate import TranslateRequest, TranslateResponse


def mock_analyze_cv(request: AnalyzeCvRequest) -> dict:
    return AnalyzeCvResponse(
        overall_score=68,
        dimensions=CvDimensions(
            layout_ats=DimensionScore(
                score=70,
                issues=["Experience section could use clearer date formatting for ATS."],
                fixes=["Use MM/YYYY – MM/YYYY on one line per role."],
            ),
            language=DimensionScore(
                score=65,
                issues=["Some bullets use weak openings (Responsible for)."],
                fixes=["Start bullets with action verbs: Coordinated, Supported, Delivered."],
            ),
            keywords=KeywordsDimension(
                score=55,
                missing=["KPI", "stakeholder"],
                suggested_bullets=[],
            ),
            jd_fit=JdFitDimension(
                score=60 if request.jd_extract else 50,
                gaps=["Add JD keywords in experience bullets if you have done related work."],
            ),
        ),
        rewrites=[
            CvRewrite(
                section="experience",
                original_ref=request.sections.experience[0] if request.sections.experience else "N/A",
                suggested_vi="[Mock] Viết lại bullet với động từ mạnh và số liệu nếu có.",
                suggested_en="[Mock] Rewrite bullet with a strong verb and metrics if available.",
                needs_user_fact=False,
            )
        ],
        company_model_feedback=f"Mock feedback for company_model={request.company_model.value}.",
        confidence=0.75,
        meta={"source": "mock"},
    ).model_dump()


def mock_translate(request: TranslateRequest) -> TranslateResponse:
    prefix = "[CV-native mock] " if request.mode.value == "cv_native" else "[Literal mock] "
    return TranslateResponse(
        translated=prefix + request.text,
        notes=["Set LLM_PROVIDER=groq and configure GROQ_API_KEY for real translation."],
        meta={"source": "mock"},
    )


def mock_portfolio_suggest(request: PortfolioSuggestRequest) -> PortfolioSuggestResponse:
    return PortfolioSuggestResponse(
        activity_summary_vi=f"[Mock] Tóm tắt: {request.activity_text[:120]}...",
        activity_summary_en=f"[Mock] Summary: {request.activity_text[:120]}...",
        suggested_cv_bullet_vi="[Mock] Hỗ trợ [hoạt động] cho [đối tượng], góp phần [kết quả nếu có số liệu].",
        suggested_cv_bullet_en="[Mock] Supported [activity] for [audience], contributing to [outcome if quantified].",
        action_verbs=["Coordinated", "Supported", "Facilitated"],
        industry_keywords=["teamwork", "communication"],
        confidence=0.7,
        meta={"source": "mock"},
    )
