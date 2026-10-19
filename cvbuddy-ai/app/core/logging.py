import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.request_context import request_id_context


class SafeJsonFormatter(logging.Formatter):
    SAFE_FIELDS = (
        "event", "request_id", "method", "path", "status_code", "latency_ms",
        "error_code", "upstream_status", "model", "exception_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for field in self.SAFE_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(SafeJsonFormatter())
