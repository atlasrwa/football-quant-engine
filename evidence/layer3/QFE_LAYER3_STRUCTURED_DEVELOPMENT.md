# QFE V2 Layer 3 — Structured Model Development Evidence

Frozen on: 2026-10-02
Bundle hash: 709c1daf0eea03fb439460d41cd4f3f3152009963bad69a77a2cf28c72f26c62
Chronology hash: 9cf5e680174b78b639a80bd85498ed04f3f79482634ced8194ae5c9192495269
Corpus hash: bde8a51688674f0ca5d7b17426327cc55d5d44ce4106443eb1a2f5b780419e22

> DEVELOPMENT SELECTION ONLY.
> Calibration rows scored during selection: 0.
> Protected rows scored during selection: 0.

## Intensity grid

3 decay horizons × 3 team-influence levels × 3
team-in-competition prior strengths = 27 candidates per target.

### Goals intensity

- Anchor hl180_inf075_tcp08: 1.450109
- Selected hl360_inf100_tcp04: 1.446783
- Selected MAE: 0.892010
- Improvement vs anchor: +0.003326 (95% CI +0.001453 to +0.005168)

### Corners intensity

- Anchor hl180_inf075_tcp08: 2.394904
- Selected hl180_inf100_tcp04: 2.389006
- Selected MAE: 2.115767
- Improvement vs anchor: +0.005898 (95% CI +0.002168 to +0.009331)

## Goals distribution: Poisson vs Dixon–Coles

- N: 3812
- Poisson joint NLL: 2.893567
- Dixon–Coles joint NLL: 2.893783
- Joint NLL delta Poisson - Dixon–Coles: -0.000216 (95% CI -0.000786 to +0.000428)
- Event LL delta Poisson - Dixon–Coles: -0.000057
- Decision: reject current Dixon–Coles candidate.

## Corners distribution: Poisson vs NB2

- N: 3783
- Poisson joint NLL: 4.778011
- NB2 joint NLL: 4.689384
- Joint NLL delta Poisson - NB2: +0.088627 (95% CI +0.066015 to +0.113199)
- Event LL delta Poisson - NB2: +0.003186 (95% CI +0.001832 to +0.004638)
- Decision: select NB2 for the next stage.

### Corners joint-NLL delta by competition

| Competition | Poisson - NB2 |
|---|---:|
| comp_0256 | +0.120818 |
| comp_0976 | +0.072622 |
| comp_3039 | +0.121440 |
| comp_8321 | +0.052389 |
| comp_8814 | +0.089077 |
| comp_9777 | +0.104517 |

## Scientific interpretation

Development evidence supports stronger dynamic intensities for both
targets and NB2 overdispersion for corners. It does not support the
tested Dixon–Coles correction for goals on this development window.

This is not protected OOS evidence. Additional DEVELOPMENT candidates
must be evaluated under the same frozen chronology before the
standalone component set is frozen for CALIBRATION.
