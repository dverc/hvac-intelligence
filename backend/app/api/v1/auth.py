from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.auth import verify_api_key
from app.core.auth_jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
)
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

UserRole = Literal["admin", "dispatcher", "read_only"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    org_id: str
    role: UserRole = "dispatcher"


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    role: str
    org_id: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str
    role: str
    org_id: str


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    role: str
    org_id: str
    is_active: bool
    created_at: str
    last_login_at: str | None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
    dependencies=[Depends(verify_api_key)],
)
async def register_user(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    email = _normalize_email(body.email)
    try:
        org_uuid = uuid.UUID(body.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid org_id") from exc

    org = await db.get(Organization, org_uuid)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        org_id=str(org_uuid),
        email=email,
        hashed_password=pwd_context.hash(body.password),
        role=body.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return RegisterResponse(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=user.org_id,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    email = _normalize_email(form.username)
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is None or not pwd_context.verify(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "org_id": user.org_id,
        }
    )

    return LoginResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=user.org_id,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    user = await db.get(User, uuid.UUID(str(current_user["sub"])))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return UserProfileResponse(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=user.org_id,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.post("/logout", status_code=200)
async def logout() -> dict[str, str]:
    # JWT is stateless — the client deletes the token to end the session.
    return {"status": "ok", "message": "Logged out"}
