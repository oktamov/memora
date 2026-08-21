"""aiogram Bot and Dispatcher construction (SPEC §9a).

Webhook mode, mounted on the same FastAPI app and the same process. There is no second
service and no polling.
"""

from __future__ import annotations

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.registry import ProviderRegistry
from app.telegram.handlers import register_handlers
from app.telegram.handlers.deps import BotContext

logger = get_logger(__name__)


def build_bot(client: httpx.AsyncClient) -> Bot:
    """The Bot. `client` is accepted so the shared-client rule stays visible at the
    call site; aiogram manages its own aiohttp session internally."""
    del client
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    registry: ProviderRegistry,
) -> Dispatcher:
    """The Dispatcher, with its resources injected into the workflow context.

    Handlers take `context: BotContext` as a keyword argument; aiogram fills it from
    the workflow data set here, which keeps them free of FastAPI and of globals.
    """
    dispatcher = Dispatcher()
    dispatcher["context"] = BotContext(
        session_factory=session_factory, redis=redis, registry=registry
    )
    register_handlers(dispatcher)
    return dispatcher


async def configure_webhook(bot: Bot) -> None:
    """Point Telegram at us. Safe to call on every boot — it is idempotent."""
    if not settings.MINI_APP_URL.startswith("https://"):
        logger.warning(
            "webhook_not_registered",
            extra={
                "event": "webhook_not_registered",
                "reason": "Telegram requires an HTTPS webhook URL",
            },
        )
        return

    base = settings.MINI_APP_URL.rstrip("/")
    url = f"{base}/telegram/webhook/{settings.TELEGRAM_WEBHOOK_PATH_SECRET}"
    await bot.set_webhook(
        url=url,
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET or None,
        drop_pending_updates=False,
        allowed_updates=["message", "callback_query"],
    )
    logger.info("webhook_registered", extra={"event": "webhook_registered"})


async def configure_menu_button(bot: Bot) -> None:
    """Set the chat menu button, for every chat, to open the Mini App.

    SPEC §9a asks for a *persistent* way to open the app. The menu button is the only
    persistent affordance that also carries `initData` — a reply-keyboard button opens
    the app unauthenticated (DECISIONS.md D26). Setting it here rather than in BotFather
    means a fresh deployment is correct without anyone remembering a manual step.
    """
    if not settings.MINI_APP_URL.startswith("https://"):
        logger.warning(
            "menu_button_not_set",
            extra={
                "event": "menu_button_not_set",
                "reason": "Telegram requires an HTTPS Mini App URL",
            },
        )
        return

    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Memorani ochish",
            web_app=WebAppInfo(url=settings.MINI_APP_URL),
        )
    )
    logger.info("menu_button_set", extra={"event": "menu_button_set"})
