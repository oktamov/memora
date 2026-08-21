"""Pending bot lookups, held in Redis between the reply and the save (SPEC §9a).

A chat message carries no state, and Telegram caps callback data at 64 bytes, so the
lookup result and the user's current selection live under a short token. They expire
on their own — an abandoned lookup should not linger.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.providers.base import LookupResult

logger = get_logger(__name__)

PENDING_TTL_SECONDS = 60 * 60  # an hour is far longer than anyone deliberates


@dataclass(slots=True)
class PendingLookup:
    token: str
    user_id: str
    result: LookupResult
    selected: set[int] = field(default_factory=set)

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "result": self.result.to_dict(),
                "selected": sorted(self.selected),
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, token: str, raw: str) -> PendingLookup:
        payload: dict[str, Any] = json.loads(raw)
        return cls(
            token=token,
            user_id=payload["user_id"],
            result=LookupResult.from_dict(payload["result"]),
            selected=set(payload.get("selected", [])),
        )


def _key(token: str) -> str:
    return f"bot:pending:{token}"


def new_token() -> str:
    """Short enough to leave room in the 64-byte callback payload."""
    return secrets.token_urlsafe(8)


async def save(redis: Redis, pending: PendingLookup) -> None:
    try:
        await redis.set(_key(pending.token), pending.to_json(), ex=PENDING_TTL_SECONDS)
    except Exception as exc:
        logger.warning(
            "pending_save_failed", extra={"event": "pending_save_failed", "error": str(exc)}
        )


async def load(redis: Redis, token: str) -> PendingLookup | None:
    try:
        raw = await redis.get(_key(token))
    except Exception as exc:
        logger.warning(
            "pending_load_failed", extra={"event": "pending_load_failed", "error": str(exc)}
        )
        return None

    if not raw:
        return None
    try:
        return PendingLookup.from_json(token, raw)
    except (ValueError, KeyError):
        return None


async def drop(redis: Redis, token: str) -> None:
    try:
        await redis.delete(_key(token))
    except Exception as exc:
        logger.warning(
            "pending_drop_failed", extra={"event": "pending_drop_failed", "error": str(exc)}
        )
