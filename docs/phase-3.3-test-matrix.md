# Phase 3.3 Test Matrix

## Summary

| Suite | Count | Status |
|-------|-------|--------|
| Existing engine tests | 727 | ALL PASS |
| Phase 3.1 integration tests | 104 | ALL PASS |
| Phase 3.2 integration tests | 46 | ALL PASS |
| Phase 3.3 integration tests | 27 | ALL PASS |
| **Total** | **904** | **ALL PASS** |

## Phase 3.3 Tests (27)

### Predictions (test_phase33_predictions.py) — 14 tests

**Creation (3):**
- [x] Server-computed proof_hash (I10)
- [x] NULL entry_odds preserved (I3)
- [x] Invalid odds rejected (CHECK constraint)

**Settlement (5):**
- [x] WIN outcome computed correctly (I11)
- [x] LOSS outcome computed correctly
- [x] Settlement idempotent (I14)
- [x] BACKTEST predictions rejected (I12)
- [x] NULL closing_odds → NULL CLV (I4)

**Immutability (2):**
- [x] Settlement UPDATE blocked (Trust Test 1)
- [x] Settlement DELETE blocked (Trust Test 2)

**Paper Ledger Trust (4):**
- [x] Ledger UPDATE blocked (Trust Test 3)
- [x] Ledger DELETE blocked (Trust Test 4)
- [x] Balance reconstruction from ledger entries
- [x] Settlement atomically creates ledger entry

### Social (test_phase33_social.py) — 13 tests

**Follows (4):**
- [x] Follow and unfollow cycle
- [x] Self-follow prevented (CHECK constraint)
- [x] Duplicate follow idempotent
- [x] Follower/following lists correct

**Quarantine (5):**
- [x] Enter quarantine
- [x] Version-specific quarantine (I19)
- [x] Promotion requires PASSED validation
- [x] Promotion requires 90-day period
- [x] State immutable after promotion

**Cross-User Isolation (2):**
- [x] User cannot see other's predictions
- [x] User cannot see other's portfolio (Trust Test 8)

**Reputation & Leaderboard (2):**
- [x] Reputation system-writable only (users blocked)
- [x] Leaderboard readable by all

## Mandatory Trust Tests Coverage

| # | Test | Status |
|---|------|--------|
| 1 | UPDATE settlements blocked | PASS |
| 2 | DELETE settlements blocked | PASS |
| 3 | UPDATE paper_ledger_entries blocked | PASS |
| 4 | DELETE paper_ledger_entries blocked | PASS |
| 5 | proof_hash server-computed | PASS |
| 6 | closing_odds not client-supplied | PASS (NULL CLV test) |
| 7 | outcome server-derived | PASS (WIN/LOSS tests) |
| 8 | Cross-user portfolio isolation | PASS |
| 9 | Cross-user prediction isolation | PASS |
| 10 | Promotion requires validation | PASS |
| 11 | Settlement idempotent | PASS |
| 12 | BACKTEST cannot enter live settlement | PASS |
