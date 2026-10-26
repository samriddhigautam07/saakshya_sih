"""FastAPI dependencies shared by API routes."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.database import get_session


def get_db(request: Request) -> Generator[Session, None, None]:
    yield from get_session(request.app.state.session_factory)
