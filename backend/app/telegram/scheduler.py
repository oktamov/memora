"""The hourly reminder job (SPEC §9a).

APScheduler inside the API process — no Celery, no second service (SPEC §3).
"""

from __future__ import annotations

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.telegram.notify import send_reminders

logger = get_logger(__name__)

JOB_ID = "daily-reminders"


def build_scheduler(
    bot: Bot, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIOScheduler:
    """Runs on the hour. Each pass decides for itself whose local hour it now is."""
    scheduler = AsyncIOScheduler(timezone="UTC")

    async def run() -> None:
        try:
            await send_reminders(bot, session_factory)
        except Exception as exc:
            # A failed pass must not kill the job; the next hour tries again.
            logger.error(
                "reminder_job_failed",
                extra={"event": "reminder_job_failed", "error": str(exc)},
            )

    scheduler.add_job(
        run,
        CronTrigger(minute=0),
        id=JOB_ID,
        # A slow pass must not stack up behind the next hour's.
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )
    return scheduler
