from app.schemas.portfolio import (
    PortfolioFromImageRequest,
    PortfolioSuggestRequest,
    PortfolioSuggestResponse,
)
from app.services.llm import LLMService, ensure_mock_allowed, get_llm_service
from app.services.mock_llm import mock_portfolio_suggest
from app.services.errors import LLMUpstreamError


async def run_portfolio_suggest(
    request: PortfolioSuggestRequest,
    *,
    llm_service: LLMService | None = None,
) -> PortfolioSuggestResponse:
    service = llm_service or get_llm_service()
    ensure_mock_allowed(service)
    if service.use_mock:
        return mock_portfolio_suggest(request)

    import json

    from app.pipeline.context_matrix import ContextMatrixBuilder

    builder = ContextMatrixBuilder()
    industry = builder.load_industry(request.industry_slug)

    system = (
        "Generate portfolio/CV bullets from user activity text. "
        "Do not invent facts beyond the activity description. "
        "Return JSON with: activity_summary_vi, activity_summary_en, "
        "suggested_cv_bullet_vi, suggested_cv_bullet_en, action_verbs, "
        "industry_keywords, confidence."
    )
    payload = {
        "activity_text": request.activity_text,
        "caption": request.optional_caption,
        "industry": industry,
        "vertical_slug": request.vertical_slug,
    }
    raw = await service.generate_json(
        system_instruction=system,
        user_message=json.dumps(payload, ensure_ascii=False),
    )
    required_text_fields = (
        "activity_summary_vi", "activity_summary_en",
        "suggested_cv_bullet_vi", "suggested_cv_bullet_en",
    )
    if any(not isinstance(raw.get(field), str) for field in required_text_fields):
        raise LLMUpstreamError(
            status_code=502,
            message="Provider output did not match the portfolio schema",
            code="unsupported_schema",
        )
    return PortfolioSuggestResponse(
        activity_summary_vi=raw.get("activity_summary_vi", ""),
        activity_summary_en=raw.get("activity_summary_en", ""),
        suggested_cv_bullet_vi=raw.get("suggested_cv_bullet_vi", ""),
        suggested_cv_bullet_en=raw.get("suggested_cv_bullet_en", ""),
        action_verbs=raw.get("action_verbs", []),
        industry_keywords=raw.get("industry_keywords", []),
        confidence=float(raw.get("confidence", 0.7)),
        meta={
            "source": getattr(service, "provider_name", "groq"),
            "model": getattr(service, "model_name", "unknown"),
        },
    )


async def run_portfolio_from_image(
    request: PortfolioFromImageRequest,
    *,
    llm_service: LLMService | None = None,
) -> PortfolioSuggestResponse:
    """Generate portfolio copy from an uploaded image URL plus optional context.

    This keeps the public contract aligned with the product spec while avoiding
    fake vision inference when the configured LLM client is text-only.
    """

    caption = (request.optional_caption or "").strip()
    if not caption:
        return PortfolioSuggestResponse(
            activity_summary_vi=(
                "Can them mo ta hoat dong de bien anh nay thanh noi dung CV dang tin cay."
            ),
            activity_summary_en=(
                "More activity context is needed before turning this image into reliable CV content."
            ),
            suggested_cv_bullet_vi="",
            suggested_cv_bullet_en="",
            action_verbs=[],
            industry_keywords=[],
            confidence=0.2,
            meta={
                "source": "local",
                "image_url_received": "true",
                "needs_user_confirmation": "true",
            },
        )

    response = await run_portfolio_suggest(
        PortfolioSuggestRequest(
            activity_text=caption,
            industry_slug=request.industry_slug,
            vertical_slug=request.vertical_slug,
            optional_caption=caption,
            tier=request.tier,
        ),
        llm_service=llm_service,
    )
    response.meta = response.meta.model_copy(
        update={
            "image_url_received": "true",
            "vision_mode": "caption_context",
            "needs_user_confirmation": "true",
        }
    )
    response.confidence = min(response.confidence, 0.85)
    return response
