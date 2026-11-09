from __future__ import annotations

class LLMQuotaError(Exception):
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class LLMUpstreamError(Exception):
    def __init__(
        self,
        status_code: int | None,
        message: str,
        code: str = "provider_unavailable",
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)


class MockProhibitedError(Exception):
    """Raised if mock inference is attempted while production is active."""
