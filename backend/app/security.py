"""Password hashing and short-lived JWT access tokens."""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.config import Settings

password_hasher = PasswordHash.recommended()
# A per-process dummy hash keeps unknown-email login attempts on the password verification path.
_DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "verifywise-ai"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except (UnknownHashError, ValueError, TypeError):
        return False


def verify_unknown_user_password(password: str) -> None:
    password_hasher.verify(password, _DUMMY_HASH)


def create_access_token(user_id: str, settings: Settings) -> str:
    secret = _jwt_secret(settings)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "exp": expires,
            "jti": secrets.token_urlsafe(16),
            "iss": JWT_ISSUER,
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(
        token,
        _jwt_secret(settings),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "jti", "iss"]},
    )


def validate_auth_settings(settings: Settings) -> None:
    _jwt_secret(settings)
    if not 1 <= settings.access_token_expire_minutes <= 60:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 60.")


def _jwt_secret(settings: Settings) -> str:
    if settings.jwt_secret_key is None:
        raise RuntimeError("JWT_SECRET_KEY must be configured before starting the API.")
    secret = settings.jwt_secret_key.get_secret_value()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters.")
    return secret
