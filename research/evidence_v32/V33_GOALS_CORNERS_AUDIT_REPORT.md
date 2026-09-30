# QFE V3.3 — Goals O/U and Corners O/U model upgrade audit

Status: **DEVELOPMENT_ONLY / NO PRODUCTION PROMOTION**

Frozen spec: `ff4f224`  
Frozen apparatus: `93407e3`

No live provider, bookmaker, LLM, Telegram or deployment calls were made. Existing
V3/V3.2/V3.2.3 evidence and production paths were not rewritten.

## Executive decision

### Goals O/U

Retain **VENUE_DEEP_POISSON** as the preferred prospective challenger. Do not
replace the full deep bundle with the compact chance-only bundle.

The result is strongest for total goals >2.5. The full deep model improves over
the rich model, and on the venue-supported cohort the full venue-deep model also
beats the venue-compact model with better log loss and Brier. The >3.5 direction
is also favorable but less certain.

Do **not** force xG. On a support-matched cohort it worsened both total >2.5 and
total >3.5 proper scores. npxG remains excluded because the repository provider
contract marks its per-side semantics unaudited.

This remains a development challenger, not a production promotion, because the
outcomes are exposed development data and prior timestamped market evidence is
still too small/inconclusive to establish incremental value after market.

### Corners O/U

Keep the frozen **QFE_CORNERS_V3_TSA_MEDIAN** reference unchanged.

The new pressure model contains real-looking signal: versus a regularized
corner-history base it reduces log loss and Brier at 8.5, 9.5 and 10.5.
However, calibration slopes deteriorate materially. The preregistered gate
therefore fails.

Adding venue-conditioned pressure is inconsistent: it helps 8.5 slightly but
hurts 9.5 and 10.5. The extended proxy bundle (throw-ins, accurate long balls,
offsides, goal kicks, free kicks) is worse at every tested line. Both additions
are dropped.

Against the actual frozen V3 replay, the venue-pressure challenger is slightly
better at 8.5/9.5 and essentially flat at 10.5, but all uncertainty intervals are
wide. That is not enough to replace the protected reference.
## Evidence support

- Full evidence panel: 8,625 fixtures.
- Goals full-deep support: 3,811 fixtures.
- Goals venue support: 3,574 fixtures.
- Corner target/stat panel: 4,487 fixtures.
- Corner pressure support: 3,761 fixtures.
- Corner venue-pressure support: 3,549 fixtures.
- Corner extended support: 3,759 fixtures.
- Five expanding chronological folds with calibration/test separation and 28h
  purge inherited from V3.2.2.
- Paired uncertainty uses ISO-week blocks rather than IID fixture bootstrap.

## Goals O/U — what stays

| Comparison | Total >2.5 LL gain | Total >3.5 LL gain | Decision |
| --- | ---: | ---: | --- |
| DEEP vs RICH | +0.000986 | +0.000392 | Keep full deep bundle |
| VENUE_DEEP vs VENUE_COMPACT | +0.001393 | +0.000662 | Keep full venue-deep challenger |
| VENUE_DEEP_XG vs matched control | -0.000525 | -0.000363 | Drop mandatory xG |

For VENUE_DEEP vs VENUE_COMPACT, the total >2.5 week-block interval is
[+0.000300, +0.002471] and Brier improves by -0.000659. Total >3.5 Brier
improves by -0.000216, but its interval crosses zero.

The compact ablation matters scientifically. The six full-deep-only fields
(dispossessed, fouled in final third, ball recoveries, passes, accurate passes,
offsides) cannot yet be attributed individually, but removing the block loses
O/U performance. They remain as a **registered block**, not as individually
claimed predictive features.

## Corners O/U — what was learned

### Core pressure bundle

Pressure features:
- total shots;
- blocked shots;
- accurate crosses;
- final-third entries;
- shots inside the box;
- touches in the penalty area;
- possession;
- clearances;
- shots off target.

Against the support-matched corner-history base:

| Line | LL gain | Brier direction | Calibration slope: base → pressure |
| --- | ---: | --- | --- |
| O8.5 | +0.000697 | better | 0.881 → 0.721 |
| O9.5 | +0.001452 | better | 1.025 → 0.821 |
| O10.5 | +0.001013 | better | 1.031 → 0.796 |

So the pressure information is not useless. It improves discrimination/proper
score slightly, but the probability scale becomes too compressed/miscalibrated
to pass the frozen gate.

### Venue-conditioned corners

Relative to the same pressure model:
- O8.5: +0.000431 LL gain;
- O9.5: -0.000827;
- O10.5: -0.000830.

Decision: **drop the venue add-on for corners** in this version.

### Extended proxy raw fields

The extended arm adds throw-ins, accurate long balls, offsides, goal kicks and
free kicks. All five have high raw coverage, but coverage is not predictive
evidence. The arm worsens log loss at every line:
- O8.5: -0.001133;
- O9.5: -0.001280;
- O10.5: -0.000868.

Decision: **drop the entire extended proxy block**.
## Raw-stat re-audit

High coverage does not justify inclusion by itself.

### Keep in goals challenger
The existing deep raw set plus the V3.2.3 matched-venue evidence remains the
best development frontier. No newly discovered raw field earned addition in
V3.3.

### Keep only as a corners research hypothesis
The nine direct corner-pressure fields above are retained only for a future
calibration experiment. They are not promoted into the operational corner model.

### Explicitly do not add
- xG as a mandatory goals input: matched-support O/U result is negative.
- npxG: 76.45% expanded-cache coverage, but per-side semantics are still marked
  unaudited by the provider contract.
- goals prevented: lower coverage and prior repository semantic/coverage warning.
- duel/tackle percentage fields: naming/unit behavior requires a separate provider
  semantics audit before use.
- hit woodwork: high coverage but rare and not sufficiently direct to justify
  entry without a separate preregistration.
- throw-ins / long balls / goal kicks / free kicks for corners: empirically worse
  as an incremental block in V3.3.

## Model status after V3.3

**Goals O/U:** preferred research frontier =
`VENUE_DEEP_POISSON`, no xG. Strongest evidence is total >2.5. Still requires
new prospective frozen outcomes and a larger timestamped market comparison
before any production promotion.

**Corners O/U:** production/research reference remains
`QFE_CORNERS_V3_TSA_MEDIAN`. The core pressure bundle has enough signal to
justify one future experiment with a separately frozen calibration layer, but
V3.3 itself does not authorize a model replacement.

## Integrity conclusion

The audit did not optimize for a successful story. A simpler goals ablation was
rejected because it lost information. The attractive-looking extra corner
features were rejected because they worsened results. The core corner pressure
model was also not promoted despite small proper-score gains because calibration
failed the preregistered gate.

That is the correct frontier to carry forward.
