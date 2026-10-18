from __future__ import annotations

import hmac
import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings


class ProductionGateMiddleware:
    def __init__(self, app: ASGIApp, config: Settings) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _header_value(scope, b"x-request-id")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
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
                bool(self.config.ai_internal_key)
                and bool(supplied_key)
                and hmac.compare_digest(supplied_key, self.config.ai_internal_key.strip())
            )
        )

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [(key, value) for key, value in headers if key.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode("ascii", errors="ignore")))
                message["headers"] = headers
            await send(message)

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

        await self.app(scope, receive, send_with_request_id)


def _header_value(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1").strip()
    return ""
