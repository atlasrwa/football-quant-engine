# QFE V3.6 — Chronology, eligibility, corner coherence, calibration and market-combination audit

Status: **DEVELOPMENT_ONLY / NO PRODUCTION PROMOTION**

Frozen protocol commit: `2f6622a`  
Implementation commit: `97eba29`

The experiment is offline-only. No provider, bookmaker, LLM, Telegram or deployment calls were made. Existing production models and ledgers were not mutated.

## What was repaired

### 1. Chronology

All fitted stages now respect the actual forecast timestamp rather than merely the target kickoff.

- football feature horizon: T−24h;
- previous match labels must be available before that forecast timestamp;
- a four-hour completion buffer is applied;
- every stage boundary has a strict 28-hour purge;
- outer evaluation fixtures are predicted only from artifacts whose latest fit label is available before the fixture's T−24h cutoff.

The old V3.5 cached replay fails this standard as prospective evidence. Of its 12 fixtures:
- 10 used an artifact whose fitted labels were not all available before the T−24h forecast time;
- the remaining 2 still do not have artifact-creation provenance establishing that the artifact existed before the forecast timestamp.

The V3.5 replay remains immutable as a diagnostic, but it must not count toward promotion or prospective validation.

### 2. Eligibility

Goals venue-deep eligibility now requires:
- explicit non-neutral fixture status;
- sufficient all-venue goal/deep raw history;
- sufficient home-at-home history for the home side;
- sufficient away-away history for the away side;
- target labels and historical evidence available before the T−24h cutoff.

Unsupported fixtures abstain instead of imputing eligibility.

### 3. Corner coherence

The V3.5 line-specific corner blend was structurally unsafe: different weights at 8.5, 9.5 and 10.5 can make over probabilities cross.

V3.6:
- horizon-matches the V3 corner parent and pressure challenger at the same T−24h cutoff;
- uses one shared blend coefficient across all registered lines;
- tests both a shared logit blend and a PMF/probability mixture;
- enforces monotone over-line probabilities.

The fitted shared pressure weights were highly stable:

| Fold | Shared logit weight | PMF mixture weight |
| --- | ---: | ---: |
| 0 | 0.17277 | 0.17291 |
| 1 | 0.17504 | 0.17312 |

## Chronological panel

Full evidence base: **8,625 fixtures**.

### Goals

Fold 0:
- count train: 1,038
- count calibration: 459
- probability calibration: 507
- evaluation: 1,080

Fold 1:
- count train: 2,029
- count calibration: 650
- probability calibration: 374
- evaluation: 438

Combined evaluation: **1,518 fixtures / 3,036 line observations**.

### Corners

Fold 0:
- count train: 1,130
- count calibration: 462
- probability/stack calibration: 520
- evaluation: 1,081

Fold 1:
- count train: 2,137
- count calibration: 650
- probability/stack calibration: 375
- evaluation: 516

Combined evaluation: **1,597 fixtures / 4,791 line observations**.  
Common support with the horizon-matched V3 corner parent: **1,564 fixtures**.

## Goals calibration challengers

| Arm | Log loss | Brier | Calibration intercept | slope |
| --- | ---: | ---: | ---: | ---: |
| Raw | 0.633637 | 0.221654 | 0.1396 | 1.060 |
| Count scale | **0.632931** | 0.221335 | 0.0325 | **1.053** |
| Count affine | 0.632705 | 0.221157 | 0.0413 | 1.100 |
| Shared sigmoid | 0.632572 | **0.221142** | 0.0570 | 1.098 |

Shared sigmoid improves log loss over count scale by only **0.000360**.

Paired UTC-week 95% interval:
**[-0.001707, +0.002588]**

Count affine gain:
**+0.000227**, interval **[-0.001092, +0.001499]**.

The preregistered minimum worthwhile improvement was **0.005 log loss**. Neither challenger is close, and both uncertainty intervals cross zero.

### Goal line detail

O2.5:
- count scale LL: 0.678773
- shared sigmoid: 0.678935
- count affine: 0.679206

O3.5:
- count scale LL: 0.587090
- shared sigmoid: 0.586209
- count affine: 0.586204

The apparent O3.5 calibration improvement does not generalize strongly enough across the registered goal bundle to authorize a target-specific promotion after exposure.

**Decision: keep VENUE_DEEP_POISSON with its existing count-scale calibration unchanged.**

## Corner calibration / combination challengers

| Arm | Log loss | Brier | Calibration slope |
| --- | ---: | ---: | ---: |
| Pressure count scale | 0.669793 | 0.238483 | 0.888 |
| Shared sigmoid | 0.669618 | 0.238409 | 0.946 |
| Horizon-matched V3 parent | 0.670301 | 0.238760 | 0.851 |
| Shared coherent logit stack | **0.668297** | **0.237808** | 0.912 |
| Coherent PMF mixture | 0.668323 | 0.237820 | **0.915** |

Shared-logit stack gain versus pressure count-scale:
**+0.001510 log loss**.

Paired UTC-week 95% interval:
**[-0.004084, +0.007464]**.

PMF-mixture gain:
**+0.001483**, interval **[-0.004107, +0.007451]**.

Again, the preregistered worthwhile threshold was **0.005**.

### Corner line detail

Shared coherent logit stack vs pressure count scale:

- O8.5: 0.666155 vs 0.667032
- O9.5: 0.686960 vs 0.687538
- O10.5: 0.651775 vs 0.654809

The direction is favorable at all three lines, and calibration improves materially at O10.5, but uncertainty remains too wide for promotion.

**Decision: retire the V3.5 line-specific corner stack from forward scientific use. Keep the new coherent shared stack as research/shadow only. Do not replace the protected V3 reference or declare it promoted.**

## Market-combination challenger

The combined market cache contains **310 fixture histories**, but the timestamp distribution does not match the registered T−24h prediction horizon.

At the registered horizon, within the frozen one-hour quote-age window:

- goals matched line observations: **0**
- corners matched line observations: **0**

Therefore the market-combination arms correctly returned **MARKET_UNTESTED**.

Only a handful of genuine near-close observations exist in the evaluation panel:

- goals: 8 line observations / 4 fixtures
- corners: 4 observations / 4 fixtures

Those are reported only as a different information horizon and are far below the preregistered 100-fixture market-fit minimum.

A coverage-only audit of fixed candidate horizons, performed without using outcomes to choose a winner, found:

| Market horizon | Goals complete fixtures | Corner fixtures with a quoted registered line |
| --- | ---: | ---: |
| T−24h | 0 | 0 |
| T−12h | 9 | 10 |
| T−6h | 15 | 21 |
| T−3h | 27 | 23 |
| T−1h | 36 | 39 |
| T−15m | 37 | 47 |

Corners never had all three registered lines quoted together at any candidate horizon.

The correct response is **not** to lower the 100-fixture market-fit requirement after seeing this. More timestamped market capture is required before a market-adjusted challenger can be honestly fitted.

## Selection thresholds

The existing disagreement thresholds remain frozen and unchanged:

- selected model probability >= 60%;
- model minus no-vig market probability >= 5 percentage points;
- model must beat the raw vig-loaded break-even probability.

No V3.6 calibration parameter was selected using these thresholds, and the thresholds were not retuned from the cached outcomes.

## Final decision

1. **Goals:** keep the current venue-deep count-scale model unchanged.
2. **Corners:** V3.5 line-specific mixing is superseded scientifically by the coherent shared-weight formulation, but the coherent mix remains research/shadow only because the OOS gain is small and uncertain.
3. **Calibration:** no new calibration arm earns promotion.
4. **Market combination:** remains untested because point-in-time quote support is insufficient; do not force a fit.
5. **Old cached 4–1 replay:** diagnostic only, not prospective validation.
6. **Selection thresholds:** remain frozen at 60% / +5 pp / raw break-even.
7. **Next evidence requirement:** accumulate genuine timestamped quotes at the intended decision horizon, freeze probabilities prospectively, settle through the V32.1 stable-score gate, then evaluate log loss, Brier, calibration and market/closing-line incremental value.
