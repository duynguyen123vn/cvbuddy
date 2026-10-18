from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.response_metadata import attach_provider_metadata
from app.pipeline.translate import run_translate
from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services.errors import LLMQuotaError, LLMUpstreamError


router = APIRouter(prefix="/translate")


@router.post("", response_model=TranslateResponse)
async def translate_text(body: TranslateRequest) -> TranslateResponse:
    started = perf_counter()
    try:
        result = await run_translate(body)
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
        raise HTTPException(status_code=429, detail="LLM quota exceeded. Please retry later.", headers=headers) from exc
    except LLMUpstreamError as exc:
        raise HTTPException(status_code=502, detail="AI provider unavailable.") from exc
