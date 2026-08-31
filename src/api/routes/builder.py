"""No-code strategy builder API endpoint.

Exposes a FastAPI REST interface for compiling strategy definitions
from form data and running async backtests.
"""

from __future__ import annotations

import uuid
import logging
from typing import List

from src.engine.analysis.builder import StrategyBuilder
from src.engine.analysis.evaluator import Condition, Strategy

logger = logging.getLogger(__name__)

# In-memory job store (production would use Redis/DB)
_job_store: dict[str, dict] = {}


# --- Pydantic models (standalone, no FastAPI import required at module level) ---

class ConditionSchema:
    """Condition schema for API input."""

    def __init__(self, field: str, op: str, value: float):
        self.field = field
        self.op = op
        self.value = value


class CompileRequest:
    """Request model for strategy compilation."""

    def __init__(
        self,
        name: str,
        metric: str,
        market: str,
        conditions: List[dict],
        direction: str,
        logic: str = "and",
        min_odds: float = 1.50,
    ):
        self.name = name
        self.metric = metric
        self.market = market
        self.conditions = conditions
        self.direction = direction
        self.logic = logic
        self.min_odds = min_odds


class CompileResponse:
    """Response model for strategy compilation."""

    def __init__(self, job_id: str, strategy_json: str, status: str = "queued"):
        self.job_id = job_id
        self.strategy_json = strategy_json
        self.status = status

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "strategy_json": self.strategy_json,
            "status": self.status,
        }


class BacktestResultResponse:
    """Response model for backtest result polling."""

    def __init__(self, job_id: str, status: str, result: dict | None = None):
        self.job_id = job_id
        self.status = status
        self.result = result

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "result": self.result,
        }


def compile_strategy(request: CompileRequest) -> CompileResponse:
    """Compile a strategy from form data.

    Converts the request into a Strategy object via StrategyBuilder,
    creates a job ID, and returns the compiled strategy JSON.

    Args:
        request: Strategy compilation request.

    Returns:
        CompileResponse with job_id and strategy JSON.
    """
    builder = StrategyBuilder()
    builder.set_name(request.name)
    builder.set_metric(request.metric)
    builder.set_market(request.market)
    builder.set_direction(request.direction)
    builder.set_logic(request.logic)
    builder.set_min_odds(request.min_odds)

    for cond in request.conditions:
        builder.add_condition(
            field=cond["field"],
            op=cond["op"],
            value=float(cond["value"]),
        )

    # Validate and build
    strategy = builder.build()
    strategy_json = builder.to_json()

    # Create job
    job_id = str(uuid.uuid4())
    _job_store[job_id] = {
        "status": "queued",
        "strategy_json": strategy_json,
        "result": None,
    }

    logger.info("Strategy compiled: job_id=%s, name='%s'", job_id, request.name)
    return CompileResponse(job_id=job_id, strategy_json=strategy_json, status="queued")


def get_result(job_id: str) -> BacktestResultResponse:
    """Poll backtest result by job ID.

    Args:
        job_id: The job identifier.

    Returns:
        BacktestResultResponse with current status and result if complete.
    """
    if job_id not in _job_store:
        return BacktestResultResponse(job_id=job_id, status="not_found")

    job = _job_store[job_id]
    return BacktestResultResponse(
        job_id=job_id,
        status=job["status"],
        result=job["result"],
    )


def update_job(job_id: str, status: str, result: dict | None = None) -> None:
    """Update job status (called by background worker).

    Args:
        job_id: Job identifier.
        status: New status ("running", "completed", "failed").
        result: Backtest result dict (if completed).
    """
    if job_id in _job_store:
        _job_store[job_id]["status"] = status
        _job_store[job_id]["result"] = result


def clear_jobs() -> None:
    """Clear all jobs (for testing)."""
    _job_store.clear()
