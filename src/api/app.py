"""FastAPI application for the Football Quant Engine.

Wires up all routes, middleware, and lifecycle management (DB pool).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.errors import APIError, ErrorCodes, error_response
from src.api.middleware.correlation import CorrelationIDMiddleware
from src.api.routes.users import router as auth_router, users_router
from src.api.routes.strategies import router as strategies_router
from src.api.routes.predictions import router as predictions_router
from src.api.routes.portfolios import router as portfolios_router
from src.api.routes.social import router as social_router
from src.api.routes.quarantine import router as quarantine_router
from src.api.routes.broadcasts import router as broadcasts_router
from src.api.routes.attestations import router as attestations_router
from src.persistence.database import init_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and close DB pool."""
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Football Quant Engine",
    version="0.1.0",
    description="Consumer/social hybrid quantitative football betting platform",
    lifespan=lifespan,
)

# Middleware (applied in reverse order — last added executes first)
app.add_middleware(CorrelationIDMiddleware)

# Routes
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(strategies_router)
app.include_router(predictions_router)
app.include_router(portfolios_router)
app.include_router(social_router)
app.include_router(quarantine_router)
app.include_router(broadcasts_router)
app.include_router(attestations_router)


# ═══════════════════════════════════════════════════════════════════
# EXCEPTION HANDLERS
# ═══════════════════════════════════════════════════════════════════

@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle structured API errors."""
    request_id = getattr(request.state, "request_id", None)
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        details=exc.details,
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Never leaks internals."""
    import logging
    logger = logging.getLogger("api")
    request_id = getattr(request.state, "request_id", None)
    logger.error("Unhandled error [%s]: %s", request_id, str(exc), exc_info=True)
    return error_response(
        status_code=500,
        code=ErrorCodes.INTERNAL_ERROR,
        message="An internal error occurred",
        request_id=request_id,
    )


# ═══════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint (unauthenticated)."""
    return {"status": "ok", "service": "football-quant-engine"}
