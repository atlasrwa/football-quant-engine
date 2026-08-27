# Phase 3.3 API Contract

## New Endpoints (14)

### Predictions
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | /api/v1/predictions | Required | proof_hash server-computed; source must be LIVE_SIGNAL or PAPER_TRADE |
| GET | /api/v1/predictions | Required | List user's predictions; ?status= filter |
| GET | /api/v1/predictions/{id} | Required | Get single prediction |

### Settlements
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | /api/v1/settlements/settle | Required | Accepts match result (goals); outcome/closing_odds server-derived |

### Portfolios
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | /api/v1/portfolios | Required | Create paper portfolio |
| GET | /api/v1/portfolios | Required | List user's portfolios |
| GET | /api/v1/portfolios/{id} | Required | Get single portfolio |
| GET | /api/v1/portfolios/{id}/ledger | Required | Get ledger entries |

### Quarantine
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | /api/v1/quarantine/enter | Required | Enter strategy version into quarantine |
| POST | /api/v1/quarantine/{id}/{version}/promote | Required | Promote (requires 90d + PASSED validation) |
| GET | /api/v1/quarantine/{id}/{version} | Required | Get quarantine status |

### Validation
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | /api/v1/validation/{id} | Required | Get validation result |

### Social
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | /api/v1/users/{id}/follow | Required | Follow user (idempotent) |
| DELETE | /api/v1/users/{id}/follow | Required | Unfollow user |
| GET | /api/v1/users/{id}/followers | Required | Get follower list |
| GET | /api/v1/users/{id}/following | Required | Get following list |
| GET | /api/v1/users/{id}/reputation | Required | Get reputation score |
| GET | /api/v1/leaderboard | Required | ?scope=global&period=30d |

## Fields NOT Accepted from Client
- `proof_hash` (I10: server-computed)
- `closing_odds` (I9: from market_prices)
- `outcome` (I11: from SettlementFactory)
- `fdr_validated` (I8: from quarantine status)
- `settlement.profit_loss` (computed from outcome + odds)
- `settlement.clv_pct` (computed from entry/closing odds)
- `reputation_score` (system-derived)
- `leaderboard.rank` (system-computed)

## Total Routes: 31 (17 from Phase 3.1 + 14 from Phase 3.3)
