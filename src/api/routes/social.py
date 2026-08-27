"""Social API endpoints: follows, reputation, leaderboard."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.auth.context import AuthContext
from src.persistence.database import get_pool
from src.persistence.events import EventService, EventTypes
from src.persistence.pg_social_repository import (
    PgFollowRepository, PgReputationRepository, PgLeaderboardRepository,
)

router = APIRouter(prefix="/api/v1", tags=["social"])


# ═══════════════════ Follows ═══════════════════

@router.post("/users/{user_id}/follow", status_code=201)
async def follow_user(user_id: UUID, ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Follow a user."""
    if user_id == ctx.user_id:
        raise APIError(422, ErrorCodes.BUSINESS_RULE_VIOLATION, "Cannot follow yourself")

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            repo = PgFollowRepository(conn)
            is_new = await repo.follow(ctx.user_id, user_id)

            if is_new:
                await EventService(conn).emit(
                    event_type=EventTypes.FOLLOW_CREATED,
                    aggregate_type="follow",
                    aggregate_id=f"{ctx.user_id}:{user_id}",
                    actor_id=ctx.user_id,
                    payload={"followed_id": str(user_id)},
                )

    return {"status": "following", "followed_id": str(user_id)}


@router.delete("/users/{user_id}/follow")
async def unfollow_user(user_id: UUID, ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Unfollow a user."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            repo = PgFollowRepository(conn)
            deleted = await repo.unfollow(ctx.user_id, user_id)

            if deleted:
                await EventService(conn).emit(
                    event_type=EventTypes.FOLLOW_DELETED,
                    aggregate_type="follow",
                    aggregate_id=f"{ctx.user_id}:{user_id}",
                    actor_id=ctx.user_id,
                    payload={"unfollowed_id": str(user_id)},
                )

    return {"status": "unfollowed", "unfollowed_id": str(user_id)}


@router.get("/users/{user_id}/followers")
async def get_followers(user_id: UUID, ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Get a user's followers."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgFollowRepository(conn)
            followers = await repo.get_followers(user_id)
            count = await repo.follower_count(user_id)
    return {"followers": [str(f) for f in followers], "count": count}


@router.get("/users/{user_id}/following")
async def get_following(user_id: UUID, ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Get users that a user follows."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgFollowRepository(conn)
            following = await repo.get_following(user_id)
            count = await repo.following_count(user_id)
    return {"following": [str(f) for f in following], "count": count}


# ═══════════════════ Reputation ═══════════════════

@router.get("/users/{user_id}/reputation")
async def get_reputation(
    user_id: UUID,
    period: str = "30d",
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get a user's reputation score."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgReputationRepository(conn)
            score = await repo.get_by_user(user_id, period_type=period)
    if not score:
        return {"reputation": None}
    return {"reputation": _serialize(score)}


# ═══════════════════ Leaderboard ═══════════════════

@router.get("/leaderboard")
async def get_leaderboard(
    scope: str = "global",
    period: str = "30d",
    limit: int = 50,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get the leaderboard."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgLeaderboardRepository(conn)
            entries = await repo.get_leaderboard(scope=scope, period_type=period, limit=limit)
    return {"leaderboard": [_serialize(e) for e in entries], "scope": scope, "period": period}


def _serialize(record: dict) -> dict:
    result = {}
    for k, v in record.items():
        if hasattr(v, "hex"):
            result[k] = str(v)
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result
