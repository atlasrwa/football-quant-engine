# Phase 2 Report — Reproducibility + Prediction Domain Foundation

**Date:** 2026-08-24  
**Status:** COMPLETE  
**Tests before:** 529 passing  
**Tests after:** 628 passing (+99 new, 0 regressions)  
**Files added:** 9 (8 source + 1 test)  
**Files modified:** 0 (existing code untouched)

---

## 1. Objective

Transform the existing quantitative engine into a reproducible prediction platform by establishing canonical domain objects for the full provenance chain:

```
Strategy → DatasetVersion → FeatureVersion → ModelVersion
    → BacktestRun → ValidationRun
    → PredictionEvent → Settlement
```

This phase builds the **domain foundation** without introducing persistence, databases, social features, or web infrastructure.

---

## 2. Architecture Decision: Extension, Not Rewrite

The existing engine survived Phase 0 audit, Phase 1 remediation, and adversarial integrity gate testing (529 tests). Phase 2 was designed to:

1. **Add** a new `src/domain/` module alongside existing code
2. **Bridge** existing types via factories (no modifications to Signal, XBetRecord, etc.)
3. **Preserve** all existing behavior (0 existing files modified)
4. **Enable** future features (paper betting, leaderboards, marketplace) without coupling to them

The new domain layer consumes outputs from the existing engine and produces canonical domain objects.

---

## 3. Module Structure

```
src/domain/
├── __init__.py              Clean public API (re-exports all types)
├── provenance.py            DatasetVersion, FeatureVersion, ModelVersion
├── backtest_run.py          BacktestRun, ValidationRun
├── market.py                MarketDefinition, MarketPrice
├── prediction.py            PredictionEvent (the core Phase 2 deliverable)
├── settlement.py            Settlement (outcome resolution)
├── factories.py             PredictionEventFactory, SettlementFactory
└── provenance_builder.py    ProvenanceBuilder (chain construction)
```

---

## 4. Domain Types Implemented

### 4.1 Provenance Chain (`provenance.py`)

| Type | Purpose | Key Fields |
|------|---------|------------|
| `DatasetVersion` | Immutable snapshot of input data | dataset_id, source, league_id, season, n_matches, date_range, content_hash |
| `FeatureVersion` | Feature computation config | feature_version_id, dataset_id, rolling windows, xmetric coefficients, content_hash |
| `ModelVersion` | Full evaluation context | model_version_id, strategy_id/version/hash, feature_version_id, walk-forward params, content_hash |

Each type has:
- `compute_content_hash()` — deterministic SHA-256 from canonical JSON
- `to_dict()` — JSON-safe serialization
- Frozen immutability

### 4.2 Execution Records (`backtest_run.py`)

| Type | Purpose | Key Fields |
|------|---------|------------|
| `BacktestRun` | Record of a backtest execution | run_id, model_version_id, strategy linkage, results (bets, ROI, drawdown, P&L), content_hash |
| `ValidationRun` | Record of statistical validation | validation_id, backtest_run_id, p_value, ROI, sample_size, effect_size, CI, FDR parameters, status |

Status enums: `BacktestStatus` (RUNNING/COMPLETED/FAILED), `ValidationStatus` (PASSED/FAILED/INSUFFICIENT_DATA)

### 4.3 Market Types (`market.py`)

| Type | Purpose | Key Fields |
|------|---------|------------|
| `MarketDefinition` | Abstract market identity | market_type, line, description, content_hash |
| `MarketPrice` | Specific price observation | match_id, market_type, line, side, price_type, odds, timestamp, source |

Enums: `MarketType` (OVER_UNDER, MATCH_RESULT, BTTS, ASIAN_HANDICAP, CORNERS, CARDS), `PriceSide` (OVER/UNDER/HOME/DRAW/AWAY/YES/NO), `PriceType` (OPENING/ENTRY/CLOSING/LIVE)

### 4.4 PredictionEvent (`prediction.py`)

The core Phase 2 deliverable. Every prediction the system makes becomes a PredictionEvent with:

| Field | Type | Purpose |
|-------|------|---------|
| prediction_id | str (UUID) | Unique identifier |
| strategy_id | str | Strategy that generated this |
| strategy_version | int | Version of the strategy |
| strategy_content_hash | str | Integrity verification |
| model_version_id | str | Full provenance linkage |
| match_id | int | Match being predicted |
| match_date_unix | int | Match timestamp |
| home_team / away_team | str | Match context |
| league_id | int | League context |
| market_type / market_line | str / float | What market |
| direction | str | OVER/UNDER/BACK/LAY |
| entry_odds | float | None | Odds at prediction time |
| model_edge_pct | float | Estimated edge |
| confidence | float | 0-100 score |
| recommended_stake | float | Fraction of bankroll |
| source | PredictionSource | BACKTEST/LIVE_SIGNAL/PAPER_TRADE |
| status | PredictionStatus | PENDING/SETTLED_WIN/SETTLED_LOSS/SETTLED_VOID/EXPIRED |
| proof_hash | str | Pre-commitment SHA-256 |
| created_at / settled_at | str | Lifecycle timestamps |

Properties: `is_settled`, `is_win`  
Static: `compute_proof_hash()` — deterministic pre-commitment hash for proof-of-alpha

### 4.5 Settlement (`settlement.py`)

| Field | Type | Purpose |
|-------|------|---------|
| settlement_id | str | Unique identifier |
| prediction_id | str | Links to PredictionEvent |
| match_id | int | The match that was played |
| outcome | SettlementOutcome | WIN/LOSS/VOID/PUSH |
| actual_total_goals | int | Actual match result |
| actual_result | str | Score string (e.g., "2-1") |
| entry_odds / closing_odds | float | None | For CLV calculation |
| clv_pct | float | None | Real CLV (only if closing odds available) |
| stake | float | Amount staked |
| profit_loss | float | Actual P&L |
| settled_at | str | Settlement timestamp |

Properties: `has_clv`, `beat_closing_line`  
Statics: `compute_clv()`, `compute_profit_loss()`

### 4.6 Factories (`factories.py`)

| Factory | Purpose |
|---------|---------|
| `PredictionEventFactory.from_signal()` | Signal → PredictionEvent (live signals) |
| `PredictionEventFactory.from_backtest_bet()` | Backtest bet → PredictionEvent (already settled) |
| `SettlementFactory.settle_prediction()` | PredictionEvent + outcome → Settlement |

### 4.7 ProvenanceBuilder (`provenance_builder.py`)

Orchestrates construction of the full provenance chain from existing engine types:

```python
builder = ProvenanceBuilder()
dataset_v = builder.create_dataset_version(matches, source="footystats")
feature_v = builder.create_feature_version(dataset_v, config)
model_v = builder.create_model_version(strategy_identity, feature_v)
backtest_run = builder.create_backtest_run(model_v, dataset_v, feature_v, results)
validation_run = builder.create_validation_run(backtest_run, p_value, roi, ...)
```

---

## 5. Design Principles

| Principle | Implementation |
|-----------|----------------|
| Immutability | All types are `@dataclass(frozen=True, slots=True)` |
| Determinism | Content hashes use `json.dumps(sort_keys=True, separators=(",",":"))` + SHA-256 |
| No coupling | Domain types have zero imports from persistence, HTTP, or external services |
| Validation | `__post_init__` validates invariants (odds > 1.0, confidence 0-100, etc.) |
| Serialization | Every type has `to_dict()` returning JSON-safe dicts |
| Bridging | Factories consume existing types without modifying them |
| Provenance | Every PredictionEvent links to strategy_id → model_version_id → full chain |

---

## 6. What This Enables (Not Built Yet)

The PredictionEvent + Settlement foundation enables these future features without further schema changes:

| Feature | How PredictionEvent Supports It |
|---------|--------------------------------|
| Paper betting | Track virtual P&L via Settlement.profit_loss |
| User prediction history | Query by strategy_id + time range |
| Creator reputation | Aggregate win_rate / CLV across Settlements |
| Leaderboards | Rank by ROI / CLV / Sharpe from Settlement data |
| Social feeds | PredictionEvents are the feed items |
| Strategy following | Subscribe to predictions by strategy_id |
| Proof-of-alpha | proof_hash pre-commits before outcome |
| Web3 attestations | proof_hash is on-chain-ready SHA-256 |
| Strategy marketplace | ValidationRun + BacktestRun provide track record |
| CLV tracking | Settlement.clv_pct when closing odds available |

---

## 7. Test Coverage

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| TestDatasetVersion | 7 | Creation, immutability, hash determinism, hash sensitivity, serialization |
| TestFeatureVersion | 7 | Creation, hash determinism, param sensitivity, dataset sensitivity |
| TestModelVersion | 5 | Creation, hash determinism, strategy/window/odds sensitivity |
| TestBacktestRun | 4 | Creation, hash determinism, model sensitivity, status serialization |
| TestValidationRun | 4 | Passed/failed/insufficient states, to_dict |
| TestMarketDefinition | 5 | Creation, hash determinism, line/type sensitivity |
| TestMarketPrice | 6 | Creation, invalid odds, implied probability, validity |
| TestPredictionEvent | 17 | All statuses, validation errors, proof hash, serialization |
| TestSettlement | 14 | All outcomes, CLV computation, P&L, invalid inputs |
| TestPredictionEventFactory | 4 | Signal→prediction, backtest→prediction, unique IDs |
| TestSettlementFactory | 7 | OVER/UNDER win/loss, CLV with/without closing odds, linkage |
| TestProvenanceBuilder | 11 | Full chain construction, all validation gates, linkage |
| TestEndToEndPipeline | 3 | Signal→prediction→settlement, backtest lifecycle, full provenance |
| **Total** | **99** | |

---

## 8. Existing Code Impact

**Zero files modified.** The domain layer is purely additive:

```
Before:                          After:
src/models/    (unchanged)       src/models/    (unchanged)
src/engine/    (unchanged)       src/engine/    (unchanged)
src/features/  (unchanged)       src/features/  (unchanged)
src/backtest/  (unchanged)       src/backtest/  (unchanged)
src/ingestion/ (unchanged)       src/ingestion/ (unchanged)
src/api/       (unchanged)       src/api/       (unchanged)
                                 src/domain/    (NEW - 8 files)
tests/         (529 passing)     tests/         (628 passing, +99)
```

---

## 9. Remaining Work (Phase 3+)

| Item | Phase | Notes |
|------|-------|-------|
| Persistent storage for domain objects | Phase 3 | JSON-file or SQLite initially, then PostgreSQL |
| Strategy lifecycle state machine | Phase 3 | DRAFT → BACKTESTED → VALIDATED → QUARANTINED → LIVE |
| PredictionEvent emission from XMetricBacktester | Phase 3 | Wire factory into backtest run loop |
| Closing odds data feed | Phase 5 | Needed for real CLV in Settlement |
| User/Creator identity | Phase 4 | Links PredictionEvents to users |
| Heuristic Kelly replacement | Phase 3 | Risk-unit tiers for recommended_stake |
| API endpoints for predictions | Phase 3 | REST endpoints consuming domain types |
| Duplicate backtest system consolidation | Phase 3 | Unify under domain model |

---

## 10. Conclusion

Phase 2 establishes the canonical prediction domain model. Every prediction can now be:
- **Traced** back to its exact strategy, dataset, features, and model configuration
- **Verified** via deterministic content hashes at every level
- **Settled** against actual outcomes with proper CLV when closing odds exist
- **Proven** via pre-commitment proof hashes suitable for on-chain attestation

The existing 529-test quantitative engine remains untouched and fully operational. The 99 new tests verify the domain model independently. The system is ready for Phase 3 (persistence + lifecycle + API).
