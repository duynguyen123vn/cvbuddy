from fastapi import APIRouter

from app.pipeline.translate import run_translate
from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services.errors import LLMQuotaError, LLMUpstreamError
from fastapi import HTTPException

router = APIRouter(prefix="/translate")


@router.post("", response_model=TranslateResponse)
async def translate_text(body: TranslateRequest) -> TranslateResponse:
    try:
        return await run_translate(body)
    except LLMQuotaError as exc:
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        raise HTTPException(status_code=429, detail="LLM quota exceeded. Please retry later.", headers=headers) from exc
    except LLMUpstreamError as exc:
        status = exc.status_code or 502
        raise HTTPException(status_code=status, detail="LLM upstream error. See server logs.") from exc
