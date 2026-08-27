# Phase 3.3 Paper Ledger Trust Model

## Design Principle

The paper ledger is the **social trust foundation** of the platform.

If ledger entries could be modified, users could fabricate track records.
The append-only guarantee makes paper portfolios as trustworthy as
blockchain ledgers — without chain complexity.

## Guarantees

1. **APPEND-ONLY**: No UPDATE, no DELETE (DB trigger enforced)
2. **MONOTONIC**: BIGSERIAL PK ensures strict chronological ordering
3. **RECONSTRUCTABLE**: `SUM(amounts)` = `current_balance` at any point
4. **ATOMIC WITH SETTLEMENT**: Settlement + ledger entry in same transaction
5. **IDEMPOTENT**: `has_settlement_entry()` prevents double-crediting
6. **AUDITABLE**: Every entry has `created_at`, `entry_type`, optional `metadata`

## Entry Types

| Type | Trigger | Amount | Notes |
|------|---------|--------|-------|
| OPENING_BALANCE | Portfolio creation | +initial_balance | First entry in every portfolio |
| BET_PLACED | Prediction placed | -stake | Stake deducted from bankroll |
| BET_SETTLED | Settlement resolved | +/-profit_loss | WIN: +profit, LOSS: -stake |
| ADJUSTMENT | Admin correction | +/- | Compensating entry; never rewrites history |

## Balance Reconstruction

```
portfolio.current_balance = SUM(paper_ledger_entries.amount)
                            WHERE portfolio_id = X
                            ORDER BY id ASC
```

The `current_balance` field on `paper_portfolios` is a **cached/materialized** value.
The ledger is the source of truth. If they disagree, the ledger wins.

## Correction Mechanism

Errors are corrected by **compensating entries**, never by modifying history:

```
Entry #1: OPENING_BALANCE +1000 → 1000
Entry #2: BET_SETTLED +50 → 1050    ← this was wrong
Entry #3: ADJUSTMENT -50 → 1000     ← compensating entry
Entry #4: BET_SETTLED +30 → 1030    ← correct amount
```

## Security

- RLS ensures users can only see their own ledger entries
- No API endpoint exists to INSERT arbitrary ledger entries
- Only the settlement service and portfolio creation service can append
- Admin ADJUSTMENT entries require explicit authorization (not yet exposed via API)
