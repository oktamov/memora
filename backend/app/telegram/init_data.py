"""Telegram Mini App `initData` validation (SPEC §7).

This module is the entire basis of authentication. Anyone can POST any
`telegram_id`; only the HMAC below proves a payload came from Telegram. Nothing here
reads `initDataUnsafe`, and no caller may trust `parse_init_data` output without
having gone through `validate_init_data` first.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.core.errors import UnauthorizedError


@dataclass(frozen=True, slots=True)
class TelegramUser:
    """The `user` object, trusted only after the HMAC check passes."""

    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    is_premium: bool


@dataclass(frozen=True, slots=True)
class InitData:
    user: TelegramUser
    auth_date: int
    start_param: str | None
    raw: dict[str, str]


def _data_check_string(fields: dict[str, str]) -> str:
    """Step 2: remaining keys sorted alphabetically, joined `key=value` with `\\n`."""
    return "\n".join(f"{key}={fields[key]}" for key in sorted(fields))


def _expected_hash(data_check_string: str, bot_token: str) -> str:
    """Steps 3-4."""
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86_400,
    now: float | None = None,
) -> InitData:
    """Run the six steps of SPEC §7 in order. Raise `UnauthorizedError` on any failure.

    Args:
        init_data: the raw `window.Telegram.WebApp.initData` query string.
        bot_token: the bot token the Mini App was opened from.
        max_age_seconds: step 6 freshness window; 24 hours per spec.
        now: injectable clock, for tests.
    """
    if not bot_token:
        raise UnauthorizedError(
            "Telegram bot sozlanmagan.", code="bot_not_configured", status_code=503
        )
    if not init_data:
        raise UnauthorizedError("initData bo'sh.", code="init_data_missing")

    # Step 1: parse the raw query string, pull out `hash`, keep every other key.
    # `keep_blank_values` matters — dropping an empty field would change the
    # data-check string and break an otherwise valid signature.
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    if not pairs:
        raise UnauthorizedError("initData o'qib bo'lmadi.", code="init_data_malformed")

    fields = dict(pairs)
    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise UnauthorizedError("initData imzosi yo'q.", code="init_data_no_hash")

    # Nothing else is removed. SPEC §7 step 1 says "pull out `hash`, keep every other
    # key", and Telegram means it literally: newer clients also send `signature` (the
    # Ed25519 field used for *third-party* validation), and it is still part of the
    # data-check string for the bot's own HMAC. Excluding it produces a different
    # string and therefore a hash that never matches.

    # Steps 2-4.
    expected = _expected_hash(_data_check_string(fields), bot_token)

    # Step 5: constant-time comparison. Never `==`.
    if not hmac.compare_digest(expected, received_hash):
        raise UnauthorizedError("initData imzosi noto'g'ri.", code="init_data_bad_hash")

    # Step 6: freshness.
    auth_date = _parse_auth_date(fields)
    current = time.time() if now is None else now
    age = current - auth_date
    if age > max_age_seconds:
        raise UnauthorizedError(
            "initData eskirgan.",
            code="init_data_expired",
            details={"age_seconds": int(age), "max_age_seconds": max_age_seconds},
        )

    # Only now may `user` be trusted.
    return InitData(
        user=_parse_user(fields),
        auth_date=auth_date,
        start_param=fields.get("start_param"),
        raw=fields,
    )


def _parse_auth_date(fields: dict[str, str]) -> int:
    raw = fields.get("auth_date")
    if raw is None:
        raise UnauthorizedError("initData'da auth_date yo'q.", code="init_data_no_auth_date")
    try:
        return int(raw)
    except ValueError as exc:
        raise UnauthorizedError(
            "initData'dagi auth_date noto'g'ri.", code="init_data_bad_auth_date"
        ) from exc


def _parse_user(fields: dict[str, str]) -> TelegramUser:
    raw = fields.get("user")
    if not raw:
        raise UnauthorizedError("initData'da foydalanuvchi yo'q.", code="init_data_no_user")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UnauthorizedError(
            "initData'dagi foydalanuvchi o'qib bo'lmadi.", code="init_data_bad_user"
        ) from exc

    telegram_id = payload.get("id")
    if not isinstance(telegram_id, int):
        raise UnauthorizedError(
            "initData'dagi foydalanuvchi id noto'g'ri.", code="init_data_bad_user_id"
        )

    return TelegramUser(
        telegram_id=telegram_id,
        username=payload.get("username"),
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        language_code=payload.get("language_code"),
        is_premium=bool(payload.get("is_premium", False)),
    )
