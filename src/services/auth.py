"""Authentication helpers for FastAPI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.config import settings
from db.models import User
from db.session import get_session
from models.auth import AuthenticatedUser

token_scheme = HTTPBearer(auto_error=False)

if not settings.JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY must be configured for authentication.")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(*, subject: str, extra_claims: dict[str, str] | None = None) -> str:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.JWT_EXPIRES_MINUTES)
    payload: dict[str, str | float] = {
        "sub": subject,
        "iat": now.timestamp(),
        "exp": expires.timestamp(),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def require_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(token_scheme),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from error

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        user_id = int(subject)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        ) from error

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")

    return AuthenticatedUser(id=user.id, email=user.email)
