"""Trusted-operator user provisioning commands; there is no public registration API."""

import argparse
from getpass import getpass
import re
import sys

from sqlalchemy import select

from app.config import get_settings
from app.database import create_database_engine, create_session_factory, initialize_database
from app.models import User, UserRole
from app.security import hash_password

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def create_user(email: str, role: UserRole) -> None:
    normalized_email = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized_email):
        raise ValueError("A valid email address is required.")
    password = getpass("New password (minimum 12 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if len(password) > 128:
        raise ValueError("Password must contain no more than 128 characters.")

    engine = create_database_engine(get_settings().database_url)
    try:
        initialize_database(engine)
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            existing = session.scalar(select(User).where(User.email == normalized_email))
            if existing is not None:
                raise ValueError("A user with that email already exists.")
            session.add(
                User(email=normalized_email, password_hash=hash_password(password), role=role.value)
            )
            session.commit()
    finally:
        engine.dispose()
    print(f"Created active user {normalized_email} with role {role.value}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision a VerifyWise AI user (trusted local operator only).")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create-user", help="Create a user without exposing their password in shell history.")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--role", required=True, choices=[role.value for role in UserRole])
    args = parser.parse_args()
    try:
        create_user(args.email, UserRole(args.role))
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
