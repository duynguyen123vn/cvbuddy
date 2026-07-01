from fastapi import APIRouter, HTTPException

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
    try:
        return await run_portfolio_suggest(body)
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


@router.post("/from-image", response_model=PortfolioSuggestResponse)
async def suggest_portfolio_from_image(
    body: PortfolioFromImageRequest,
) -> PortfolioSuggestResponse:
    try:
        return await run_portfolio_from_image(body)
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
