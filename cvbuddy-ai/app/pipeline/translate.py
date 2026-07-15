from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services.llm import LLMService, get_llm_service
from app.services.mock_llm import mock_translate


async def run_translate(
    request: TranslateRequest,
    *,
    llm_service: LLMService | None = None,
) -> TranslateResponse:
    service = llm_service or get_llm_service()
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
    return TranslateResponse(
        translated=raw.get("translated", ""),
        notes=raw.get("notes", []),
        meta={"source": getattr(service, "provider_name", "groq")},
    )
