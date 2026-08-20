"""Structured JSON logging (SPEC §12).

Provider calls are logged with name, latency, cache status and whether the call
counted against quota. Lookup payloads are never logged.
"""

import logging
import sys
from typing import Any

from pythonjsonlogger import jsonlogger

from app.core.config import settings

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())

    for noisy in ("uvicorn.access", "uvicorn.error", "aiogram.event"):
        logging.getLogger(noisy).handlers = [handler]
        logging.getLogger(noisy).propagate = False

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_provider_call(
    logger: logging.Logger,
    *,
    provider: str,
    term_length: int,
    source_lang: str,
    target_lang: str,
    latency_ms: float,
    cache: str,
    counted_against_quota: bool,
    ok: bool,
    error: str | None = None,
) -> None:
    """One structured line per provider call. `term_length`, never the term itself."""
    extra: dict[str, Any] = {
        "event": "provider_call",
        "provider": provider,
        "term_length": term_length,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "latency_ms": round(latency_ms, 2),
        "cache": cache,
        "counted_against_quota": counted_against_quota,
        "ok": ok,
    }
    if error:
        extra["error"] = error
    logger.info("provider_call", extra=extra)
