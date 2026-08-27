# Phase 3.3 Security Model

## RLS Classification (Phase 3.3 Tables)

| Table | Class | Read | Write | Force RLS |
|-------|-------|------|-------|-----------|
| predictions | D (User+System) | Owner + admin | Owner + admin | Yes |
| settlements | D (inherited) | Via prediction owner | System + prediction owner | Yes |
| paper_portfolios | A (User) | Owner + admin | Owner + admin | Yes |
| paper_ledger_entries | A (inherited) | Via portfolio owner | Via portfolio owner | Yes |
| quarantine_entries | D | Owner + admin + promoted public | Owner + admin | Yes |
| validation_runs | D (inherited) | Via strategy owner | System only | Yes |
| follows | A | Follower + followed + admin | Follower + admin | Yes |
| reputation_scores | B (System) | All authenticated | System only | Yes |
| leaderboard_snapshots | B (System) | All authenticated | System only | Yes |

## Trust Boundaries (Invariants Preserved)

| # | Invariant | Enforcement |
|---|-----------|-------------|
| I3 | entry_odds > 1.0 OR NULL | CHECK constraint on predictions |
| I4 | NULL closing_odds → NULL CLV | SettlementService logic + nullable column |
| I8 | fdr_validated not client-forgeable | Not a column; derived from quarantine status |
| I9 | closing_odds from market_prices only | SettlementService loads from DB; not in API schema |
| I10 | proof_hash server-computed | PredictionService.create_prediction() computes it |
| I11 | outcome server-derived | SettlementFactory._resolve_outcome() called by service |
| I12 | BACKTEST cannot enter live settlement | SettlementService rejects source="BACKTEST" |
| I14 | Settlement idempotent | UNIQUE(prediction_id) + service checks existing |

## Immutability Enforcement

| Table | Mechanism | What's Protected |
|-------|-----------|-----------------|
| predictions | Trigger: `enforce_prediction_immutability` | All fields except status/settled_at |
| settlements | Trigger: `prevent_modification` (UPDATE+DELETE) | All fields |
| paper_ledger_entries | Trigger: `prevent_modification` (UPDATE+DELETE) | All fields |
| quarantine_entries | Trigger: `enforce_quarantine_lifecycle` | Provenance fields + terminal states |
| validation_runs | Trigger: `prevent_modification` (UPDATE+DELETE) | All fields |
| leaderboard_snapshots | Trigger: `prevent_modification` (UPDATE+DELETE) | All fields |

## IDOR Protection

Tested explicitly:
- User A cannot read User B's predictions (RLS)
- User A cannot read User B's portfolios (RLS)
- User A cannot read User B's ledger entries (RLS via portfolio)
- Users cannot write to reputation_scores (system-only INSERT policy)
- Users cannot bypass settlement immutability (trigger + RLS)
