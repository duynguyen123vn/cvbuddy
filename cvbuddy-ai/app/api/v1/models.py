from fastapi import APIRouter

from app.core.config import settings
from app.schemas.cv import LlmModel

router = APIRouter(prefix="/models")

MODEL_LABELS = {
    LlmModel.QWEN_3_8_27B: "Qwen 3.8 27B",
    LlmModel.GPT_OSS_120B: "GPT OSS 120B",
}


@router.get("")
async def list_models() -> dict:
    return {
        "provider": "groq",
        "default_model": settings.groq_analyze_model,
        "default_extract_model": settings.groq_extract_model,
        "default_analyze_model": settings.groq_analyze_model,
        "server_available": True,
        "models": [
            {"id": model.value, "display_name": display_name}
            for model, display_name in MODEL_LABELS.items()
        ],
    }
