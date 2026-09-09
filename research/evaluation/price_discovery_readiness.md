# Price-discovery study — readiness

Branch `research/price-discovery-prospective` · baseline `main 57e80ffa6`.
This documents the first price-discovery study's data preparation and its
readiness against the **preregistered** sample gate. No model is fitted; no
predictive-signal, edge, or profitability claim is made or permitted before the
gate is met.

## The question this dataset prepares for

> Can genuinely point-in-time information (fundamental disagreement, lineups,
> availability, referee/context) predict subsequent market movement, and later
> improve outcome forecasts versus the same-vintage market?

The FIRST question is price discovery — does information known at time *t*
predict where the market moves afterward — not "can we beat outcomes".

## Readiness state: PRICE_DISCOVERY_NOT_ENOUGH_DATA / EXPLORATORY

The state is derived deterministically:

- `PRICE_DISCOVERY_NOT_ENOUGH_DATA` — below the descriptive floor.
- `PRICE_DISCOVERY_EXPLORATORY` — enough for descriptives; **gate not met**.
- `PRICE_DISCOVERY_EVALUABLE` — the preregistered gate is met (only then may a
  formal model be run/promoted).

As of the latest build the state is **EXPLORATORY**: same-book multi-vintage
transitions have begun to accumulate now that the scheduler runs continuously,
but the preregistered thresholds are not close to met. The exact live counts
are in `research/evaluation/prospective_data_quality.json`.

## Preregistered gate (fixed in advance — never lowered after seeing results)

| Requirement | Threshold |
|---|---|
| Captured fixtures | ≥ 300 |
| Valid same-book LATE→FINAL transitions | ≥ 200 |
| Confirmed lineups observed before FINAL | ≥ 150 |
| PRE_LINEUP → POST_LINEUP same-book/same-line pairs | ≥ 100 |

These are declared in code (`ReadinessGate` / `PROSPECTIVE_GATE`) and asserted
by tests so they cannot be silently relaxed.

## Current blocker (honest)

The store's early captures clustered in a narrow window (EARLY/MID), so most
keys had a single snapshot and no same-key transitions. The continuous
scheduler is now the mechanism that fills LATE/FINAL and produces:

- same-book LATE→FINAL price transitions,
- confirmed lineups (announced ~1h pre-kickoff),
- PRE_LINEUP → POST_LINEUP price pairs.

No lineup/availability/referee observations exist in the store yet, so the
lineup-dependent gate rows are 0. These are reported as **0**, never
substituted with a fabricated value. `UNKNOWN != false`.

## Dataset contract (leakage-safe)

`src/research/experiments/price_discovery/dataset.py` builds rows where:

- movement target = `logit(p_later) − logit(p_earlier)` on de-vigged
  probabilities, for the **same** bookmaker+market+selection+line;
- cross-book and cross-line comparisons are refused (never fabricated);
- line changes are tracked **separately** and never counted as price movement;
- predictor fields (fundamental disagreement, lineup surprise, availability,
  referee) attach information from the **earlier** endpoint only, and remain
  NULL until those channels are captured — never invented;
- serialization is deterministic (byte-identical re-runs).

## Descriptive reporting only (pre-gate)

Allowed now: N, coverage (by book/market/competition), movement distribution,
sign split, median absolute movement, bookmaker continuity, line-change count.
Not allowed until the gate: any claim of predictive signal, edge, profitability,
or promotion. The report emitter contains none of that vocabulary.

## Price-discovery evidence ladder (do not skip levels)

```
L0 no signal predicts later movement
L1 features predict direction/magnitude of later movement
L2 when model disagrees with market, market later moves toward model
L3 adjusted earlier price approaches the genuine close better than raw earlier
L4 same-vintage adjusted probability beats market on outcomes OOS
L5 executable economic edge after price/limits/slippage/liquidity
```

We are at **pre-L1** (collecting the data required to even test L1). Outcome
analysis (L4+) is explicitly deferred until L1/L2 evidence exists.

## Next action

Let the collector accrue LATE/FINAL and lineup data. Re-run
`python -m src.research.experiments.price_discovery.cli report` to refresh the
counts; when the preregistered gate is met the state flips to EVALUABLE and the
formal M0–M4 study (deferred here) may run, producing
`price_discovery_report.{md,json}`.
