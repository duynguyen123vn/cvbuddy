from time import perf_counter

from fastapi import APIRouter

from app.core.config import settings
from app.core.response_metadata import attach_provider_metadata
from app.pipeline.portfolio import run_portfolio_from_image, run_portfolio_suggest
from app.schemas.portfolio import (
    PortfolioFromImageRequest,
    PortfolioSuggestRequest,
    PortfolioSuggestResponse,
)

router = APIRouter(prefix="/portfolio")


@router.post("/suggest", response_model=PortfolioSuggestResponse)
async def suggest_portfolio(body: PortfolioSuggestRequest) -> PortfolioSuggestResponse:
    started = perf_counter()
    result = await run_portfolio_suggest(body)
    provider = "mock" if settings.use_mock_llm else "groq"
    actual_model = result.meta.get("model", settings.groq_model) if isinstance(result.meta, dict) else settings.groq_model
    return attach_provider_metadata(
        result,
        provider=provider,
        model="mock" if provider == "mock" else actual_model,
        source=provider,
        latency_ms=(perf_counter() - started) * 1000,
    )


@router.post("/from-image", response_model=PortfolioSuggestResponse)
async def suggest_portfolio_from_image(
    body: PortfolioFromImageRequest,
) -> PortfolioSuggestResponse:
    started = perf_counter()
    result = await run_portfolio_from_image(body)
    current = result.meta
    source = current.source
    provider = (
        source
        if source in {"local", "mock"}
        else "mock"
        if settings.use_mock_llm
        else "groq"
    )
    return attach_provider_metadata(
        result,
        provider=provider,
        model=("local" if provider == "local" else "mock" if provider == "mock" else current.model),
        latency_ms=(perf_counter() - started) * 1000,
        source=source,
    )
