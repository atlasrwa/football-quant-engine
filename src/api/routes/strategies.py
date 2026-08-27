"""Strategy API endpoints: create, get, versions, visibility, fork."""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.api.schemas.strategies import (
    CreateStrategyRequest,
    CreateStrategyResponse,
    ForkRequest,
    StrategyResponse,
    StrategyVersionResponse,
    VisibilityUpdateRequest,
)
from src.auth.context import AuthContext
from src.persistence.database import get_pool
from src.persistence.events import EventService, EventTypes
from src.persistence.idempotency import IdempotencyService, IdempotencyConflictError, compute_request_hash
from src.persistence.pg_strategy_repository import (
    PgStrategyForkRepository,
    PgStrategyRepository,
    PgStrategyVersionRepository,
    StrategyRecord,
    compute_content_hash,
)

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.post("", status_code=201)
async def create_strategy(
    body: CreateStrategyRequest,
    ctx: AuthContext = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> dict:
    """Create a new strategy with its first version.

    Supports Idempotency-Key header for safe retries.
    Content hash is computed server-side from the definition.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            # Idempotency check
            if idempotency_key:
                req_hash = compute_request_hash(body.model_dump(mode="json"))
                idem_svc = IdempotencyService(conn)
                try:
                    cached = await idem_svc.check(ctx.user_id, idempotency_key, req_hash)
                except IdempotencyConflictError:
                    raise APIError(
                        409, ErrorCodes.IDEMPOTENCY_CONFLICT,
                        "Idempotency key already used with a different request body",
                    )
                if cached is not None:
                    return cached.response_body

            # Build definition dict
            definition = {
                "name": body.name,
                "metric": body.metric,
                "market": body.market,
                "conditions": [c.model_dump(mode="json") for c in body.conditions],
                "logic": body.logic,
                "direction": body.direction,
                "min_odds": body.min_odds,
            }

            # Check for duplicate content hash
            ver_repo = PgStrategyVersionRepository(conn)
            content_hash = compute_content_hash(definition)
            existing = await ver_repo.get_by_content_hash(content_hash)
            if existing:
                raise APIError(
                    409, ErrorCodes.CONFLICT,
                    "A strategy with this exact definition already exists",
                    details={"existing_strategy_id": str(existing.strategy_id), "version": existing.version},
                )

            # Create strategy
            strat_repo = PgStrategyRepository(conn)
            strategy_id = uuid4()
            strat = await strat_repo.create_strategy(StrategyRecord(
                id=strategy_id,
                owner_id=ctx.user_id,
                name=body.name,
                description=body.description,
                visibility=body.visibility,
                status="active",
            ))

            # Create first version
            version = await ver_repo.create_version(
                strategy_id=strategy_id,
                definition=definition,
                created_by=ctx.user_id,
            )

            # Emit events
            event_svc = EventService(conn)
            await event_svc.emit(
                event_type=EventTypes.STRATEGY_CREATED,
                aggregate_type="strategy",
                aggregate_id=str(strategy_id),
                actor_id=ctx.user_id,
                payload={"name": body.name, "visibility": body.visibility},
            )
            await event_svc.emit(
                event_type=EventTypes.STRATEGY_VERSION_CREATED,
                aggregate_type="strategy",
                aggregate_id=str(strategy_id),
                actor_id=ctx.user_id,
                payload={"version": version.version, "content_hash": version.content_hash},
            )

            response_body = CreateStrategyResponse(
                strategy=StrategyResponse(
                    id=strat.id, owner_id=strat.owner_id,
                    name=strat.name, description=strat.description,
                    visibility=strat.visibility, status=strat.status,
                    created_at=strat.created_at.isoformat() if strat.created_at else None,
                ),
                version=StrategyVersionResponse(
                    id=version.id, strategy_id=version.strategy_id,
                    version=version.version, definition=version.definition,
                    content_hash=version.content_hash, created_by=version.created_by,
                    is_deprecated=version.is_deprecated,
                    created_at=version.created_at.isoformat() if version.created_at else None,
                ),
            ).model_dump(mode="json")

            # Store idempotency response
            if idempotency_key:
                await idem_svc.store(
                    ctx.user_id, idempotency_key,
                    "POST /api/v1/strategies", "POST",
                    req_hash, 201, response_body,
                )

    return response_body


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get a strategy by ID. Respects visibility rules."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            strat_repo = PgStrategyRepository(conn)
            strat = await strat_repo.get_strategy(strategy_id)

    if not strat:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Strategy not found")

    return {
        "strategy": StrategyResponse(
            id=strat.id, owner_id=strat.owner_id,
            name=strat.name, description=strat.description,
            visibility=strat.visibility, status=strat.status,
            created_at=strat.created_at.isoformat() if strat.created_at else None,
        ).model_dump(mode="json")
    }


@router.get("/{strategy_id}/versions/{version}")
async def get_strategy_version(
    strategy_id: UUID,
    version: int,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get a specific strategy version."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            ver_repo = PgStrategyVersionRepository(conn)
            ver = await ver_repo.get_version(strategy_id, version)

    if not ver:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Strategy version not found")

    return {
        "version": StrategyVersionResponse(
            id=ver.id, strategy_id=ver.strategy_id,
            version=ver.version, definition=ver.definition,
            content_hash=ver.content_hash, created_by=ver.created_by,
            is_deprecated=ver.is_deprecated,
            created_at=ver.created_at.isoformat() if ver.created_at else None,
        ).model_dump(mode="json")
    }


@router.patch("/{strategy_id}/versions/{version}/visibility")
async def update_visibility(
    strategy_id: UUID,
    version: int,  # included in path for specificity but changes strategy-level visibility
    body: VisibilityUpdateRequest,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Change strategy visibility. Only the owner can do this."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            strat_repo = PgStrategyRepository(conn)
            strat = await strat_repo.get_strategy(strategy_id)

            if not strat:
                raise APIError(404, ErrorCodes.NOT_FOUND, "Strategy not found")

            if strat.owner_id != ctx.user_id and not ctx.is_admin:
                raise APIError(403, ErrorCodes.FORBIDDEN, "Only the owner can change visibility")

            updated = await strat_repo.update_visibility(strategy_id, body.visibility)

            await EventService(conn).emit(
                event_type=EventTypes.STRATEGY_VISIBILITY_CHANGED,
                aggregate_type="strategy",
                aggregate_id=str(strategy_id),
                actor_id=ctx.user_id,
                payload={"old_visibility": strat.visibility, "new_visibility": body.visibility},
            )

    return {
        "strategy": StrategyResponse(
            id=updated.id, owner_id=updated.owner_id,
            name=updated.name, description=updated.description,
            visibility=updated.visibility, status=updated.status,
            created_at=updated.created_at.isoformat() if updated.created_at else None,
        ).model_dump(mode="json")
    }


@router.post("/{strategy_id}/fork", status_code=201)
async def fork_strategy(
    strategy_id: UUID,
    body: ForkRequest,
    ctx: AuthContext = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> dict:
    """Fork a strategy (copy its definition into a new strategy owned by the current user)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            ver_repo = PgStrategyVersionRepository(conn)
            strat_repo = PgStrategyRepository(conn)
            fork_repo = PgStrategyForkRepository(conn)

            # Get source version
            if body.source_version:
                source_ver = await ver_repo.get_version(strategy_id, body.source_version)
            else:
                source_ver = await ver_repo.get_latest_version(strategy_id)

            if not source_ver:
                raise APIError(404, ErrorCodes.NOT_FOUND, "Source strategy version not found")

            # Create new strategy (the fork)
            source_strat = await strat_repo.get_strategy(strategy_id)
            fork_name = body.name or f"Fork of {source_strat.name}"
            new_strategy_id = uuid4()

            new_strat = await strat_repo.create_strategy(StrategyRecord(
                id=new_strategy_id,
                owner_id=ctx.user_id,
                name=fork_name,
                description=body.description or f"Forked from {source_strat.name} v{source_ver.version}",
                visibility="private",
                status="active",
            ))

            # Create version on the fork (same definition, new version record)
            new_ver = await ver_repo.create_version(
                strategy_id=new_strategy_id,
                definition=source_ver.definition,
                created_by=ctx.user_id,
            )

            # Record fork lineage
            await fork_repo.create_fork(
                source_strategy_id=strategy_id,
                source_version=source_ver.version,
                source_content_hash=source_ver.content_hash,
                target_strategy_id=new_strategy_id,
                forked_by=ctx.user_id,
            )

            await EventService(conn).emit(
                event_type=EventTypes.STRATEGY_FORKED,
                aggregate_type="strategy",
                aggregate_id=str(new_strategy_id),
                actor_id=ctx.user_id,
                payload={
                    "source_strategy_id": str(strategy_id),
                    "source_version": source_ver.version,
                    "source_content_hash": source_ver.content_hash,
                },
            )

    return {
        "strategy": StrategyResponse(
            id=new_strat.id, owner_id=new_strat.owner_id,
            name=new_strat.name, description=new_strat.description,
            visibility=new_strat.visibility, status=new_strat.status,
            created_at=new_strat.created_at.isoformat() if new_strat.created_at else None,
        ).model_dump(mode="json"),
        "version": StrategyVersionResponse(
            id=new_ver.id, strategy_id=new_ver.strategy_id,
            version=new_ver.version, definition=new_ver.definition,
            content_hash=new_ver.content_hash, created_by=new_ver.created_by,
            is_deprecated=new_ver.is_deprecated,
            created_at=new_ver.created_at.isoformat() if new_ver.created_at else None,
        ).model_dump(mode="json"),
        "fork_source": {
            "strategy_id": str(strategy_id),
            "version": source_ver.version,
            "content_hash": source_ver.content_hash,
        },
    }
