from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.schemas.cv import ProviderMetadata


def attach_provider_metadata(
    response: Any,
    *,
    provider: str,
    model: str,
    latency_ms: float,
    source: str | None = None,
) -> Any:
    is_mapping = isinstance(response, dict)
    current = response.get("meta") if is_mapping else getattr(response, "meta", None)
    values = current.model_dump() if isinstance(current, ProviderMetadata) else dict(current or {})
    known = {"source", "provider", "model", "schemaVersion", "promptVersion", "latencyMs"}
    extras = {key: value for key, value in values.items() if key not in known}
    metadata = ProviderMetadata(
        source=source or values.get("source") or provider,
        provider=provider,
        model=model,
        schemaVersion=settings.ai_schema_version,
        promptVersion=settings.ai_prompt_version,
        latencyMs=round(max(latency_ms, 0.0), 2),
        **extras,
    )
    if is_mapping:
        response["meta"] = metadata.model_dump()
    else:
        response.meta = metadata
    return response
