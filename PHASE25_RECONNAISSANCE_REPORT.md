# Phase 2.5 Reconnaissance Report

**Date:** 2026-08-24  
**Status:** AUDIT COMPLETE — Implementation phase next  
**Baseline:** 659 tests passing, 0 failures  
**Scope:** Production integrity gate before Phase 3

---

## 1. Executive Summary

The Phase 2 integration is architecturally sound. PredictionEvent is correctly frozen/immutable, Settlement is separate from Prediction, and the factory pattern cleanly decouples domain from engine.

However, the audit identifies **three P0 gaps** that must be fixed before persistence/users can be safely introduced:

| # | Gap | Severity | Status |
|---|-----|----------|--------|
| 1 | Settlement is NOT idempotent — same prediction can be settled multiple times | **P0 CRITICAL** | NOT SAFE |
| 2 | Callbacks have no deduplication — retry of settlement will double-apply P&L | **P0 CRITICAL** | NOT SAFE |
| 3 | No lifecycle state machine — PENDING→SETTLED transition not enforced at service level | **P1 HIGH** | WEAK |

There are also structural observations that need documentation but NOT code changes:

| # | Observation | Verdict |
|---|-------------|---------|
| 4 | PredictionEvent is frozen (immutable) — settlement cannot mutate it | ALREADY CORRECT |
| 5 | Proof hash uses only immutable prediction fields | ALREADY CORRECT |
| 6 | Settlement is separate from PredictionEvent | ALREADY CORRECT |
| 7 | `strategy_identities` dict is appropriate (not a service locator) | ACCEPTABLE |
| 8 | No synthetic data introduced in Phase 2 | CONFIRMED |
| 9 | Timestamps use UTC timezone-aware ISO 8601 | CONFIRMED |
| 10 | Backtest vs Live semantics separated by PredictionSource enum | CONFIRMED |

---

## 2. Concern #1 — PENDING / Immutability Semantics

### Current State

`PredictionEvent` is a `@dataclass(frozen=True, slots=True)`. Once created, its fields CANNOT be mutated. Python will raise `FrozenInstanceError` on any attribute assignment.

The current lifecycle model:

```
PENDING → (external settlement) → Settlement object created
```

The PredictionEvent itself never transitions — it is born with a status and remains that way forever. For live/paper predictions, it is born `PENDING`. For backtest predictions, it is born `SETTLED_WIN/LOSS/VOID`.

### Assessment

**This is semantically correct.** The desired model is:

```
CREATED → LOCKED → PENDING_SETTLEMENT → SETTLED → ANALYZED
```

In the current implementation:
- `CREATED` = factory creates the object
- `LOCKED` = the moment `frozen=True` takes effect (instantiation)
- `PENDING_SETTLEMENT` = `status=PENDING` on the frozen object
- `SETTLED` = a `Settlement` object is created linking to this prediction
- `ANALYZED` = downstream reads (not yet built)

The critical invariant **"once LOCKED, prediction attributes cannot change"** is ALREADY SATISFIED by Python's frozen dataclass mechanism. There is no need to add a separate LOCKED state — the dataclass IS the lock.

### Settlement Separation

Settlement data (outcome, CLV, P&L, settled_at) lives exclusively in the `Settlement` object, not in `PredictionEvent`. The `settled_at` field on PredictionEvent is set at creation time only for backtest predictions (where outcome is known), and is `None` for live/paper predictions. It is never mutated.

### Verdict: MOSTLY CORRECT

One weakness: The `PredictionStatus` enum on the frozen prediction is informational only for live predictions. A PENDING prediction's status field says `PENDING`, but nothing prevents creating a Settlement for it AND THEN creating ANOTHER Settlement for it. The immutability of the prediction is fine, but the settlement service lacks the guard.

**Action needed:** Settlement idempotency at the service level (Concern #3).

---

## 3. Concern #2 — Strategy Execution Context

### Current State

```python
strategy_identities: Dict[str, StrategyIdentityInfo] = {}
```

`StrategyIdentityInfo` is a small frozen dataclass:
```python
@dataclass(frozen=True, slots=True)
class StrategyIdentityInfo:
    strategy_id: str
    strategy_version: int
    content_hash: str
    model_version_id: str | None = None
```

It is passed to `XMetricBacktester.__init__()` and used in `_run_fold()` to emit PredictionEvents.

### Assessment

This is:
- ✅ Clean and appropriate — carries only execution provenance
- ✅ Immutable (frozen dataclass)
- ✅ No hidden global state
- ✅ No service locator pattern
- ✅ Deterministic
- ✅ Backward compatible (optional parameter, defaults to empty dict)

The dictionary key is `strategy_name` which maps naturally to the evaluator's Signal output. This is NOT becoming a god object — it carries exactly 4 fields.

### Verdict: LEAVE UNCHANGED

A `StrategyExecutionContext` wrapper would add abstraction without adding value. The current pattern is appropriately simple for the current complexity level.

---

## 4. Concern #3 — Settlement Idempotency

### Current State — CRITICAL GAP

`PredictionSettlementService.settle_match()`:

```python
pending = self._pending.pop(match_id, [])
for prediction in pending:
    settlement = SettlementFactory.settle_prediction(...)
    self._settlements[prediction.prediction_id] = settlement
```

The `pop()` removes predictions from the pending dict, so a second call for the same match returns empty. This provides **partial idempotency** — if the service state survives between calls.

**But there is NO check against `self._settlements`** before creating a new settlement. If a prediction is somehow in both `_pending` and already has a settlement (shouldn't happen in current flow, but could under retry/restart), it would be overwritten silently.

More critically: **There is no guard against re-registering and re-settling.** If the service is reconstructed (restart) and predictions are re-registered, they can be settled again.

### Specific Failure Modes

1. **Worker retry after crash:** Service state is lost. Predictions are re-registered. `settle_match()` runs again. Duplicate settlements, duplicate callbacks, duplicate P&L.

2. **Race condition (future):** Two workers both call `settle_match()` for the same match. One gets the pending list, the other gets empty. This is actually safe with `pop()` in single-process mode, but not safe with persistence.

3. **Callback double-execution:** If `settle_match()` is retried and the prediction was already popped from pending but still in `_all_predictions`, there's no way to detect it was already settled.

### Required Fix

Add an explicit check: if `prediction.prediction_id` already has a settlement in `_settlements`, skip it (idempotent) or error (conflicting).

### Verdict: P0 FIX REQUIRED

---

## 5. Concern #4 — Paper Trading Readiness

### Current State

```
QuarantineSettlementBridge._on_settlement()
    → QuarantineTracker.update_paper_pnl(strategy_name, pnl_delta, bets=1)
```

The bridge is called as a settlement callback. It accumulates P&L as a scalar delta on `QuarantineEntry.paper_pnl`.

### Assessment

**Double-counting risk:** If settlement is retried (concern #3), the callback fires again, and `paper_pnl` gets the same delta added twice. `QuarantineTracker.update_paper_pnl()` is purely additive — it has no deduplication.

**Reconstruction:** Paper P&L cannot currently be reconstructed from settlements because the bridge doesn't track which settlement_ids it has processed.

### Architectural Boundary

The desired model is correct:
```
PredictionEvent → Settlement → QuarantineTracker (via bridge)
```

Settlement IS the single source of truth. But the bridge must be idempotent.

### Required Fix

1. Track processed `settlement_id` values in the bridge
2. Skip if already processed (idempotent)
3. This also solves callback double-execution

### Verdict: P0 FIX REQUIRED (coupled to Concern #3)

---

## 6. Concern #5 — Persistence Readiness

### Current State

All domain objects are:
- Frozen dataclasses (immutable after construction)
- Have UUID-based identities
- Have `to_dict()` serialization
- Have content hashes where applicable
- Have ISO 8601 timestamps
- Have no database coupling

### Persistence Classification

| Object | Mutability | Identity | Versioned | Append-Only |
|--------|-----------|----------|-----------|-------------|
| Strategy | Immutable per version | strategy_id + version | Yes | Yes (versions) |
| StrategyIdentity | Frozen | strategy_id + version | Yes | Yes |
| DatasetVersion | Frozen | dataset_id | No | Yes |
| FeatureVersion | Frozen | feature_version_id | No | Yes |
| ModelVersion | Frozen | model_version_id | No | Yes |
| BacktestRun | Frozen | run_id | No | Yes |
| ValidationRun | Frozen | validation_id | No | Yes |
| PredictionEvent | Frozen | prediction_id | No | Yes |
| Settlement | Frozen | settlement_id | No | Yes |
| QuarantineEntry | **MUTABLE** | strategy_name | No | No — accumulates |

### Unique Constraints Needed

- `PredictionEvent.prediction_id` — globally unique
- `Settlement.settlement_id` — globally unique  
- `Settlement.prediction_id` — **MUST BE UNIQUE** (one settlement per prediction)
- `BacktestRun.run_id` — globally unique
- `StrategyIdentity` — unique on (strategy_id, strategy_version)

### Repository Boundaries

Minimal interfaces needed:
- `PredictionRepository` — store/retrieve predictions, check existence
- `SettlementRepository` — store/retrieve settlements, enforce unique prediction_id constraint

Not yet needed (can wait for Phase 3):
- `StrategyRepository` — StrategyRegistry is acceptable in-memory for now
- `BacktestRepository` — BacktestRun is produced by orchestrator, consumed by reports
- `ProvenanceRepository` — Provenance chain is linked by IDs, not stored centrally

### Verdict: DOCUMENT ONLY (no code needed yet)

The architecture is persistence-ready. All objects are serializable, have identities, and are append-only. The only required change is enforcing the unique constraint `Settlement.prediction_id` (which is the idempotency fix from Concern #3).

---

## 7. Additional Findings

### Proof-of-Alpha Integrity

`PredictionEvent.compute_proof_hash()` uses:
```python
{
    "strategy_content_hash": ...,
    "match_id": ...,
    "direction": ...,
    "entry_odds": ...,
    "timestamp": ...,
}
```

- ✅ `sort_keys=True` — deterministic ordering
- ✅ `separators=(",", ":")` — canonical JSON
- ✅ All fields are immutable prediction attributes
- ✅ No settlement fields included
- ✅ No random values
- ✅ No runtime addresses
- ⚠️ `timestamp` is `int(datetime.now(timezone.utc).timestamp())` — generated at creation time, then frozen. This is correct but means two calls within the same second produce the same timestamp component. Acceptable.

### Security / Trust Boundaries

- `fdr_validated` — set by `CommunityBroadcaster` from `validation_passed` parameter. The broadcaster does NOT decide this. ✅
- `closing_odds` — passed into `SettlementFactory` from `MatchResult`. Not client-provided in current flow. ✅
- `proof_hash` — computed by factory, not caller-provided. ✅
- `entry_odds` — extracted from `Signal.odds` which comes from DataFrame market data. ✅

**Future risk:** When user-facing APIs are added, none of these should be accepted from client input. Document this as a constraint.

### Performance

PredictionEvent creation in `_run_fold()`:
- Accesses `row.get(col)` — O(1) per column
- Calls `PredictionEvent.compute_proof_hash()` — one SHA-256 per bet
- Creates one UUID per bet
- No DataFrame copies
- No O(N²) patterns
- Memory: one PredictionEvent object (~500 bytes) per bet

For a typical backtest with ~100-500 bets: negligible overhead.

### Backtest / Live Separation

- `PredictionSource.BACKTEST` — created pre-settled, historical timestamps
- `PredictionSource.LIVE_SIGNAL` — created PENDING, real generation timestamp
- `PredictionSource.PAPER_TRADE` — created PENDING, real generation timestamp

These cannot be confused because:
1. Backtest predictions are born settled (status ≠ PENDING)
2. The settlement service refuses to register non-PENDING predictions
3. Source enum is frozen on the object

### No Synthetic Data

Confirmed: Phase 2 integration does NOT introduce:
- ❌ Synthetic odds (R03 fix already in place)
- ❌ Synthetic CLV (returns None when closing odds unavailable)
- ❌ Fake validation (fdr_validated comes from authoritative source)
- ❌ Fake provenance (all provenance computed from real inputs)

---

## 8. Implementation Plan

### P0 — Must Fix

| # | Fix | Location | Effort |
|---|-----|----------|--------|
| 1 | Settlement idempotency: check if prediction already settled before creating new settlement | `PredictionSettlementService.settle_match()` | SMALL |
| 2 | Conflicting settlement detection: if already settled with different outcome, raise error | `PredictionSettlementService.settle_match()` | SMALL |
| 3 | Callback deduplication: track processed settlement_ids in QuarantineSettlementBridge | `QuarantineSettlementBridge._on_settlement()` | SMALL |

### P1 — Should Fix

| # | Fix | Location | Effort |
|---|-----|----------|--------|
| 4 | Add `is_already_settled()` query method to service | `PredictionSettlementService` | TRIVIAL |
| 5 | Document lifecycle semantics in module docstring | `prediction.py` | TRIVIAL |

### P2 — Document Only

| # | Item | Deliverable |
|---|------|-------------|
| 6 | Persistence design | `PHASE25_PERSISTENCE_DESIGN.md` |
| 7 | Repository boundaries | Same document |
| 8 | Security constraints for future APIs | Implementation report |

---

## 9. Answer to the Critical Question

> "If we introduce a database, users, paper bankrolls and reputation tomorrow, is there any architectural flaw today that could cause duplicate settlements, fake performance, mutable historical predictions, broken provenance or untrustworthy reputation?"

**YES — one flaw:** Settlement is not idempotent. A retry or replay can produce duplicate settlements, duplicate P&L, and corrupt quarantine/paper metrics.

**Fix required before Phase 3.**

All other concerns (immutability, provenance, proof integrity, trust boundaries, backtest/live separation) are architecturally sound.

---

## 10. Conclusion

The Phase 2 domain model is architecturally correct and persistence-ready. The single critical gap is settlement idempotency — the guarantee that one prediction produces one economic effect. This is a small, targeted fix to the settlement service and quarantine bridge. Once applied, the system is safe for Phase 3 introduction of persistence, users, and financial features.

