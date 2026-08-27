# Phase 3.4 Codebase Assessment

## Overview

Phase 3.4 introduces two bounded contexts — **Signal Dispatch** and **Attestation** — to the Football Quant Engine platform. These contexts turn authoritative predictions into auditable outputs and cryptographically verifiable provenance.

## Architecture Position

```
QUANT ENGINE → PREDICTION → QUARANTINE/VALIDATION → PROMOTION → SETTLEMENT → PAPER LEDGER → BROADCAST → ATTESTATION → OPTIONAL FUTURE BLOCKCHAIN
```

## Existing Architecture (Phases 3.1–3.3)

- **Backend**: Python FastAPI + asyncpg + PostgreSQL 16
- **Pattern**: API Routes → Services (conn-based) → Repositories (conn-based) → PostgreSQL
- **Security**: RLS with `SET LOCAL app.user_id/app.user_role` + helper functions + FORCE ROW LEVEL SECURITY
- **Immutability**: `prevent_modification()` trigger function for INSERT-only tables
- **Hashing**: Canonical JSON (sort_keys=True, compact separators) + SHA-256
- **Idempotency**: DB UNIQUE constraints + check/store pattern
- **Events**: `EventService.emit()` within same transaction as business operation

## Phase 3.4 Integration Points

1. **PredictionService** — provides authoritative prediction data for broadcasts
2. **QuarantineService** — provides PROMOTED status for trust gating
3. **SettlementService** — provides authoritative settlement data for reveals
4. **EventService** — extended with 6 new event types
5. **RLS helper functions** — reused (`current_app_user_id()`, `is_admin_or_system()`)
6. **prevent_modification()** — reused for immutability triggers

## Conceptual Model

```
PREDICTION
     │
     ├──────────────→ BROADCAST
     │                    │
     │                    ├── Web
     │                    ├── Mobile
     │                    ├── Telegram
     │                    ├── Discord
     │                    ├── Email
     │                    └── Webhook
     │
     └──────────────→ ATTESTATION
                          │
                          ├── COMMIT (before settlement)
                          │
                          └── REVEAL (after settlement)
                                 │
                                 └── Optional blockchain
```

**Prediction ≠ Broadcast ≠ Delivery Attempt ≠ Attestation**

These are DISTINCT concepts with separate lifecycles and persistence.

## Files Created

| File | Purpose |
|------|---------|
| `migrations/0034_create_broadcast_logs.sql` | broadcast_logs table |
| `migrations/0035_create_attestation_commitments.sql` | attestation_commitments table |
| `migrations/0036_create_attestation_reveals.sql` | attestation_reveals table |
| `migrations/0037_create_phase_3_4_rls.sql` | RLS policies |
| `migrations/0038_create_phase_3_4_triggers.sql` | Immutability triggers |
| `src/persistence/pg_broadcast_repository.py` | Broadcast repository |
| `src/persistence/pg_attestation_repository.py` | Attestation repository |
| `src/persistence/broadcast_hashing.py` | Canonical hashing |
| `src/services/broadcast_service.py` | BroadcastService |
| `src/services/attestation_service.py` | AttestationService |
| `src/services/dispatch/__init__.py` | Dispatch package |
| `src/services/dispatch/models.py` | DispatchResult model |
| `src/services/dispatch/dispatcher.py` | SignalDispatcher |
| `src/services/dispatch/adapters.py` | Channel adapters |
| `src/api/routes/broadcasts.py` | Broadcast API endpoints |
| `src/api/routes/attestations.py` | Attestation API endpoints |
| `tests/integration/test_phase34_broadcast.py` | Broadcast tests |
| `tests/integration/test_phase34_attestation.py` | Attestation tests |
| `tests/integration/test_phase34_concurrency.py` | Concurrency tests |
| `tests/integration/test_phase34_hashing.py` | Hashing tests |

## Files Modified

| File | Change |
|------|--------|
| `src/persistence/events.py` | Added 6 EventTypes |
| `src/api/app.py` | Registered 2 new routers |

## Quant Engine Changes

**NONE**. No files in `src/models/`, `src/features/`, `src/backtest/`, `src/engine/`, `src/domain/`, `src/ingestion/`, `src/serializer.py`, or `src/cli.py` were modified.
