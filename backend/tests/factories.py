"""Test fixtures.

`AGENT.md` §3: real Telegram initData cannot be obtained here, so we sign payloads
with a dummy bot token using the exact algorithm from SPEC §7. Tests then exercise
both a valid and a tampered payload, which covers §7 without a live bot.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

DUMMY_BOT_TOKEN = "123456:AAdummy-bot-token-for-tests-only"


def sign_init_data(fields: dict[str, str], bot_token: str = DUMMY_BOT_TOKEN) -> str:
    """Produce a correctly signed initData query string for `fields`."""
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def make_init_data(
    *,
    telegram_id: int = 777_000_111,
    username: str | None = "reader",
    first_name: str | None = "Aziz",
    language_code: str | None = "uz",
    auth_date: int | None = None,
    start_param: str | None = None,
    signature: str | None = None,
    bot_token: str = DUMMY_BOT_TOKEN,
) -> str:
    """A valid, freshly signed initData string."""
    user: dict[str, object] = {"id": telegram_id, "first_name": first_name}
    if username is not None:
        user["username"] = username
    if language_code is not None:
        user["language_code"] = language_code

    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAF-test-query-id",
        "user": json.dumps(user, separators=(",", ":")),
    }
    if start_param is not None:
        fields["start_param"] = start_param
    if signature is not None:
        # Newer Telegram clients send this alongside `hash`. It stays *inside* the
        # data-check string for the bot's HMAC (see tests/test_init_data.py).
        fields["signature"] = signature
    return sign_init_data(fields, bot_token)
