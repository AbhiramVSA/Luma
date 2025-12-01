"""Pydantic models for authentication."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class AuthenticatedUser(BaseModel):
    id: int
    email: EmailStr
