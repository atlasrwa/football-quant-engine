"""Prospective evidence and market-observation plane for QFE V2.

This package captures point-in-time provider/market evidence and computes
research diagnostics such as genuine closing prices. It does not own, select,
or wrap a production probability model. QFE V2 model outputs enter this plane
only through explicit future versioned forecast artifacts after the offline
probability stack is frozen.

Design invariants:

- QFE V2's independent ``p_model`` remains odds-blind.
- Provider ``last_seen`` prices are not treated as genuine closing lines; only
  QFE's own timestamped pre-kickoff snapshots can define a genuine close.
- Missing is distinct from zero.
- Evidence is usable only when its observation timestamp satisfies the
  registered forecast cutoff.
- Absence from a lineup never implies injury or suspension without explicit
  provider evidence.
- This plane must not reintroduce any deprecated legacy probability path.

Network access is guarded, provider-scoped and fails closed when credentials or
verified capability are unavailable. Secrets are never serialized.
"""

from __future__ import annotations

__all__ = [
    "api_contract",
]

from src.research.prospective.prediction_freeze import (
    BASE_CORPUS_MANIFEST_HASH,
    COMPETITION_UNIVERSE,
    EXECUTION_PROTOCOL_HASH,
    LAYER4_MODEL_FREEZE_HASH,
    LAYER5_PROTOCOL_HASH,
    PREDICTION_BUNDLE_VERSION,
    ProspectivePredictionRow,
    blank_target_from_match,
    build_prospective_prediction_bundle,
    write_prospective_prediction_bundle,
)

from src.research.prospective.incremental_history import (
    PROTOCOL_HASH as INCREMENTAL_HISTORY_PROTOCOL_HASH,
    SNAPSHOT_VERSION as INCREMENTAL_HISTORY_SNAPSHOT_VERSION,
    build_incremental_history_snapshot,
    load_incremental_history_snapshot,
)
