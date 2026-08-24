# Phase 2.5 Persistence Design

**Date:** 2026-08-24  
**Status:** DESIGN DOCUMENT — blueprint for Phase 3 implementation  
**Purpose:** Define the conceptual persistence model so that Phase 3 can introduce a database without architectural surprises.

---

## 1. Design Principles

1. **Domain objects remain persistence-ignorant** — no SQLAlchemy, no ORM decorators, no database imports in `src/domain/`
2. **Repository pattern** — thin interfaces between domain and storage
3. **Append-only where possible** — immutable records create audit trails naturally
4. **Idempotency keys** — unique constraints prevent duplicates at the storage layer
5. **No premature implementation** — this document defines WHAT, not HOW (no Postgres DDL yet)

---

## 2. Strategy

### Identity

```
Primary Key: strategy_id (UUID)
Version Key: (strategy_id, strategy_version) — composite unique
```

### Characteristics

| Property | Value |
|----------|-------|
| Mutability | **Immutable per version** — changes create new version |
| Versioning | Yes — monotonically increasing integer |
| Append-only | Yes — versions are appended, never modified |
| Content hash | SHA-256 of canonical strategy JSON (deduplication key) |

### Fields

| Field | Type | Constraint |
|-------|------|------------|
| strategy_id | UUID | NOT NULL |
| strategy_version | int | NOT NULL, >= 1 |
| name | str | NOT NULL |
| content_hash | str(64) | NOT NULL, index |
| created_at | timestamptz | NOT NULL |
| schema_version | str | NOT NULL |
| parent_version | int | NULL (first version has no parent) |

### Unique Constraints

- `UNIQUE(strategy_id, strategy_version)`
- `INDEX(content_hash)` — for dedup lookup

### Audit Fields

- `created_at` — when this version was registered

---

## 3. Prediction

### Identity

```
Primary Key: prediction_id (UUID)
Idempotency: prediction_id is globally unique
```

### Characteristics

| Property | Value |
|----------|-------|
| Mutability | **Immutable after creation** (frozen dataclass) |
| Versioning | No — predictions are never modified |
| Append-only | Yes — write once, read many |
| Settlement link | 1:1 with Settlement (via prediction_id FK) |

### Fields

| Field | Type | Constraint |
|-------|------|------------|
| prediction_id | UUID | PRIMARY KEY |
| strategy_id | UUID | NOT NULL, FK → Strategy |
| strategy_version | int | NOT NULL |
| strategy_content_hash | str(64) | NOT NULL |
| model_version_id | UUID | NULL (optional provenance link) |
| match_id | int | NOT NULL, index |
| match_date_unix | bigint | NOT NULL |
| home_team | str | NOT NULL |
| away_team | str | NOT NULL |
| league_id | int | NOT NULL, index |
| market_type | str | NOT NULL |
| market_line | float | NULL |
| direction | str | NOT NULL, CHECK IN ('OVER','UNDER','BACK','LAY') |
| entry_odds | float | NULL (None = odds unavailable) |
| model_edge_pct | float | NOT NULL |
| confidence | float | NOT NULL, CHECK [0, 100] |
| recommended_stake | float | NOT NULL, CHECK >= 0 |
| source | str | NOT NULL, CHECK IN ('BACKTEST','LIVE_SIGNAL','PAPER_TRADE') |
| status | str | NOT NULL |
| proof_hash | str(64) | NOT NULL |
| created_at | timestamptz | NOT NULL |
| settled_at | timestamptz | NULL |

### Unique Constraints

- `PRIMARY KEY(prediction_id)`
- `INDEX(match_id)` — for batch settlement lookup
- `INDEX(strategy_id, created_at)` — for strategy history
- `INDEX(source, status)` — for pending paper trade queries

### Immutability Rule

Once written, no field may be updated. The `status` and `settled_at` fields are set at creation time (PENDING for live/paper, SETTLED_* for backtest) and never modified. Settlement state is tracked via the separate Settlement table.

---

## 4. Settlement

### Identity

```
Primary Key: settlement_id (UUID)
Unique Constraint: prediction_id (one settlement per prediction)
```

### Characteristics

| Property | Value |
|----------|-------|
| Mutability | **Immutable after creation** |
| Versioning | No |
| Append-only | Yes |
| Idempotency | `UNIQUE(prediction_id)` — enforces one-settlement-per-prediction at DB level |

### Fields

| Field | Type | Constraint |
|-------|------|------------|
| settlement_id | UUID | PRIMARY KEY |
| prediction_id | UUID | NOT NULL, UNIQUE, FK → Prediction |
| match_id | int | NOT NULL |
| outcome | str | NOT NULL, CHECK IN ('WIN','LOSS','VOID','PUSH') |
| actual_total_goals | int | NOT NULL |
| actual_result | str | NOT NULL |
| entry_odds | float | NULL |
| closing_odds | float | NULL |
| clv_pct | float | NULL |
| stake | float | NOT NULL, CHECK >= 0 |
| profit_loss | float | NOT NULL |
| settled_at | timestamptz | NOT NULL |

### Unique Constraints

- `PRIMARY KEY(settlement_id)`
- **`UNIQUE(prediction_id)`** — THE critical constraint. Prevents duplicate settlements at the storage layer, complementing the service-level idempotency check.
- `INDEX(match_id)` — for match-based queries

### Idempotency at Storage Layer

```sql
-- Attempting to insert a duplicate settlement:
INSERT INTO settlement (..., prediction_id, ...) VALUES (...)
ON CONFLICT (prediction_id) DO NOTHING;
-- Returns 0 rows affected = idempotent no-op
```

---

## 5. Backtest Run

### Identity

```
Primary Key: run_id (UUID)
Content Hash: (model_version_id, dataset_id) for deduplication
```

### Characteristics

| Property | Value |
|----------|-------|
| Mutability | **Immutable after completion** |
| Versioning | No |
| Append-only | Yes |
| Status transition | RUNNING → COMPLETED / FAILED (one-way) |

### Fields

| Field | Type | Constraint |
|-------|------|------------|
| run_id | UUID | PRIMARY KEY |
| model_version_id | UUID | NOT NULL |
| strategy_id | UUID | NOT NULL |
| strategy_version | int | NOT NULL |
| dataset_id | UUID | NOT NULL |
| feature_version_id | UUID | NOT NULL |
| status | str | NOT NULL |
| total_bets | int | NOT NULL |
| net_roi_pct | float | NOT NULL |
| win_rate | float | NOT NULL |
| max_drawdown_pct | float | NOT NULL |
| avg_model_edge_pct | float | NOT NULL |
| total_profit_loss | float | NOT NULL |
| n_folds | int | NOT NULL |
| content_hash | str(64) | NOT NULL |
| started_at | timestamptz | NOT NULL |
| completed_at | timestamptz | NULL |

### Unique Constraints

- `PRIMARY KEY(run_id)`
- `INDEX(strategy_id, started_at)`
- `INDEX(content_hash)` — dedup: same model + dataset = same run

---

## 6. Validation Run

### Identity

```
Primary Key: validation_id (UUID)
```

### Characteristics

| Property | Value |
|----------|-------|
| Mutability | **Immutable** |
| Versioning | No |
| Append-only | Yes |

### Fields

| Field | Type | Constraint |
|-------|------|------------|
| validation_id | UUID | PRIMARY KEY |
| backtest_run_id | UUID | NOT NULL, FK → BacktestRun |
| strategy_id | UUID | NOT NULL |
| strategy_version | int | NOT NULL |
| status | str | NOT NULL |
| p_value | float | NOT NULL |
| roi_pct | float | NOT NULL |
| sample_size | int | NOT NULL |
| effect_size | float | NOT NULL |
| confidence_interval_lower | float | NOT NULL |
| confidence_interval_upper | float | NOT NULL |
| min_sample_required | int | NOT NULL |
| min_roi_required | float | NOT NULL |
| max_p_value | float | NOT NULL |
| fdr_submission_count | int | NOT NULL |
| fdr_adjusted_threshold | float | NULL |
| reason | str | NOT NULL |
| validated_at | timestamptz | NOT NULL |

---

## 7. Provenance Objects (Dataset, Feature, Model Versions)

### DatasetVersion

| Property | Value |
|----------|-------|
| Primary Key | dataset_id (UUID) |
| Immutable | Yes |
| Content hash | SHA-256 of sorted match_id list |

### FeatureVersion

| Property | Value |
|----------|-------|
| Primary Key | feature_version_id (UUID) |
| Immutable | Yes |
| FK | dataset_id → DatasetVersion |
| Content hash | SHA-256 of (dataset_id + feature params) |

### ModelVersion

| Property | Value |
|----------|-------|
| Primary Key | model_version_id (UUID) |
| Immutable | Yes |
| FK | feature_version_id → FeatureVersion |
| Content hash | SHA-256 of (strategy hash + feature version + backtest params) |

### Storage Decision

Provenance objects are **derivable** — they can be reconstructed from inputs. Storage is optional for Phase 3. They can be persisted for audit/lookup efficiency but are not required for correctness.

---

## 8. Mutable State: QuarantineEntry

### Identity

```
Primary Key: strategy_name (str) — currently strategy_id in bridge usage
```

### Characteristics

| Property | Value |
|----------|-------|
| Mutability | **MUTABLE** — paper_pnl and paper_bets accumulate |
| Versioning | No |
| Append-only | No — fields are updated in place |
| Derivable | Yes — CAN be reconstructed from Settlement records |

### Fields

| Field | Type | Constraint |
|-------|------|------------|
| strategy_name | str | PRIMARY KEY |
| status | str | NOT NULL, CHECK IN ('PENDING_QUARANTINE','PROMOTED','REJECTED') |
| entry_date | timestamptz | NOT NULL |
| promotion_date | timestamptz | NULL |
| paper_pnl | float | NOT NULL, default 0 |
| paper_bets | int | NOT NULL, default 0 |

### Reconstruction Guarantee

```
paper_pnl = SUM(settlement.profit_loss) 
            WHERE prediction.strategy_id = this.strategy_name
            AND prediction.source = 'PAPER_TRADE'
            AND settlement.outcome IN ('WIN', 'LOSS')
```

This means QuarantineEntry is a **materialized view** that can be rebuilt from settlements. This is critical for data integrity — if paper_pnl ever drifts, it can be corrected from the authoritative Settlement table.

---

## 9. Repository Boundaries

### Required for Phase 3

| Repository | Responsibility |
|------------|---------------|
| `PredictionRepository` | Store, retrieve, existence check, match-based queries |
| `SettlementRepository` | Store (with UNIQUE prediction_id), retrieve, strategy queries |

### Optional for Phase 3

| Repository | Responsibility | Reason |
|------------|---------------|--------|
| `StrategyRepository` | Persist registry across restarts | Only if registry needs durability |
| `BacktestRepository` | Store backtest results | Only for historical reporting |
| `ProvenanceRepository` | Store provenance chain | Only for audit trail |

### Not Needed

| What | Why |
|------|-----|
| `QuarantineRepository` | QuarantineEntry is derivable from settlements |
| `SignalRepository` | Signals are transient; PredictionEvent is the durable record |
| `FeatureRepository` | Features are recomputable from data + config |

---

## 10. Interface Design (Abstract)

```python
from abc import ABC, abstractmethod
from typing import List, Optional

class PredictionRepository(ABC):
    """Store and retrieve PredictionEvents."""

    @abstractmethod
    def save(self, prediction: PredictionEvent) -> None: ...

    @abstractmethod
    def get_by_id(self, prediction_id: str) -> Optional[PredictionEvent]: ...

    @abstractmethod
    def exists(self, prediction_id: str) -> bool: ...

    @abstractmethod
    def get_pending_for_match(self, match_id: int) -> List[PredictionEvent]: ...

    @abstractmethod
    def get_by_strategy(self, strategy_id: str) -> List[PredictionEvent]: ...


class SettlementRepository(ABC):
    """Store and retrieve Settlements. Enforces one-per-prediction."""

    @abstractmethod
    def save(self, settlement: Settlement) -> None: ...
    # Raises if prediction_id already has a settlement (unique constraint)

    @abstractmethod
    def get_by_prediction_id(self, prediction_id: str) -> Optional[Settlement]: ...

    @abstractmethod
    def exists_for_prediction(self, prediction_id: str) -> bool: ...

    @abstractmethod
    def get_by_match(self, match_id: int) -> List[Settlement]: ...

    @abstractmethod
    def get_by_strategy(self, strategy_id: str) -> List[Settlement]: ...
```

These interfaces are NOT implemented in Phase 2.5. They are documented here as the contract for Phase 3.

---

## 11. Relationship Diagram

```
Strategy (strategy_id, version)
    │
    ├──→ PredictionEvent (prediction_id)
    │         │
    │         └──→ Settlement (settlement_id) [UNIQUE prediction_id]
    │
    ├──→ BacktestRun (run_id)
    │         │
    │         └──→ ValidationRun (validation_id)
    │
    └──→ ModelVersion (model_version_id)
              │
              ├──→ FeatureVersion (feature_version_id)
              │         │
              │         └──→ DatasetVersion (dataset_id)
              │
              └──→ BacktestRun (via model_version_id)
```

---

## 12. Migration Strategy (Phase 3)

1. **Implement in-memory repositories** that wrap current dict-based stores with the repository interface
2. **Add PostgreSQL implementations** behind the same interfaces
3. **Switch via dependency injection** — `PredictionSettlementService` accepts repository in constructor
4. **Run dual-write** during migration to verify correctness
5. **Add UNIQUE constraint on Settlement.prediction_id** as the database-level idempotency guard

### Migration Order

1. SettlementRepository (most critical — economic integrity)
2. PredictionRepository (needed for settlement queries)
3. StrategyRepository (for durability across restarts)
4. BacktestRepository + ProvenanceRepository (for reporting)

---

## 13. Summary

| Object | Immutable | Append-Only | Unique Key | Versioned | Derivable |
|--------|-----------|-------------|------------|-----------|-----------|
| Strategy | per version | Yes | (id, version) | Yes | No |
| PredictionEvent | Yes | Yes | prediction_id | No | No |
| Settlement | Yes | Yes | settlement_id + UNIQUE(prediction_id) | No | No |
| BacktestRun | Yes | Yes | run_id | No | No |
| ValidationRun | Yes | Yes | validation_id | No | No |
| DatasetVersion | Yes | Yes | dataset_id | No | Yes (from data) |
| FeatureVersion | Yes | Yes | feature_version_id | No | Yes (from config) |
| ModelVersion | Yes | Yes | model_version_id | No | Yes (from strategy+features) |
| QuarantineEntry | No | No | strategy_name | No | Yes (from settlements) |

The architecture is persistence-ready. No code changes are needed in Phase 2.5 — only this design document.

