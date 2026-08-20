"""FastAPI dependencies: database session, shared clients, current user."""

from typing import Annotated

import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User


def get_redis(request: Request) -> Redis:
    """The process-wide Redis pool, created in the lifespan."""
    redis: Redis = request.app.state.redis
    return redis


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The one shared `httpx.AsyncClient` (SPEC §6, §13). Never build one per request."""
    client: httpx.AsyncClient = request.app.state.http_client
    return client


def get_client_ip(request: Request) -> str:
    """Best-effort client IP, trusting the `X-Forwarded-For` our own nginx sets."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


DbSession = Annotated[AsyncSession, Depends(get_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]
HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
ClientIp = Annotated[str, Depends(get_client_ip)]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("Avtorizatsiya talab qilinadi.", code="unauthorized")
    return token


async def get_current_user(request: Request, session: DbSession) -> User:
    """Resolve the session JWT to a live, active user."""
    user_id = decode_access_token(_bearer_token(request))

    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise UnauthorizedError("Foydalanuvchi topilmadi.", code="user_not_found")
    if not user.is_active:
        raise ForbiddenError("Hisob faol emas.", code="user_inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
