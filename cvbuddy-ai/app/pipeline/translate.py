from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services.llm import LLMService, ensure_mock_allowed, get_llm_service
from app.services.errors import LLMUpstreamError
from app.services.mock_llm import mock_translate


async def run_translate(
    request: TranslateRequest,
    *,
    llm_service: LLMService | None = None,
) -> TranslateResponse:
    service = llm_service or get_llm_service()
    ensure_mock_allowed(service)
    if service.use_mock:
        return mock_translate(request)

    system = (
        "You translate Vietnamese to English for CVs. "
        "Mode cv_native: strong action verbs, concise, no word-for-word translation. "
        "Return JSON: {\"translated\": \"...\", \"notes\": [\"...\"]}"
    )
    import json

    raw = await service.generate_json(
        system_instruction=system,
        user_message=json.dumps(
            {"text": request.text, "mode": request.mode.value},
            ensure_ascii=False,
        ),
    )
    if not isinstance(raw.get("translated"), str) or not isinstance(raw.get("notes", []), list):
        raise LLMUpstreamError(
            status_code=502,
            message="Provider output did not match the translation schema",
            code="unsupported_schema",
        )
    return TranslateResponse(
        translated=raw.get("translated", ""),
        notes=raw.get("notes", []),
        meta={
            "source": getattr(service, "provider_name", "groq"),
            "model": getattr(service, "model_name", "unknown"),
        },
    )
