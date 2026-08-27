"""User API endpoints: registration, login, profile."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.api.schemas.users import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserResponse,
)
from src.auth.context import AuthContext
from src.auth.passwords import hash_password, verify_password
from src.auth.tokens import create_access_token
from src.persistence.database import get_pool
from src.persistence.events import EventService, EventTypes
from src.persistence.pg_user_repository import PgUserRepository
from src.persistence.repositories import UserRecord

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.post("/register", status_code=201)
async def register(body: RegisterRequest) -> dict:
    """Register a new user account.

    Creates the user, emits USER_REGISTERED event, returns the user record.
    Does NOT return a token — user must login separately.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Use system context for registration (user doesn't exist yet)
            await conn.execute("SET LOCAL app.user_id = '00000000-0000-0000-0000-000000000001'")
            await conn.execute("SET LOCAL app.user_role = 'system'")

            repo = PgUserRepository(conn)

            # Check existing
            if await repo.get_by_username(body.username):
                raise APIError(409, ErrorCodes.CONFLICT, f"Username '{body.username}' is already taken")
            if body.email and await repo.get_by_email(body.email):
                raise APIError(409, ErrorCodes.CONFLICT, f"Email is already registered")

            user_id = uuid4()
            user = UserRecord(
                id=user_id,
                username=body.username,
                email=body.email,
                display_name=body.display_name,
                password_hash=hash_password(body.password),
                role="user",
                status="active",
            )
            created = await repo.create(user)

            # Emit audit event in same transaction
            await EventService(conn).emit(
                event_type=EventTypes.USER_REGISTERED,
                aggregate_type="user",
                aggregate_id=str(user_id),
                actor_type="system",
                payload={"username": body.username, "email": body.email},
            )

    return {
        "user": UserResponse(
            id=created.id,
            username=created.username,
            email=created.email,
            display_name=created.display_name,
            role=created.role,
            status=created.status,
            created_at=created.created_at.isoformat() if created.created_at else None,
        ).model_dump(mode="json")
    }


@router.post("/login")
async def login(body: LoginRequest) -> LoginResponse:
    """Authenticate with username and password. Returns JWT access token."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL app.user_id = '00000000-0000-0000-0000-000000000001'")
            await conn.execute("SET LOCAL app.user_role = 'system'")

            repo = PgUserRepository(conn)
            user = await repo.get_by_username(body.username)

            if not user or not user.password_hash:
                raise APIError(401, ErrorCodes.UNAUTHENTICATED, "Invalid credentials")

            if not verify_password(body.password, user.password_hash):
                raise APIError(401, ErrorCodes.UNAUTHENTICATED, "Invalid credentials")

            if user.status != "active":
                raise APIError(403, ErrorCodes.FORBIDDEN, "Account is disabled")

            # Update last login
            await repo.update_last_login(user.id)

            # Generate token
            token = create_access_token(user.id, user.role)

            # Emit login event
            try:
                await EventService(conn).emit(
                    event_type=EventTypes.USER_LOGIN,
                    aggregate_type="user",
                    aggregate_id=str(user.id),
                    actor_type="user",
                    actor_id=user.id,
                )
            except Exception:
                pass  # Login succeeds even if event fails

    return LoginResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            status=user.status,
            created_at=user.created_at.isoformat() if user.created_at else None,
        ),
    )


@users_router.get("/me")
async def get_me(ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Get the current authenticated user's profile."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            repo = PgUserRepository(conn)
            user = await repo.get_by_id(ctx.user_id)

    if not user:
        raise APIError(404, ErrorCodes.NOT_FOUND, "User not found")

    return {
        "user": UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            status=user.status,
            avatar_url=user.avatar_url,
            bio=user.bio,
            created_at=user.created_at.isoformat() if user.created_at else None,
        ).model_dump(mode="json")
    }
