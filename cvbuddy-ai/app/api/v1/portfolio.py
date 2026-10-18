from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.response_metadata import attach_provider_metadata
from app.pipeline.portfolio import run_portfolio_from_image, run_portfolio_suggest
from app.schemas.portfolio import (
    PortfolioFromImageRequest,
    PortfolioSuggestRequest,
    PortfolioSuggestResponse,
)
from app.services.errors import LLMQuotaError, LLMUpstreamError

router = APIRouter(prefix="/portfolio")


@router.post("/suggest", response_model=PortfolioSuggestResponse)
async def suggest_portfolio(body: PortfolioSuggestRequest) -> PortfolioSuggestResponse:
    started = perf_counter()
    try:
        result = await run_portfolio_suggest(body)
        provider = "mock" if settings.use_mock_llm else "groq"
        return attach_provider_metadata(
            result,
            provider=provider,
            model="mock" if provider == "mock" else settings.groq_model,
            latency_ms=(perf_counter() - started) * 1000,
        )
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
        raise HTTPException(status_code=502, detail="AI provider unavailable.") from exc


@router.post("/from-image", response_model=PortfolioSuggestResponse)
async def suggest_portfolio_from_image(
    body: PortfolioFromImageRequest,
) -> PortfolioSuggestResponse:
    started = perf_counter()
    try:
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
            model=(
                "local"
                if provider == "local"
                else "mock"
                if provider == "mock"
                else settings.groq_model
            ),
            latency_ms=(perf_counter() - started) * 1000,
            source=source,
        )
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
        raise HTTPException(status_code=502, detail="AI provider unavailable.") from exc
