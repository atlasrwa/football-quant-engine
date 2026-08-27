# Phase 3.2 Test Matrix

## Summary

| Suite | Count | Status |
|-------|-------|--------|
| Existing engine tests | 727 | ALL PASS |
| Phase 3.1 integration tests | 104 | ALL PASS |
| Phase 3.2 integration tests | 46 | ALL PASS |
| **Total** | **877** | **ALL PASS** |

## Phase 3.2 Tests (46)

### Market Prices (tests/integration/test_market_prices.py) — 6 tests
- [x] Multiple time-series observations allowed (no uniqueness blocking)
- [x] Provider identity preserved (multiple sources coexist)
- [x] NULL odds NOT allowed (NOT NULL constraint)
- [x] Odds must exceed 1.0 (CHECK constraint)
- [x] Closing price lookup returns most recent
- [x] Immutability: UPDATE blocked (RLS)

### Provenance Chain (tests/integration/test_provenance.py) — 11 tests

**Dataset Versions (4):**
- [x] Create with computed content_hash
- [x] Same content deduplicates (returns existing)
- [x] Different content produces different hash
- [x] Immutability: UPDATE blocked (RLS)

**Feature Versions (4):**
- [x] Create with correct content_hash
- [x] Same config deduplicates
- [x] Different config produces new version
- [x] Dataset relationship preserved

**Model Versions (3):**
- [x] Create with deterministic hash
- [x] Same config deduplicates
- [x] Provenance chain integrity (strategy + feature links)

### Backtest Persistence (tests/integration/test_backtest_persistence.py) — 14 tests

**Backtest Runs (6):**
- [x] Create in RUNNING status
- [x] Complete with metrics
- [x] Same user dedup (UniqueViolation)
- [x] Different users independently allowed
- [x] Completed run immutable (trigger blocks)
- [x] Full provenance chain queryable

**Backtest Bets (4):**
- [x] Insert bet record
- [x] NULL CLV preserved (never fabricated)
- [x] Batch insert
- [x] Immutability: UPDATE blocked (RLS)

**Cross-User Isolation (2):**
- [x] User cannot see other user's runs
- [x] User cannot see other user's bets

**Hashing Compatibility (2 inline):**
- [x] Content hash matches BacktestRun.compute_content_hash()
- [x] Deterministic across invocations

### Canonical Hashing (tests/integration/test_hashing.py) — 15 tests

**Dataset Hashing (5):**
- [x] Deterministic
- [x] Order-independent (sorted internally)
- [x] Different IDs differ
- [x] Matches domain object method
- [x] Is valid SHA-256 (64 hex chars)

**Feature Version Hashing (5):**
- [x] Deterministic
- [x] Config change detected
- [x] Dataset change detected
- [x] xMetric coefficients included
- [x] Matches domain object method

**Model Version Hashing (3):**
- [x] Deterministic
- [x] Strategy change detected
- [x] Window change detected
- [x] Matches domain object method

**Backtest Run Hashing (3):**
- [x] Deterministic
- [x] Different inputs differ
- [x] Matches domain object method

## Invariant Preservation

All 14 existing invariants (I1-I14) remain green — verified by the 727 existing engine tests passing without modification.
