# Phase 3.4 Security Model

## RLS (Row Level Security)

All Phase 3.4 tables use ENABLE ROW LEVEL SECURITY and FORCE ROW LEVEL SECURITY.

### broadcast_logs (CLASS D — User+System)

| Operation | Policy |
|-----------|--------|
| SELECT | user_id = current_app_user_id() OR is_admin_or_system() |
| INSERT | user_id = current_app_user_id() OR is_admin_or_system() |
| UPDATE | user_id = current_app_user_id() OR is_admin_or_system() (trigger blocks) |
| DELETE | user_id = current_app_user_id() OR is_admin_or_system() (trigger blocks) |

### attestation_commitments (CLASS D — via prediction owner)

| Operation | Policy |
|-----------|--------|
| SELECT | prediction owner OR admin/system |
| INSERT | admin/system OR prediction owner |
| UPDATE | prediction owner OR admin/system (trigger blocks) |
| DELETE | prediction owner OR admin/system (trigger blocks) |

### attestation_reveals (CLASS D — via prediction owner)

| Operation | Policy |
|-----------|--------|
| SELECT | prediction owner OR admin/system |
| INSERT | admin/system OR prediction owner |
| UPDATE | prediction owner OR admin/system (trigger blocks) |
| DELETE | prediction owner OR admin/system (trigger blocks) |

Note: UPDATE/DELETE policies exist to allow RLS to match the row so the immutability trigger can produce a clear error. Without these policies, FORCE RLS would silently return 0 affected rows.

## Trust Boundaries

### Broadcast Trust Gate

The server derives broadcast eligibility from authoritative persisted state:

1. Prediction exists
2. Prediction belongs to authenticated user
3. Prediction's strategy/version has quarantine record
4. Quarantine status = PROMOTED
5. Channel is supported

**The client NEVER asserts:** fdr_validated, promoted, eligible, proof_hash, closing_odds, settlement outcome, CLV, P&L, validation status.

### Attestation Trust Boundaries

**Commitment:**
- commitment_hash is ALWAYS server-computed
- Client provides only prediction_id
- Must be created BEFORE settlement (enforced by checking settlement existence)
- Cross-user operations blocked by ownership check

**Reveal:**
- All settlement fields (outcome, closing_odds, profit_loss, clv_pct) are server-derived
- Client provides only prediction_id
- Requires existing commitment
- Requires existing settlement
- Cross-user operations blocked by ownership check

## Immutability Enforcement

All Phase 3.4 tables are INSERT-only. Two layers enforce this:

1. **RLS UPDATE/DELETE policies** — allow row to be found by authenticated owner
2. **Database triggers** — `prevent_modification()` raises exception on UPDATE/DELETE

Corrections occur through new events/records, never mutations.

## Idempotency

| Entity | Uniqueness Constraint | Behavior |
|--------|----------------------|----------|
| Broadcast | (prediction_id, channel, COALESCE(destination, '')) | Returns existing on duplicate |
| Commitment | UNIQUE(prediction_id) | Returns existing on duplicate |
| Reveal | UNIQUE(commitment_id) | Returns existing on duplicate |

Database uniqueness constraints are the FINAL authority. Python-level checks provide fast-path detection.

## Audit Trail

All operations emit events to the append-only event_log:

| Event | Trigger |
|-------|---------|
| BROADCAST_DISPATCHED | Successful dispatch |
| BROADCAST_FAILED | Failed dispatch |
| ATTESTATION_COMMITTED | Commitment created |
| ATTESTATION_REVEALED | Reveal created |
| ATTESTATION_CHAIN_SUBMITTED | Future on-chain submission |

Events are emitted in the same transaction as the business operation.
