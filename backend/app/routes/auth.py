"""Login and current-user endpoints. User provisioning is intentionally not public."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.dependencies import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserRead
from app.security import create_access_token, verify_password, verify_unknown_user_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    if not EMAIL_PATTERN.fullmatch(payload.email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        verify_unknown_user_password(payload.password)
        raise _invalid_credentials()
    if not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise _invalid_credentials()

    settings = request.app.state.settings
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
def current_user(user: User = Depends(get_current_user)) -> User:
    return user


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )
