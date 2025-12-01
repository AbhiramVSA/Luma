"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from models.auth import LoginRequest, TokenResponse
from services.auth import authenticate_user, create_access_token

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> TokenResponse:
    user = await authenticate_user(session, credentials.email, credentials.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(subject=str(user.id), extra_claims={"email": user.email})
    return TokenResponse(access_token=token)
