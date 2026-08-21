"""Quota arithmetic (SPEC §8.2, §8.5) — the parts that depend on the clock and
the user's own timezone."""

from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.models.user import User
from app.services import quota_service


def _user(**overrides: object) -> User:
    user = User(
        telegram_id=1,
        timezone="Asia/Tashkent",
        lookup_quota_per_day=100,
        created_at=datetime.now(UTC) - timedelta(days=30),
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def test_an_established_account_gets_its_full_quota() -> None:
    assert quota_service.effective_quota(_user()) == 100


def test_an_account_younger_than_24h_is_capped() -> None:
    fresh = _user(created_at=datetime.now(UTC) - timedelta(hours=1))

    assert quota_service.effective_quota(fresh) == settings.NEW_ACCOUNT_LOOKUP_QUOTA


def test_a_low_personal_limit_still_wins_over_the_new_account_cap() -> None:
    stingy = _user(lookup_quota_per_day=5, created_at=datetime.now(UTC) - timedelta(minutes=5))

    assert quota_service.effective_quota(stingy) == 5


def test_the_quota_key_expires_at_the_users_local_midnight() -> None:
    """23:00 in Tashkent is 18:00 UTC; one hour of quota is left, not six."""
    user = _user(timezone="Asia/Tashkent")
    at_2300_local = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)

    seconds = quota_service.seconds_until_local_midnight(user, now=at_2300_local)

    assert 3500 < seconds <= 3600


def test_the_quota_key_is_named_for_the_users_local_day() -> None:
    user = _user(timezone="Asia/Tashkent")
    # 20:00 UTC on 10 May is already 01:00 on 11 May in Tashkent.
    key = quota_service.quota_key(user, now=datetime(2026, 5, 10, 20, 0, tzinfo=UTC))

    assert key.endswith("2026-05-11")


def test_a_broken_timezone_falls_back_to_utc_instead_of_raising() -> None:
    user = _user(timezone="Not/AZone")

    assert quota_service.seconds_until_local_midnight(user) > 0
