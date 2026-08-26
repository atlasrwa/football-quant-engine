"""Batch 7/8 — Research Persistence Layer.

Repository abstraction for research objects. Domain objects remain
independent of persistence technology.

Architecture:
    Research domain objects (frozen)
        ↓
    ResearchRepository (interface)
        ↓
    InMemoryResearchRepository (tests)
    PostgresResearchRepository (production)
"""

from src.research.persistence.repository import ResearchRepository
from src.research.persistence.memory import InMemoryResearchRepository

__all__ = [
    "ResearchRepository",
    "InMemoryResearchRepository",
]
