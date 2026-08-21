"""Resources handlers need, taken from the aiogram workflow context.

`bot.py` puts these on the Dispatcher at construction, so handlers stay free of
FastAPI and of module-level globals.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.providers.registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class BotContext:
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    registry: ProviderRegistry
