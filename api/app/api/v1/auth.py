from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_session
from app.models import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services import rate_limit
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        429: {"description": "Registration limit exceeded", "content": {"application/json": {"example": {"detail": "Too many requests. Try again in 30 seconds."}}}},
        503: {"description": "Rate-limit storage is unavailable"},
    },
)
async def register(payload: UserCreate, request: Request, session: SessionDep) -> AuthResponse:
    """Create a user and return an access token."""
    await rate_limit.enforce_rate_limit(
        "auth:register", rate_limit.client_ip(request), settings.AUTH_RATE_LIMIT_PER_MINUTE
    )
    email = str(payload.email).lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    user = User(full_name=payload.full_name, email=email, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")
    await session.refresh(user)
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.post(
    "/login",
    response_model=AuthResponse,
    responses={
        429: {"description": "Login limit exceeded", "content": {"application/json": {"example": {"detail": "Too many requests. Try again in 30 seconds."}}}},
        503: {"description": "Rate-limit storage is unavailable"},
    },
)
async def login(payload: LoginRequest, request: Request, session: SessionDep) -> AuthResponse:
    """Verify credentials and return an access token."""
    await rate_limit.enforce_rate_limit(
        "auth:login", rate_limit.client_ip(request), settings.AUTH_RATE_LIMIT_PER_MINUTE
    )
    email = str(payload.email).lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> User:
    """Return the authenticated user's profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(payload: UserUpdate, current_user: CurrentUser, session: SessionDep) -> User:
    """Update the authenticated user's display name."""
    current_user.full_name = payload.full_name
    await session.commit()
    await session.refresh(current_user)
    return current_user
