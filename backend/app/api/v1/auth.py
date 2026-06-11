import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
    verify_access_token,
)
from app.core.config import get_settings
from app.core.constants import (
    FORGOT_PASSWORD_RATE_LIMIT,
    LOCKOUT_MINUTES,
    LOGIN_RATE_LIMIT,
    MAX_FAILED_LOGINS,
)
from app.core.rate_limit import limiter
from app.models.organization import Organization
from app.models.user import User
from app.services.email_service import send_email

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class ResetPasswordResponse(BaseModel):
    message: str


_FORGOT_PASSWORD_MESSAGE = (
    "If that email is registered, you will receive a reset link"
)


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
@limiter.limit(LOGIN_RATE_LIMIT, override_defaults=True)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    email = _normalize_email(form.username)
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise HTTPException(
            status_code=423,
            detail="Account temporarily locked. Try again later.",
        )

    if user is None or not pwd_context.verify(form.password, user.hashed_password):
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            await db.flush()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
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


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit(FORGOT_PASSWORD_RATE_LIMIT, override_defaults=True)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    email = _normalize_email(body.email)
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is not None and user.is_active:
        token = create_access_token(
            {"sub": user.email, "type": "password_reset"},
            expires_minutes=60,
        )
        settings = get_settings()
        reset_url = (
            f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={token}"
        )
        subject = "Reset your HVAC Intelligence password"
        text_body = (
            f"Use the link below to reset your password. This link expires in 1 hour.\n\n"
            f"{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        )
        html_body = (
            f"<p>Use the link below to reset your password. This link expires in 1 hour.</p>"
            f'<p><a href="{reset_url}">Reset password</a></p>'
            "<p>If you did not request this, you can ignore this email.</p>"
        )
        if not send_email(user.email, subject, html_body, text_body):
            logger.warning(
                "Password reset email not sent for %s — email service not configured",
                user.email,
            )

    return ForgotPasswordResponse(message=_FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    payload = verify_access_token(body.token)
    if payload is None or payload.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    email = _normalize_email(str(payload.get("sub", "")))
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = pwd_context.hash(body.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.flush()

    return ResetPasswordResponse(message="Password updated")
