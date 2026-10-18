from __future__ import annotations

from app.core.config import settings


def build_provider_metadata(
    *,
    provider: str,
    model: str,
    latency_ms: float,
    source: str | None = None,
    **extra: object,
) -> dict[str, object]:
    return {
        "source": source or provider,
        "provider": provider,
        "model": model,
        "schemaVersion": settings.ai_schema_version,
        "promptVersion": settings.ai_prompt_version,
        "latencyMs": round(max(latency_ms, 0.0), 2),
        **extra,
    }
