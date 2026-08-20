"""Auth endpoints (SPEC §7)."""

from fastapi import APIRouter, status

from app.core.config import settings
from app.core.deps import ClientIp, CurrentUser, DbSession, RedisClient
from app.core.ratelimit import hit
from app.core.security import create_access_token
from app.schemas.auth import (
    TelegramAuthRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def authenticate(
    payload: TelegramAuthRequest,
    session: DbSession,
    redis: RedisClient,
    client_ip: ClientIp,
) -> TokenResponse:
    """Exchange validated initData for a 24h session JWT.

    This is the only endpoint that accepts initData, and the only one rate limited by
    IP rather than by user — there is no user yet at this point (SPEC §8.3).
    """
    await hit(
        redis,
        f"rl:auth:ip:{client_ip}",
        limit=settings.AUTH_RATE_PER_MINUTE_PER_IP,
        window_seconds=60,
    )

    user, _start_param = await auth_service.authenticate_init_data(session, payload.init_data)
    token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserResponse)
async def read_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest, user: CurrentUser, session: DbSession
) -> UserResponse:
    """Update settings. Unset fields are left alone; `reminder_hour: null` disables."""
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)
