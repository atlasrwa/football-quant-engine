# Phase 2 Reconnaissance Report

**Date:** 2026-08-24  
**Status:** DOMAIN LAYER IMPLEMENTED — Integration phase next  
**Test suite:** 628 passed, 0 failed (17s)  
**Domain tests:** 99 passed (test_domain.py)

---

## 1. Executive Summary

Phase 2 domain model is **already implemented and tested** in `src/domain/`. The full provenance chain from DatasetVersion through PredictionEvent to Settlement exists as frozen, immutable, deterministically-hashable dataclasses with factory bridges to the existing engine. 99 comprehensive tests pass.

**What remains is INTEGRATION** — connecting the domain layer into the existing execution pipeline so that real predictions produce real PredictionEvents, and real outcomes produce real Settlements.

---

## 2. Current Architecture (Post Phase 1 + Domain Layer)

```
src/
├── models/              ← Original domain: Match, MatchFeatures, StrategyConfig, BacktestResult
├── features/            ← Feature calculators (temporal-leak-free)
├── backtest/            ← WalkForwardEngine (heuristic O/U backtest)
├── engine/
│   ├── xmetrics.py      ← xC/xB/xO (expanding-window, leak-free)
│   ├── evaluator.py     ← Strategy, Condition, Signal, StrategyEvaluator
│   ├── backtest.py      ← XMetricBacktester → XBetRecord, XBacktestResult
│   ├── validator.py     ← StatisticalValidator → ValidationVerdict
│   ├── fdr.py           ← FDRController + QuarantineTracker
│   ├── clv.py           ← CLVCalculator (real CLV from market data)
│   ├── friction.py      ← MarketFrictionConfig, FrictionAdjustedBacktester
│   ├── builder.py       ← StrategyBuilder (fluent + JSON)
│   ├── strategy_identity.py ← StrategyIdentity, StrategyRegistry
│   ├── data/            ← BaseDataLoader, adapters
│   ├── metrics/         ← BookieMetricsCalculator
│   └── signals/         ← CryptoSignalExporter, CommunityBroadcaster, DeepLinker
├── domain/              ← ★ PHASE 2 DOMAIN (NEW)
│   ├── prediction.py    ← PredictionEvent, PredictionStatus, PredictionSource
│   ├── settlement.py    ← Settlement, SettlementOutcome
│   ├── provenance.py    ← DatasetVersion, FeatureVersion, ModelVersion
│   ├── backtest_run.py  ← BacktestRun, ValidationRun
│   ├── market.py        ← MarketDefinition, MarketPrice, MarketType, PriceSide, PriceType
│   ├── factories.py     ← PredictionEventFactory, SettlementFactory
│   └── provenance_builder.py ← ProvenanceBuilder
├── api/                 ← HTTP endpoints (builder compile/result)
```

---

## 3. Domain Model — Implemented Types

### Provenance Chain (reproducibility)

| Type | Location | Purpose |
|------|----------|---------|
| `DatasetVersion` | `src/domain/provenance.py` | Immutable dataset snapshot (source, league, season, content_hash) |
| `FeatureVersion` | `src/domain/provenance.py` | Feature computation config (windows, coefficients, content_hash) |
| `ModelVersion` | `src/domain/provenance.py` | Full evaluation context (strategy + features + backtest params) |
| `BacktestRun` | `src/domain/backtest_run.py` | Execution record with aggregate results |
| `ValidationRun` | `src/domain/backtest_run.py` | Statistical validation record with verdict |

### Market Types

| Type | Location | Purpose |
|------|----------|---------|
| `MarketDefinition` | `src/domain/market.py` | Abstract market (type + line), hashable |
| `MarketPrice` | `src/domain/market.py` | Specific price observation (odds, side, timestamp, source) |
| `MarketType` | `src/domain/market.py` | Enum: OVER_UNDER, MATCH_RESULT, CORNERS, CARDS, etc. |
| `PriceSide` | `src/domain/market.py` | Enum: OVER, UNDER, HOME, DRAW, AWAY |
| `PriceType` | `src/domain/market.py` | Enum: OPENING, ENTRY, CLOSING, LIVE |

### Prediction & Settlement

| Type | Location | Purpose |
|------|----------|---------|
| `PredictionEvent` | `src/domain/prediction.py` | **Canonical atomic prediction** with full provenance |
| `PredictionStatus` | `src/domain/prediction.py` | Lifecycle: PENDING → SETTLED_WIN/LOSS/VOID/EXPIRED |
| `PredictionSource` | `src/domain/prediction.py` | How generated: BACKTEST, LIVE_SIGNAL, PAPER_TRADE |
| `Settlement` | `src/domain/settlement.py` | Outcome resolution: P&L, CLV, actual result |
| `SettlementOutcome` | `src/domain/settlement.py` | Enum: WIN, LOSS, VOID, PUSH |

### Factories (bridge layer)

| Type | Location | Purpose |
|------|----------|---------|
| `PredictionEventFactory` | `src/domain/factories.py` | Creates PredictionEvent from Signal or backtest bet |
| `SettlementFactory` | `src/domain/factories.py` | Settles PredictionEvent against actual outcome |
| `ProvenanceBuilder` | `src/domain/provenance_builder.py` | Constructs full provenance chain from engine types |

---

## 4. What the Domain Layer Already Does

1. **Full provenance chain**: Strategy → Dataset → Features → Model → Backtest → Validation → PredictionEvent → Settlement
2. **Deterministic content hashes**: Every provenance object has a SHA-256 hash computed from its canonical JSON representation
3. **Immutability**: All types are `frozen=True, slots=True` dataclasses
4. **Factory bridges**: `PredictionEventFactory.from_signal()` and `PredictionEventFactory.from_backtest_bet()` bridge existing Signal/XBetRecord to PredictionEvent without modifying existing code
5. **Settlement logic**: `SettlementFactory.settle_prediction()` resolves predictions against actual outcomes with proper CLV computation
6. **Serialization**: All types have `to_dict()` for JSON-safe output
7. **Validation invariants**: Proper `__post_init__` checks on odds > 1.0, confidence [0,100], non-negative stakes, valid directions
8. **Proof-of-alpha**: Deterministic SHA-256 pre-commitment hash on PredictionEvent

---

## 5. What Is NOT Yet Done (Integration Gaps)

The domain objects exist but are not **consumed** by the pipeline. These are the integration points that need wiring:

### Gap 1: Backtest → PredictionEvent emission

`XMetricBacktester._run_fold()` produces `XBetRecord` objects but does NOT emit `PredictionEvent` objects. The factory exists but is never called by the backtester.

**Integration point:** After each `XBetRecord` is created in `_run_fold()`, call `PredictionEventFactory.from_backtest_bet()` to produce the canonical prediction record.

### Gap 2: Live Signal → PredictionEvent emission

`CommunityBroadcaster.run_once()` and `CryptoSignalExporter.dispatch()` produce `SignalPayload` objects but do NOT emit `PredictionEvent`. The factory exists but is never called by the signal dispatch pipeline.

**Integration point:** Before or after dispatch, call `PredictionEventFactory.from_signal()` to produce the canonical prediction.

### Gap 3: Settlement pipeline

No automated settlement exists. The `SettlementFactory` exists but nothing calls it when match results arrive. The quarantine system tracks `paper_pnl` and `paper_bets` as scalars but has no concept of individual prediction records.

**Integration point:** A settlement service that, given a completed match, finds all PENDING predictions for that match and calls `SettlementFactory.settle_prediction()`.

### Gap 4: Provenance chain construction

`ProvenanceBuilder` exists but is never called by the backtest or signal pipeline. When a backtest runs, no `DatasetVersion`/`FeatureVersion`/`ModelVersion`/`BacktestRun` is actually created.

**Integration point:** Wrap the existing `XMetricBacktester.run()` in an orchestrator that creates provenance objects before/after execution.

### Gap 5: Quarantine ↔ PredictionEvent linkage

`QuarantineTracker.update_paper_pnl()` accepts scalar deltas. It should instead be driven by settled PredictionEvents from the paper_trade source.

**Integration point:** When a PAPER_TRADE PredictionEvent is settled, update the quarantine entry from the Settlement P&L.

### Gap 6: Persistence

All domain objects are in-memory only. `StrategyRegistry` is in-memory. No persistence layer exists.

**Not needed yet.** Phase 2 establishes domain correctness. Persistence is Phase 3.

---

## 6. Architectural Placement Decision

PredictionEvent is correctly placed in `src/domain/prediction.py` as a standalone domain module that:

- Has ZERO dependencies on persistence (no DB, no Redis)
- Depends only on the Python standard library (hashlib, json, uuid, datetime, dataclasses, enum)
- Is consumed by factories that bridge FROM existing engine types
- Does NOT modify any existing engine code
- Follows the "extend, don't rewrite" principle

The `src/domain/` package is the correct location. It is architecturally separate from:
- `src/models/` (original domain objects for the O/U backtest)
- `src/engine/` (execution layer)
- `src/backtest/` (legacy backtest)

---

## 7. Existing Object Relationships

```
EXISTING (Phase 0-1)                     NEW (Phase 2 Domain)
═══════════════════                      ═══════════════════
Strategy ──────────────────────────────► (used by PredictionEventFactory)
StrategyIdentity ──────────────────────► strategy_id, strategy_version, content_hash
Signal ────────────────────────────────► PredictionEventFactory.from_signal()
XBetRecord ────────────────────────────► PredictionEventFactory.from_backtest_bet()
Match ─────────────────────────────────► DatasetVersion (via ProvenanceBuilder)
StrategyConfig ────────────────────────► FeatureVersion (via ProvenanceBuilder)
XBacktestResult ───────────────────────► BacktestRun (via ProvenanceBuilder)
ValidationVerdict ─────────────────────► ValidationRun (via ProvenanceBuilder)
CLVCalculator ─────────────────────────► Settlement.compute_clv() (same formula)
QuarantineTracker ─────────────────────► driven by Settlement P&L (gap #5)
CommunityBroadcaster ──────────────────► emits PredictionEvent (gap #2)
```

---

## 8. Test Coverage Summary

| Module | Tests | Status |
|--------|-------|--------|
| Domain types (provenance, market, prediction, settlement) | 73 | PASS |
| Factories (PredictionEventFactory, SettlementFactory) | 11 | PASS |
| ProvenanceBuilder | 11 | PASS |
| End-to-end pipeline (signal→prediction→settlement) | 4 | PASS |
| **Total domain tests** | **99** | **ALL PASS** |
| **Full suite** | **628** | **ALL PASS** |

---

## 9. Recommended Next Steps (Integration Phase)

Priority order for wiring the domain layer into the execution pipeline:

| # | Action | Risk | Effort |
|---|--------|------|--------|
| 1 | Wire `PredictionEventFactory` into `XMetricBacktester` | LOW — additive, no behavior change | SMALL |
| 2 | Wire `ProvenanceBuilder` into backtest orchestration | LOW — additive | SMALL |
| 3 | Wire `PredictionEventFactory` into signal dispatch | LOW — additive | SMALL |
| 4 | Create settlement service (match result → settle predictions) | MEDIUM — new logic | MEDIUM |
| 5 | Wire settlement into quarantine P&L updates | MEDIUM — behavioral change | MEDIUM |
| 6 | Integration tests: full pipeline provenance chain | LOW — test-only | MEDIUM |

**Constraints:**
- Every change must keep all 628 tests passing
- No modification to existing engine behavior (extend only)
- No persistence layer yet (in-memory stores acceptable)
- No external infrastructure (no Postgres, no Redis, no DuckDB)

---

## 10. Conclusion

The Phase 2 domain model is **architecturally complete and tested**. The reconnaissance confirms:

1. All 10 target domain concepts from the Phase 2 spec are implemented
2. The factory bridge pattern correctly decouples domain from engine
3. No existing engine code was modified
4. The provenance chain links Strategy → Dataset → Features → Model → Backtest → Validation → Prediction → Settlement
5. All 628 tests pass

**The next phase of work is INTEGRATION** — wiring the factories into the existing pipeline so that domain objects are actually produced during execution. This is a controlled, additive process with no risk to existing behavior.
