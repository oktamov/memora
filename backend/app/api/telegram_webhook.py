"""`POST /telegram/webhook/{secret}` (SPEC §7).

Two independent checks, both before the body is parsed: the random path segment and
the `X-Telegram-Bot-Api-Secret-Token` header. Anything else is 403.
"""

from __future__ import annotations

import hmac
from typing import Any

from aiogram.types import Update
from fastapi import APIRouter, Request, Response, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook/{secret}", include_in_schema=False)
async def telegram_webhook(secret: str, request: Request) -> Response:
    # Constant-time on both, and rejected before `await request.json()`.
    if not hmac.compare_digest(secret, settings.TELEGRAM_WEBHOOK_PATH_SECRET):
        return _forbidden("path")

    expected_header = settings.TELEGRAM_WEBHOOK_SECRET
    if expected_header:
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(provided, expected_header):
            return _forbidden("header")

    bot = getattr(request.app.state, "bot", None)
    dispatcher = getattr(request.app.state, "dispatcher", None)
    if bot is None or dispatcher is None:
        # No token configured: the bot is not mounted (BLOCKERS.md B1).
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    payload: dict[str, Any] = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})

    # Telegram retries anything that is not answered quickly, so the handler runs
    # inline and the response is the acknowledgement.
    await dispatcher.feed_update(bot, update)
    return Response(status_code=status.HTTP_200_OK)


def _forbidden(which: str) -> Response:
    logger.warning(
        "webhook_rejected", extra={"event": "webhook_rejected", "reason": f"bad {which} secret"}
    )
    return Response(status_code=status.HTTP_403_FORBIDDEN)
