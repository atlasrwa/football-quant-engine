"""Canonical content hashing utility for Phase 3.2 provenance.

This module provides a SINGLE canonical hashing implementation that
produces results identical to the existing domain object static methods:

- DatasetVersion.compute_content_hash()
- FeatureVersion.compute_content_hash()
- ModelVersion.compute_content_hash()
- BacktestRun.compute_content_hash()

Rules:
- SHA-256
- Canonical JSON with sort_keys=True, separators=(",",":")
- Sorted arrays where semantically appropriate
- Normalized numeric representation (Python default)
- No timestamps (unless semantic inputs)
- No database-generated fields (UUIDs used only when they ARE semantic inputs)
- UTF-8 encoding

The server computes content_hash — it is NEVER accepted from clients.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional


def _canonical_json(obj: dict | list) -> str:
    """Produce deterministic canonical JSON string.

    Uses sort_keys for objects, compact separators, no trailing whitespace.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(data: str) -> str:
    """Compute SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_dataset_content_hash(match_ids: list[int]) -> str:
    """Compute dataset content hash from sorted match IDs.

    Identical to DatasetVersion.compute_content_hash().

    Args:
        match_ids: List of external match identifiers.

    Returns:
        64-char lowercase hex SHA-256.
    """
    canonical = json.dumps(sorted(match_ids), separators=(",", ":"))
    return _sha256(canonical)


def compute_feature_version_hash(
    dataset_id: str,
    xg_rolling_window: int,
    form_rolling_window: int,
    referee_min_matches: int,
    xmetric_coefficients: Optional[dict[str, float]] = None,
) -> str:
    """Compute feature version content hash.

    Identical to FeatureVersion.compute_content_hash().

    Args:
        dataset_id: Parent dataset UUID as string.
        xg_rolling_window: xG rolling window size.
        form_rolling_window: Form rolling window size.
        referee_min_matches: Referee minimum match threshold.
        xmetric_coefficients: Optional xMetric coefficient dict.

    Returns:
        64-char lowercase hex SHA-256.
    """
    canonical = _canonical_json({
        "dataset_id": dataset_id,
        "xg_rolling_window": xg_rolling_window,
        "form_rolling_window": form_rolling_window,
        "referee_min_matches": referee_min_matches,
        "xmetric_coefficients": xmetric_coefficients,
    })
    return _sha256(canonical)


def compute_model_version_hash(
    strategy_content_hash: str,
    feature_version_id: str,
    train_window: int,
    test_window: int,
    step_size: int,
    min_odds: float,
    max_odds: float,
) -> str:
    """Compute model version content hash.

    Identical to ModelVersion.compute_content_hash().

    Args:
        strategy_content_hash: SHA-256 of strategy definition.
        feature_version_id: Feature version UUID as string.
        train_window: Walk-forward training window.
        test_window: Walk-forward test window.
        step_size: Walk-forward step size.
        min_odds: Minimum odds filter.
        max_odds: Maximum odds filter.

    Returns:
        64-char lowercase hex SHA-256.
    """
    canonical = _canonical_json({
        "strategy_content_hash": strategy_content_hash,
        "feature_version_id": feature_version_id,
        "train_window": train_window,
        "test_window": test_window,
        "step_size": step_size,
        "min_odds": min_odds,
        "max_odds": max_odds,
    })
    return _sha256(canonical)


def compute_backtest_run_hash(
    model_version_id: str,
    dataset_id: str,
) -> str:
    """Compute backtest run content hash from inputs.

    Identical to BacktestRun.compute_content_hash().
    Hashes INPUTS only — not outputs/results.

    Args:
        model_version_id: Model version UUID as string.
        dataset_id: Dataset version UUID as string.

    Returns:
        64-char lowercase hex SHA-256.
    """
    canonical = _canonical_json({
        "model_version_id": model_version_id,
        "dataset_id": dataset_id,
    })
    return _sha256(canonical)
