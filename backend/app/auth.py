"""Authentication and role authorization dependencies."""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import User, UserRole
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
STAFF_APPLICATION_READ_ROLES = {UserRole.OFFICIAL_REVIEWER, UserRole.RULES_MANAGER}


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials, request.app.state.settings)
        user_id = claims.get("sub")
        if not isinstance(user_id, str):
            raise unauthorized
    except (jwt.InvalidTokenError, RuntimeError):
        raise unauthorized from None

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_roles(*allowed_roles: UserRole) -> Callable:
    """Build a dependency that rejects authenticated users outside the allowlist."""
    allowed = set(allowed_roles)

    def enforce_role(current_user: User = Depends(get_current_user)) -> User:
        try:
            role = UserRole(current_user.role)
        except ValueError:
            role = None
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return current_user

    return enforce_role


def ensure_application_read_access(user: User) -> None:
    if user.role == UserRole.APPLICANT:
        return
    if user.role in STAFF_APPLICATION_READ_ROLES:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
