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
    code: str = "provider_unavailable"


class MockProhibitedError(Exception):
    """Raised if mock inference is attempted while production is active."""
