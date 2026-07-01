from fastapi import APIRouter
import httpx

from app.core.config import settings
from app.schemas.cv import LlmModel

router = APIRouter(prefix="/models")

MODEL_LABELS = {
    LlmModel.LLAMA_3_3_70B: "Llama 3.3 70B",
    LlmModel.QWEN_3_6_27B: "Qwen 3.6 27B",
    LlmModel.QWEN_3_32B: "Qwen 3 32B",
    LlmModel.LLAMA_4_SCOUT: "Llama 4 Scout",
}

LOCAL_MODEL_LABELS = {
    LlmModel.QWEN3_8B_LOCAL: "Qwen 3 8B (Local)",
    LlmModel.QWEN3_5_4B_LOCAL: "Qwen 3.5 4B (Local)",
    LlmModel.QWEN3_5_9B_LOCAL: "Qwen 3.5 9B (Local)",
    LlmModel.LLAMA3_1_8B_LOCAL: "Llama 3.1 8B (Local)",
    LlmModel.GEMMA3_4B_LOCAL: "Gemma 3 4B (Local)",
}


@router.get("")
async def list_models() -> dict:
    if settings.llm_provider == "ollama":
        server_available = False
        installed_names: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(
                    f"{settings.ollama_base_url.rstrip('/')}/api/tags"
                )
            if response.status_code == 200:
                server_available = True
                installed_names = {
                    str(model.get("name", ""))
                    for model in response.json().get("models", [])
                }
        except httpx.HTTPError:
            pass

        models = [
            {
                "id": model.value,
                "display_name": display_name,
                "installed": model.value in installed_names,
            }
            for model, display_name in LOCAL_MODEL_LABELS.items()
        ]
        for installed_name in sorted(installed_names):
            if installed_name and installed_name not in {model["id"] for model in models}:
                models.append(
                    {
                        "id": installed_name,
                        "display_name": f"{installed_name} (Local)",
                        "installed": True,
                    }
                )
        return {
            "provider": "ollama",
            "default_model": settings.ollama_analyze_model,
            "default_extract_model": settings.ollama_extract_model,
            "default_analyze_model": settings.ollama_analyze_model,
            "server_available": server_available,
            "models": models,
        }

    return {
        "provider": settings.llm_provider,
        "default_model": settings.groq_analyze_model,
        "default_extract_model": settings.groq_extract_model,
        "default_analyze_model": settings.groq_analyze_model,
        "server_available": True,
        "models": [
            {"id": model.value, "display_name": display_name}
            for model, display_name in MODEL_LABELS.items()
        ],
    }
