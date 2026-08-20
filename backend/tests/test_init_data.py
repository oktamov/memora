"""M1 acceptance: a tampered initData hash is rejected, a valid one is accepted.

Every case runs against a fixture signed with a dummy token — never a live bot
(SPEC §11 M1, AGENT.md §3).
"""

import json
import time
from urllib.parse import parse_qsl, urlencode

import pytest

from app.core.errors import UnauthorizedError
from app.telegram.init_data import validate_init_data
from tests.factories import DUMMY_BOT_TOKEN, make_init_data, sign_init_data


def test_valid_init_data_is_accepted() -> None:
    raw = make_init_data(telegram_id=42, username="aziz", language_code="uz")

    result = validate_init_data(raw, DUMMY_BOT_TOKEN)

    assert result.user.telegram_id == 42
    assert result.user.username == "aziz"
    assert result.user.language_code == "uz"


def test_start_param_is_exposed_for_deep_links() -> None:
    raw = make_init_data(start_param="review")

    assert validate_init_data(raw, DUMMY_BOT_TOKEN).start_param == "review"


def test_tampered_hash_is_rejected() -> None:
    fields = dict(parse_qsl(make_init_data(), keep_blank_values=True))
    original = fields["hash"]
    # Flip one hex digit — the smallest possible forgery.
    fields["hash"] = ("1" if original[0] != "1" else "2") + original[1:]

    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(urlencode(fields), DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_bad_hash"


def test_tampered_user_id_with_the_original_hash_is_rejected() -> None:
    """The realistic attack: keep a real signature, swap in someone else's id."""
    fields = dict(parse_qsl(make_init_data(telegram_id=42), keep_blank_values=True))
    user = json.loads(fields["user"])
    user["id"] = 999_999_999
    fields["user"] = json.dumps(user, separators=(",", ":"))

    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(urlencode(fields), DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_bad_hash"


def test_payload_signed_with_a_different_bot_token_is_rejected() -> None:
    raw = make_init_data(bot_token="999999:AAsome-other-bots-token")

    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(raw, DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_bad_hash"


def test_init_data_older_than_24_hours_is_rejected() -> None:
    stale = int(time.time()) - 86_400 - 60
    raw = make_init_data(auth_date=stale)

    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(raw, DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_expired"


def test_init_data_just_inside_the_window_is_accepted() -> None:
    fresh_enough = int(time.time()) - 86_400 + 60
    raw = make_init_data(auth_date=fresh_enough)

    assert validate_init_data(raw, DUMMY_BOT_TOKEN).auth_date == fresh_enough


def test_missing_hash_is_rejected() -> None:
    fields = dict(parse_qsl(make_init_data(), keep_blank_values=True))
    del fields["hash"]

    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(urlencode(fields), DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_no_hash"


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data("", DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_missing"


def test_missing_user_is_rejected_even_when_correctly_signed() -> None:
    raw = sign_init_data({"auth_date": str(int(time.time())), "query_id": "x"})

    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(raw, DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_no_user"


def test_missing_auth_date_is_rejected_even_when_correctly_signed() -> None:
    raw = sign_init_data({"user": json.dumps({"id": 1}), "query_id": "x"})

    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(raw, DUMMY_BOT_TOKEN)

    assert exc.value.code == "init_data_no_auth_date"


def test_unconfigured_bot_token_refuses_to_validate_anything() -> None:
    with pytest.raises(UnauthorizedError) as exc:
        validate_init_data(make_init_data(), "")

    assert exc.value.code == "bot_not_configured"


def test_blank_valued_fields_are_kept_in_the_data_check_string() -> None:
    """`parse_qsl` dropping blanks would silently break real Telegram payloads."""
    raw = sign_init_data(
        {"auth_date": str(int(time.time())), "user": json.dumps({"id": 7}), "start_param": ""}
    )

    assert validate_init_data(raw, DUMMY_BOT_TOKEN).user.telegram_id == 7
