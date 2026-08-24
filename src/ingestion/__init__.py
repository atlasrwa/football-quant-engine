"""Ingestion module: data sourcing, caching, and validation.

Exports the DataProvider protocol and concrete implementations.
"""

from src.ingestion.provider import DataProvider, MockProvider

__all__ = ["DataProvider", "MockProvider"]
