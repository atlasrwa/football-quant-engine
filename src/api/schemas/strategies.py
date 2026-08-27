"""Strategy-related request/response schemas."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ConditionSchema(BaseModel):
    field: str
    op: str = Field(..., pattern=r"^(>|<|>=|<=|==|!=)$")
    value: float


class CreateStrategyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    metric: str = Field(..., pattern=r"^(xC|xB|xO)$")
    market: str = Field(..., min_length=1)
    conditions: List[ConditionSchema] = Field(..., min_length=1)
    logic: str = Field(default="and", pattern=r"^(and|or)$")
    direction: str = Field(..., pattern=r"^(OVER|UNDER|BACK|LAY)$")
    min_odds: float = Field(default=1.50, gt=1.0)
    visibility: str = Field(default="private", pattern=r"^(private|public|unlisted)$")


class StrategyResponse(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    description: Optional[str]
    visibility: str
    status: str
    created_at: Optional[str] = None


class StrategyVersionResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    version: int
    definition: dict
    content_hash: str
    created_by: UUID
    is_deprecated: bool
    created_at: Optional[str] = None


class CreateStrategyResponse(BaseModel):
    strategy: StrategyResponse
    version: StrategyVersionResponse


class VisibilityUpdateRequest(BaseModel):
    visibility: str = Field(..., pattern=r"^(private|public|unlisted)$")


class ForkRequest(BaseModel):
    source_version: Optional[int] = None  # If None, forks latest version
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
