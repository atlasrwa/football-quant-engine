# STAGE1_POWER_AND_COST_V1

`item6_stage1_power_cost_v1` · prospective, pre-spend

We are not testing OOS prediction in Stage 1. The sample must estimate generation-quality
endpoints — baseline-equivalent rate, duplicate rate, novel-measurable-family rate — with useful
precision, accounting for within-fixture dependence (K mechanisms per fixture are correlated).

## Selected sample size

- `STAGE1_SELECTED_N_FIXTURES = 120`
- `K_MECHANISMS_PER_FIXTURE = 5`
- `EXPECTED_GENERATED_MECHANISMS ≈ 600` (fewer with abstentions)

## Precision (frozen analysis)

**Fixture-level endpoints** (independent unit = fixture; e.g. novel-measurable-family rate). At
N=120, the 95% normal CI half-width is:

| true rate p | 95% CI half-width @ N=120 |
|---|---|
| 0.30 | ±0.082 |
| 0.40 | ±0.088 |
| 0.50 | ±0.089 |

So at the gate's `NOVEL_MEASURABLE_FAMILY_RATE_MIN = 0.30`, a true rate near the threshold is
estimated to roughly ±0.08 — enough to separate "clearly above" from "clearly below" the bar
without pretending to false precision.

**Mechanism-level endpoints** (e.g. baseline-equivalent rate) must NOT treat 600 mechanisms as
600 independent observations. Using a design effect `deff = 1 + (K-1)ρ` for intra-fixture
correlation ρ:

| ρ (intra-fixture) | design effect | effective N | 95% half-width @ p=0.4 |
|---|---|---|---|
| 0.2 | 1.80 | 333 | ±0.053 |
| 0.4 | 2.60 | 231 | ±0.063 |
| 0.6 | 3.40 | 176 | ±0.072 |

Even under strong clustering (ρ=0.6), effective N≈176 gives ±0.07 precision on a 0.4 rate —
adequate for the `BASELINE_EQUIVALENT_RATE ≤ 0.60` and `MULTIVARIABLE_INTERACTION_RATE ≥ 0.20`
gates. We report clustered (design-effect-adjusted) intervals, never the naive N=600 interval.

## Abstention accounting

Abstaining fixtures contribute to `ABSTENTION_RATE` (diagnostic) and are removed from the
denominator of the fixture-level novel-family rate. A high abstention rate is itself informative
(the generator declining rather than padding) and is reported, not penalized by the gate.

## Cost analysis (pre-spend; no spend authorized here)

Per-fixture token budget (packet + prompt + coverage spec in; 5 structured mechanisms out):

- input ≈ 6,500 tok/fixture → ≈ 780,000 tok total
- output ≈ 1,800 tok/fixture → ≈ 216,000 tok total

At order-of-magnitude Sonnet 4.x pricing (input ~$3/Mtok, output ~$15/Mtok):

| quantity | value |
|---|---|
| `EXPECTED_STAGE1_SPEND_USD` | ~$5.58 |
| `P90_STAGE1_SPEND_USD` | ~$7.99 |
| `MAX_STAGE1_SPEND_USD` | ~$15.64 (incl. retry buffer) |

These are estimates for authorization sizing only. The exact frozen cost guard (chars-per-token
calibration, hard ceiling) is set at spend-authorization time, mirroring the V3 discipline where
the measured actual/estimate ratio was verified conservative before the first paid call.

`NEW_SPEND_USD = 0` in this build.
