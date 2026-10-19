from time import perf_counter

from fastapi import APIRouter

from app.core.config import settings
from app.core.response_metadata import attach_provider_metadata
from app.pipeline.translate import run_translate
from app.schemas.translate import TranslateRequest, TranslateResponse


router = APIRouter(prefix="/translate")


@router.post("", response_model=TranslateResponse)
async def translate_text(body: TranslateRequest) -> TranslateResponse:
    started = perf_counter()
    result = await run_translate(body)
    provider = "mock" if settings.use_mock_llm else "groq"
    actual_model = result.meta.get("model", settings.groq_model) if isinstance(result.meta, dict) else settings.groq_model
    return attach_provider_metadata(
        result,
        provider=provider,
        model="mock" if provider == "mock" else actual_model,
        source=provider,
        latency_ms=(perf_counter() - started) * 1000,
    )
