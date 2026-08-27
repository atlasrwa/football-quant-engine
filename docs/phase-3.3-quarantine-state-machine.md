# Phase 3.3 Quarantine State Machine

## States

```
PENDING_QUARANTINE ──→ PROMOTED (after 90 days + PASSED validation)
         │
         └──────────→ REJECTED (failed paper trading / manual rejection)
```

## Transitions

| From | To | Conditions | Who |
|------|-----|-----------|-----|
| (none) | PENDING_QUARANTINE | Strategy version exists; user owns it | User via service |
| PENDING_QUARANTINE | PROMOTED | quarantine_until <= NOW() AND latest validation PASSED | Service (QuarantineService.promote) |
| PENDING_QUARANTINE | REJECTED | Any time during quarantine | Service (QuarantineService.reject) |
| PROMOTED | (any) | **FORBIDDEN** — terminal state | Trigger blocks |
| REJECTED | (any) | **FORBIDDEN** — terminal state | Trigger blocks |

## Key Properties

1. **Version-specific**: UNIQUE(strategy_id, strategy_version). V1 rejected ≠ V2 rejected.
2. **90-day minimum**: `quarantine_until = entered_at + 90 days`. Cannot promote before.
3. **Validation required**: Promotion requires `validation_runs` with status='PASSED' for the same strategy+version.
4. **Immutable after terminal**: Once PROMOTED or REJECTED, the trigger prevents any further status change.
5. **Provenance fields immutable**: strategy_id, strategy_version, user_id, entered_at, quarantine_until cannot change after creation.
6. **Paper P&L tracking**: `paper_pnl` and `paper_bets` accumulate during quarantine (updated by quarantine bridge).

## API

```
POST /api/v1/quarantine/enter
  → Creates PENDING_QUARANTINE entry with quarantine_until = NOW() + 90 days

POST /api/v1/quarantine/{strategy_id}/{version}/promote
  → Validates: PENDING + 90 days elapsed + PASSED validation
  → Transitions to PROMOTED

GET /api/v1/quarantine/{strategy_id}/{version}
  → Returns current quarantine state
```

## Integration with Existing Engine

The existing `QuarantineTracker` (src/engine/fdr.py) and its 90-day logic
are NOT modified. The database stores the state; the QuarantineService
enforces the same rules as the engine's QuarantineTracker but via SQL.
