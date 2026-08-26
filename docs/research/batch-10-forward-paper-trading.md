# Batch 10 — Forward Research, Future Fixtures & Paper Trading Foundation

**Paper trading is research evaluation only and does not constitute production betting authorization.**

## Overview

Batch 10 moves the research platform from purely historical analysis toward prospective forward research. It establishes the infrastructure to answer:

> "Using ONLY information available before kickoff, what prediction would the strategy have made, at what odds, with what probability, expected value, and paper stake — and what happened afterward?"

This is NOT live betting. No real money. No wallets. No bookmaker execution.

## Architecture

```
Future Fixtures (provider)
    ↓
Fixture Validation (status: SCHEDULED)
    ↓
Pre-Match Feature Snapshot (temporal-causal, immutable)
    ↓
Eligible Strategy Selection (governance-based)
    ↓
Probability Prediction (model)
    ↓
Current Odds Snapshot (timestamped, immutable)
    ↓
EV / Edge Calculation
    ↓
Paper Eligibility Check
    ↓
Paper Trade (GENERATED → APPROVED → OPEN)
    ↓
Kickoff
    ↓
Closing Odds (captured separately, never modifies prediction)
    ↓
Settlement (WIN / LOSS / VOID)
    ↓
CLV Calculation
    ↓
Forward Performance Report
    ↓
Research Memory
```

## Data Flow & Temporal Semantics

### The Fundamental Rule

```
information_timestamp < prediction_timestamp <= kickoff_timestamp
```

For **every** feature, odds value, or data point used to generate a prediction, the information must have been available BEFORE the prediction was generated.

### Information Time Rules

| Artifact | Temporal Constraint |
|----------|-------------------|
| Feature value | `feature_info_time < prediction_time` |
| Odds for prediction | `odds_time <= prediction_time` |
| Prediction | `prediction_time <= kickoff_time` |
| Closing odds | Captured at/near kickoff, NEVER used for prediction |
| Settlement | After match completion, NEVER modifies prediction |
| CLV | After closing odds available, NEVER modifies trade |

### Feature Snapshot Rules

1. All features come from matches completed BEFORE prediction_timestamp
2. Same-timestamp matches are EXCLUDED (strict mode)
3. Post-match features (goals, corners, cards, xG, possession) from the TARGET fixture are NEVER included
4. Historical post-match stats from PAST matches ARE legitimate (they are known outcomes)
5. Missing features are `None` (NOT zero)
6. Each feature has provenance tracking its information_timestamp
7. Snapshots are IMMUTABLE — never updated after creation

### Odds Snapshot Rules

1. Multiple snapshots preserved (never overwritten)
2. Each snapshot has a timestamp
3. Only odds with `timestamp <= prediction_time` can be used for prediction
4. Closing odds are a SEPARATE artifact with `odds_type=CLOSING`
5. Closing odds NEVER enter prediction calculations
6. Closing odds used ONLY for CLV analysis after the fact

## CLV Methodology

**Implied Probability CLV** (the single methodology used):

```
CLV = (prediction_odds / closing_odds) - 1
```

- **Positive CLV**: Got better odds than closing line (market moved against us = good)
- **Negative CLV**: Got worse odds than closing line
- **Zero CLV**: Exactly matched the closing line

Why this methodology:
- Directly comparable across odds levels
- Industry-standard measure of prediction quality
- Works consistently across all markets
- Does not require knowing bookmaker vig structure

CLV NEVER modifies: prediction probability, prediction odds, EV, stake, or trade identity.

## Paper Trade Lifecycle

```
GENERATED → APPROVED_FOR_PAPER → OPEN → SETTLED
GENERATED → REJECTED (terminal)
APPROVED_FOR_PAPER → CANCELLED (terminal)
OPEN → VOID (terminal, e.g., fixture cancelled)
```

Invalid transitions raise `ValueError`. Settled trades cannot return to OPEN.

## Paper Eligibility

Only strategies passing deterministic governance may generate paper trades:

| Criterion | Default |
|-----------|---------|
| Walk-forward validated | Required |
| Minimum folds | 5 |
| Minimum sample size | 50 |
| Positive fold ratio | >= 0.6 |
| FDR correction passed | Required |
| Max Brier score | 0.30 |
| Evidence classification | PROMISING or higher |
| Expected value | >= 0 |

AI confidence is NEVER an eligibility criterion.

## Staking

Three models supported (paper only, no real money):

| Type | Description |
|------|-------------|
| FIXED_STAKE | Fixed amount per trade (default: 100 units) |
| FIXED_PERCENT_BANKROLL | % of current bankroll (default: 2%) |
| KELLY_FRACTION | Quarter Kelly (simulation model, conservative) |

Conservative limits:
- Max stake: 5% of bankroll per trade
- Absolute max stake: 1000 units
- Minimum stake: 1 unit
- Starting bankroll: 10,000 units

## Settlement

```python
WIN:  profit = stake * (odds - 1)
LOSS: profit = -stake
VOID: profit = 0 (stake returned)
```

Settlement uses original `odds_at_prediction`, never closing odds.

## Persistence

### Tables (Migration 002)

- `future_fixtures` — Upcoming match records
- `prematch_snapshots` — Immutable feature snapshots
- `odds_snapshots` — Timestamped odds observations
- `paper_trades` — Paper trade lifecycle
- `clv_observations` — CLV calculations
- `forward_events` — Append-only audit trail

All tables use content hashes for deterministic identity.

### Forward Repository Interface

`ForwardRepository` (abstract) with `InMemoryForwardRepository` for testing. Thread-safe via `threading.Lock` for concurrent operations.

## Crash Recovery

All operations are idempotent:
- Duplicate fixture → save returns False
- Duplicate trade → save returns False
- Duplicate snapshot → save returns False
- Re-settling already-settled trade → ValueError
- Re-running orchestrator → no duplicates created

## Concurrency

Thread-safe duplicate prevention via `threading.Lock` in repository. Multiple workers attempting the same trade → exactly one succeeds.

## Security

- No AWS credentials in fixtures, trades, snapshots, or events
- No betting API credentials anywhere
- No code path for placing real bets
- No wallet, broker, or execution objects exist
- Events never contain secrets

## AI Boundary

AI (Bedrock/Claude) can:
- Propose hypotheses (existing Batch 9 flow)

AI CANNOT:
- Generate paper trades directly
- Approve strategies
- Bypass FDR/governance/eligibility
- Modify probabilities, odds, snapshots, or settlement

## Forward Performance Classification

| Classification | Meaning |
|---------------|---------|
| INSUFFICIENT_FORWARD_DATA | < 20 settled trades |
| EARLY_SIGNAL | Small sample, directionally positive |
| PROMISING | Moderate sample, positive ROI |
| STABLE | Large sample (100+), consistent, positive CLV |
| DEGRADING | Performance below 30% of historical expectation |
| FAILED_FORWARD_VALIDATION | ROI < -15% |

These do NOT equal production approval.

## Historical vs Forward Evidence

These are NEVER silently combined:

| Historical | Forward |
|-----------|---------|
| Backtest results | Pre-match predictions |
| Walk-forward folds | Paper trade outcomes |
| FDR correction | Realized P&L |
| Historical calibration | Forward calibration |
| Historical EV | CLV |

## Operational Workflow

```python
from src.research.forward import (
    DeterministicFixtureProvider, DeterministicOddsProvider,
    TemporalFeatureEngine,
)
from src.research.forward.orchestrator import ForwardResearchOrchestrator

# Setup
orchestrator = ForwardResearchOrchestrator(
    fixture_provider=fixture_provider,
    odds_provider=odds_provider,
    feature_engine=engine,
)

# Periodic operations (call from external scheduler)
orchestrator.sync_fixtures()          # Discover new fixtures
orchestrator.build_snapshots(...)     # Build feature snapshots
orchestrator.capture_odds()           # Record current odds
# ... create/approve/open trades ...
orchestrator.settle_trades(...)       # Settle completed fixtures
```

## Limitations

1. **No real odds provider yet** — Only deterministic test provider implemented. Real odds integration remains pending.
2. **No real fixture provider** — FootyStats fixture adapter not yet wired (interface ready).
3. **No production scheduler** — Orchestrator is callable; external scheduler integration pending.
4. **Feature engine is simplified** — Computes basic aggregates from historical matches. Full feature pipeline integration with existing FeatureRegistry pending.
5. **Single-thread optimized** — Thread-safe for correctness, not optimized for high concurrency.
6. **No real-data smoke test** — No suitable real odds API currently available.

## Testing

111 tests in `test_batch10_forward_paper.py`:
- Fixture model & identity (9)
- Providers (5)
- Temporal cutoff (5)
- Feature provenance (3)
- Odds snapshots (4)
- Closing odds isolation (2)
- Trade identity (3)
- State machine (6)
- Eligibility (5)
- Staking (7)
- Settlement (7)
- CLV (5)
- Orchestrator (3)
- Persistence (6)
- Crash recovery (3)
- Concurrency (2)
- Temporal leakage attacks (18 mandatory)
- AI safety (1)
- Classification (6)
- Security (4)
- Missing data / NULL (3)
- Cancelled/postponed (3)
- End-to-end integration (1)
