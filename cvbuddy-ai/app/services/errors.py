from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMQuotaError(Exception):
    message: str
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class LLMUpstreamError(Exception):
    status_code: int | None
    message: str
