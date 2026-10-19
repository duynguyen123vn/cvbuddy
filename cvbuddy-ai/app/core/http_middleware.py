from __future__ import annotations

import hmac
import hashlib
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from math import ceil

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.request_context import request_id_context


logger = logging.getLogger(__name__)


class ProductionGateMiddleware:
    def __init__(self, app: ASGIApp, config: Settings) -> None:
        self.app = app
        self.config = config
        self._request_windows: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _header_value(scope, b"x-request-id")
        if not re.fullmatch(r"[A-Za-z0-9_:-]{1,64}", request_id):
            request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        path = scope.get("path", "")
        is_versioned_api = path.startswith("/v1/") or path == "/v1"
        supplied_key = _header_value(scope, b"x-ai-internal-key")
        authorized = (
            not self.config.is_production
            or not is_versioned_api
            or scope.get("method") == "OPTIONS"
            or (
                bool(self.config.ai_internal_api_key)
                and bool(supplied_key)
                and hmac.compare_digest(supplied_key, self.config.ai_internal_api_key.strip())
            )
        )
        rate_limited = False
        retry_after = 0
        if authorized and self.config.is_production and is_versioned_api and scope.get("method") != "OPTIONS":
            key_fingerprint = hashlib.sha256(supplied_key.encode()).hexdigest()
            now = time.monotonic()
            window = self._request_windows[key_fingerprint]
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= self.config.ai_rate_limit_per_minute:
                rate_limited = True
                retry_after = max(1, ceil(60 - (now - window[0])))
            else:
                window.append(now)
        started = time.perf_counter()
        context_token = request_id_context.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [(key, value) for key, value in headers if key.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode("ascii", errors="ignore")))
                message["headers"] = headers
                logger.info(
                    "request completed",
                    extra={
                        "event": "http_request",
                        "request_id": request_id,
                        "method": scope.get("method", ""),
                        "path": path,
                        "status_code": message.get("status"),
                        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                )
            await send(message)

        try:
            if not authorized:
                import json

                payload = json.dumps(
                    {
                        "detail": "Authentication required.",
                        "error": {
                            "code": "authentication_required",
                            "message": "Authentication required.",
                            "requestId": request_id,
                        },
                    }
                ).encode()
                await send_with_request_id(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send_with_request_id(
                    {"type": "http.response.body", "body": payload, "more_body": False}
                )
                return

            if rate_limited:
                import json

                message = "Request rate limit exceeded."
                payload = json.dumps(
                    {
                        "detail": message,
                        "error": {
                            "code": "request_rate_limited",
                            "message": message,
                            "requestId": request_id,
                        },
                    }
                ).encode()
                await send_with_request_id(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"retry-after", str(retry_after).encode("ascii")),
                        ],
                    }
                )
                await send_with_request_id(
                    {"type": "http.response.body", "body": payload, "more_body": False}
                )
                return

            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_context.reset(context_token)


def _header_value(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1").strip()
    return ""
