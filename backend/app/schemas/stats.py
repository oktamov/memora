"""Stats response schemas (SPEC §7)."""

from datetime import date

from pydantic import Field

from app.schemas.common import ApiModel


class DailyActivityResponse(ApiModel):
    date: date
    reviews: int


class StatsOverviewResponse(ApiModel):
    streak_days: int
    longest_streak_days: int
    total_cards: int
    cards_due_today: int
    reviews_today: int
    #: Share of review-state answers not rated `again`, or null before any exist.
    retention_rate: float | None = None
    reviews_per_day: list[DailyActivityResponse] = Field(default_factory=list)
