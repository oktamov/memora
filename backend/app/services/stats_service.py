"""Statistics (SPEC §7).

Everything here reads `review_logs`, which is append-only and therefore the one honest
record of what the user actually did (SPEC §5).

Days are the *user's* local days throughout. A streak computed in UTC would break for
every user east of Greenwich the moment they review after their own midnight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import STATE_REVIEW, Card, CardState
from app.models.review import ReviewLog
from app.models.user import User
from app.srs.types import Rating

ACTIVITY_DAYS = 90


@dataclass(frozen=True, slots=True)
class DailyActivity:
    day: date
    reviews: int


@dataclass(frozen=True, slots=True)
class StatsOverview:
    streak_days: int = 0
    longest_streak_days: int = 0
    total_cards: int = 0
    cards_due_today: int = 0
    reviews_today: int = 0
    retention_rate: float | None = None
    reviews_per_day: list[DailyActivity] = field(default_factory=list)


def _zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


async def overview(
    session: AsyncSession, user: User, *, now: datetime | None = None
) -> StatsOverview:
    moment = now or datetime.now(UTC)
    zone = _zone(user)
    today = moment.astimezone(zone).date()

    activity = await _reviews_per_day(session, user, zone, today)
    by_day = {entry.day: entry.reviews for entry in activity}

    current, longest = _streaks(by_day, today)

    return StatsOverview(
        streak_days=current,
        longest_streak_days=longest,
        total_cards=await _total_cards(session, user),
        cards_due_today=await _due_now(session, user, moment),
        reviews_today=by_day.get(today, 0),
        retention_rate=await _retention(session, user),
        reviews_per_day=activity,
    )


async def _reviews_per_day(
    session: AsyncSession, user: User, zone: ZoneInfo, today: date
) -> list[DailyActivity]:
    """Every one of the last 90 local days, zeros included.

    The gaps matter as much as the activity — a heatmap with missing days would
    silently close them up and read as a longer streak than the user has.
    """
    first = today - timedelta(days=ACTIVITY_DAYS - 1)

    # Cast in Postgres using the user's zone so the day boundaries are theirs.
    local_day = cast(func.timezone(str(zone), ReviewLog.reviewed_at), Date).label("day")
    statement = (
        select(local_day, func.count(ReviewLog.id).label("reviews"))
        .where(ReviewLog.user_id == user.id)
        .group_by(local_day)
        .having(local_day >= first)
        .order_by(local_day)
    )

    counted = {row.day: int(row.reviews) for row in (await session.execute(statement)).all()}
    return [
        DailyActivity(
            day=first + timedelta(days=offset),
            reviews=counted.get(first + timedelta(days=offset), 0),
        )
        for offset in range(ACTIVITY_DAYS)
    ]


def _streaks(by_day: dict[date, int], today: date) -> tuple[int, int]:
    """Current and longest run of consecutive active days.

    Today not being reviewed yet does not break the streak — it is still today. The
    run is measured from yesterday in that case, which is what every SRS app does and
    what users expect at 9am.
    """
    active = {day for day, count in by_day.items() if count > 0}
    if not active:
        return 0, 0

    current = 0
    cursor = today if today in active else today - timedelta(days=1)
    while cursor in active:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    for day in sorted(active):
        if run and (day - timedelta(days=1)) in active:
            run += 1
        else:
            run = 1
        longest = max(longest, run)

    return current, longest


async def _total_cards(session: AsyncSession, user: User) -> int:
    return int(
        await session.scalar(select(func.count(Card.id)).where(Card.user_id == user.id)) or 0
    )


async def _due_now(session: AsyncSession, user: User, moment: datetime) -> int:
    statement = select(func.count(CardState.card_id)).where(
        CardState.user_id == user.id,
        CardState.suspended.is_(False),
        CardState.due <= moment,
    )
    return int(await session.scalar(statement) or 0)


async def _retention(session: AsyncSession, user: User) -> float | None:
    """Share of *review*-state answers the user did not fail.

    New and learning cards are excluded deliberately: failing a card you are still
    learning is the process working, not a memory lapse, and counting it would drag
    the number down for exactly the users who are studying hardest.
    """
    statement = select(
        func.count(ReviewLog.id).label("total"),
        func.count(ReviewLog.id).filter(ReviewLog.rating > int(Rating.again)).label("passed"),
    ).where(ReviewLog.user_id == user.id, ReviewLog.state == STATE_REVIEW)

    row = (await session.execute(statement)).one()
    if not row.total:
        return None
    return round(float(row.passed) / float(row.total), 4)
