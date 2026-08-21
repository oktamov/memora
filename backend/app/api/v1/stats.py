"""`GET /stats/overview` (SPEC §7)."""

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.stats import DailyActivityResponse, StatsOverviewResponse
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverviewResponse)
async def read_overview(user: CurrentUser, session: DbSession) -> StatsOverviewResponse:
    overview = await stats_service.overview(session, user)

    return StatsOverviewResponse(
        streak_days=overview.streak_days,
        longest_streak_days=overview.longest_streak_days,
        total_cards=overview.total_cards,
        cards_due_today=overview.cards_due_today,
        reviews_today=overview.reviews_today,
        retention_rate=overview.retention_rate,
        reviews_per_day=[
            DailyActivityResponse(date=entry.day, reviews=entry.reviews)
            for entry in overview.reviews_per_day
        ],
    )
