# Phase 3.4 Migration Guide

## Migrations

| Number | File | Purpose |
|--------|------|---------|
| 0034 | 0034_create_broadcast_logs.sql | broadcast_logs table + indexes |
| 0035 | 0035_create_attestation_commitments.sql | attestation_commitments table + indexes |
| 0036 | 0036_create_attestation_reveals.sql | attestation_reveals table + indexes |
| 0037 | 0037_create_phase_3_4_rls.sql | RLS policies (ENABLE + FORCE) |
| 0038 | 0038_create_phase_3_4_triggers.sql | Immutability triggers |

## Application Order

Migrations must be applied in order: 0034 → 0035 → 0036 → 0037 → 0038.

0035 depends on 0034 (broadcast_logs must exist before policies reference it).
0036 depends on 0035 (attestation_reveals FK → attestation_commitments).
0037 depends on 0034-0036 (policies reference all three tables).
0038 depends on 0034-0036 (triggers target all three tables).

## Prerequisites

- PostgreSQL 16
- Migrations 0001–0033 already applied
- `prevent_modification()` function exists (from migration 0022)
- RLS helper functions exist (from migration 0003)

## Running Migrations

```bash
source .venv/bin/activate
python migrations/run_migrations.py
```

## Rollback

To reverse Phase 3.4 (in reverse order):

```sql
-- Remove triggers
DROP TRIGGER IF EXISTS trg_ar_no_delete ON attestation_reveals;
DROP TRIGGER IF EXISTS trg_ar_no_update ON attestation_reveals;
DROP TRIGGER IF EXISTS trg_ac_no_delete ON attestation_commitments;
DROP TRIGGER IF EXISTS trg_ac_no_update ON attestation_commitments;
DROP TRIGGER IF EXISTS trg_bl_no_delete ON broadcast_logs;
DROP TRIGGER IF EXISTS trg_bl_no_update ON broadcast_logs;

-- Remove RLS policies
DROP POLICY IF EXISTS ar_delete_blocked ON attestation_reveals;
DROP POLICY IF EXISTS ar_update_blocked ON attestation_reveals;
DROP POLICY IF EXISTS ar_insert_system ON attestation_reveals;
DROP POLICY IF EXISTS ar_select_own ON attestation_reveals;
DROP POLICY IF EXISTS ac_delete_blocked ON attestation_commitments;
DROP POLICY IF EXISTS ac_update_blocked ON attestation_commitments;
DROP POLICY IF EXISTS ac_insert_system ON attestation_commitments;
DROP POLICY IF EXISTS ac_select_own ON attestation_commitments;
DROP POLICY IF EXISTS bl_delete_blocked ON broadcast_logs;
DROP POLICY IF EXISTS bl_update_blocked ON broadcast_logs;
DROP POLICY IF EXISTS bl_insert_own ON broadcast_logs;
DROP POLICY IF EXISTS bl_select_own ON broadcast_logs;

-- Drop tables (reverse dependency order)
DROP TABLE IF EXISTS attestation_reveals;
DROP TABLE IF EXISTS attestation_commitments;
DROP TABLE IF EXISTS broadcast_logs;
```

## Backward Compatibility

- All existing tables unchanged
- All existing migrations unchanged (0001–0033)
- CLI continues working
- In-memory repositories continue working
- Existing quant engine unaffected
- No blockchain dependency introduced
