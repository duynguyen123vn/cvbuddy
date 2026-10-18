from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.errors import LLMQuotaError, LLMUpstreamError

logger = logging.getLogger(__name__)

_HTTP_ERRORS = {
    400: ("invalid_request", "The request is invalid."),
    401: ("authentication_required", "Authentication is required."),
    403: ("forbidden", "The request is not allowed."),
    404: ("not_found", "The requested resource was not found."),
    413: ("payload_too_large", "The uploaded file is too large."),
    422: ("validation_error", "The request could not be validated."),
    429: ("rate_limited", "The service is temporarily rate limited."),
    502: ("provider_unavailable", "The AI provider is temporarily unavailable."),
    503: ("service_unavailable", "The service is temporarily unavailable."),
    500: ("internal_error", "The request could not be completed."),
}


def _error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    response = JSONResponse(
        status_code=status,
        content={
            "detail": message,
            "error": {"code": code, "message": message, "requestId": request_id},
        },
        headers={"X-Request-ID": request_id} if request_id else None,
    )
    return response


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            request, 422, "validation_error", "The request could not be validated."
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code if exc.status_code in _HTTP_ERRORS else 500
        code, message = _HTTP_ERRORS.get(status, ("internal_error", "The request could not be completed."))
        response = _error_response(request, status, code, message)
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            response.headers["Retry-After"] = retry_after
        return response

    @app.exception_handler(LLMQuotaError)
    async def handle_quota_error(request: Request, exc: LLMQuotaError) -> JSONResponse:
        response = _error_response(request, 429, "provider_rate_limited", "The AI provider is temporarily rate limited.")
        if exc.retry_after_seconds is not None:
            response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(LLMUpstreamError)
    async def handle_provider_error(request: Request, exc: LLMUpstreamError) -> JSONResponse:
        logger.warning(
            "AI provider request failed: request_id=%s upstream_status=%s",
            getattr(request.state, "request_id", ""),
            exc.status_code,
        )
        return _error_response(
            request, 502, "provider_unavailable", "The AI provider is temporarily unavailable."
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled API error: request_id=%s exception_type=%s",
            getattr(request.state, "request_id", ""),
            type(exc).__name__,
        )
        return _error_response(
            request, 500, "internal_error", "The request could not be completed."
        )
