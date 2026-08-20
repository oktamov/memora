"""Session JWT encode/decode (SPEC §7).

Every endpoint except `POST /auth/telegram` authenticates with this token, not with
initData — initData carries a freshness check that is wasted if re-validated per
request.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import settings
from app.core.errors import UnauthorizedError

_ISSUER = "memora"


def create_access_token(user_id: UUID, *, now: datetime | None = None) -> tuple[str, int]:
    """Return `(token, expires_in_seconds)` for a 24h session."""
    issued_at = now or datetime.now(UTC)
    ttl = timedelta(hours=settings.JWT_TTL_HOURS)
    expires_at = issued_at + ttl

    token = jwt.encode(
        {
            "sub": str(user_id),
            "iss": _ISSUER,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> UUID:
    """Return the user id the token was issued for, or raise `UnauthorizedError`."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Sessiya muddati tugadi.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Sessiya yaroqsiz.", code="token_invalid") from exc

    try:
        return UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Sessiya yaroqsiz.", code="token_invalid") from exc
