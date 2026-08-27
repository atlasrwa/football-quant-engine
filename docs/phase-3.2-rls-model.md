# Phase 3.2 RLS Model

## Table Classification

| Table | Class | Read Policy | Write Policy | Force RLS |
|-------|-------|-------------|--------------|-----------|
| market_prices | B (System) | All authenticated | System/admin only | Yes |
| dataset_versions | B (System) | All authenticated | System/admin only | Yes |
| feature_versions | B (System) | All authenticated | System/admin only | Yes |
| model_versions | B (System) | All authenticated | System/admin only | Yes |
| match_features | B (System) | All authenticated | System/admin only | Yes |
| backtest_runs | D (User+System) | Owner + admin | Owner + admin | Yes |
| backtest_bets | D (User+System) | Via parent run owner | Via parent run owner | Yes |

## Policy Details

### CLASS B (System-owned, publicly readable)

Applied to: `market_prices`, `dataset_versions`, `feature_versions`, `model_versions`, `match_features`

```sql
-- Anyone can read (public computation data)
POLICY *_select_all FOR SELECT USING (TRUE);

-- Only system/admin can write
POLICY *_insert_system FOR INSERT WITH CHECK (is_admin_or_system());
```

No UPDATE or DELETE policies exist — combined with INSERT-only triggers, data is immutable.

### CLASS D (User-owned)

**backtest_runs:**
```sql
-- Owner or admin can read
POLICY br_select_own FOR SELECT
    USING (user_id = current_app_user_id() OR is_admin_or_system());

-- Owner or admin can insert
POLICY br_insert_own FOR INSERT
    WITH CHECK (user_id = current_app_user_id() OR is_admin_or_system());

-- Owner or admin can update (status transitions only — trigger controls what changes)
POLICY br_update_own FOR UPDATE
    USING (user_id = current_app_user_id() OR is_admin_or_system());
```

**backtest_bets (inherits via parent run):**
```sql
-- Visible only if parent run is owned by current user
POLICY bb_select_own FOR SELECT
    USING (EXISTS (SELECT 1 FROM backtest_runs br
                   WHERE br.id = backtest_bets.run_id
                     AND (br.user_id = current_app_user_id() OR is_admin_or_system())));

-- Insertable only if parent run is owned by current user
POLICY bb_insert_own FOR INSERT
    WITH CHECK (EXISTS (SELECT 1 FROM backtest_runs br
                        WHERE br.id = backtest_bets.run_id
                          AND (br.user_id = current_app_user_id() OR is_admin_or_system())));
```

## Cross-User Isolation

Tested and verified:
- User A cannot SELECT User B's backtest_runs
- User A cannot SELECT User B's backtest_bets (even by knowing the run_id)
- System/admin can see all runs and bets
- Public data (market_prices, provenance tables) is readable by all authenticated users

## Immutability Enforcement

RLS + triggers provide defense-in-depth:
1. **RLS** prevents unauthorized UPDATE/DELETE (returns 0 rows affected)
2. **Triggers** catch any UPDATE/DELETE that bypasses RLS (e.g., superuser) and raise exceptions
3. `backtest_runs` has controlled mutability: RUNNING→COMPLETED/FAILED transitions allowed, but provenance fields and completed runs are fully immutable
