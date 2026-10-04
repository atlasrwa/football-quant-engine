# QFE V2 Layer 3 — Structured Model Development Evidence

Frozen on: 2026-10-03
Bundle hash: 3e34c31438082d2845b8bfcaf1781b7ac0b6f7794e088fbd759341f83c0b2b01
Chronology hash: 9cf5e680174b78b639a80bd85498ed04f3f79482634ced8194ae5c9192495269
Corpus hash: bde8a51688674f0ca5d7b17426327cc55d5d44ce4106443eb1a2f5b780419e22

> DEVELOPMENT SELECTION ONLY.
> Calibration rows scored during selection: 0.
> Protected rows scored during selection: 0.

## Intensity grid

3 decay horizons × 3 team-influence levels × 3
team-in-competition prior strengths = 27 candidates per target.

### Goals intensity

- Anchor hl180_inf075_tcp08: 1.450090
- Selected hl360_inf100_tcp04: 1.446764
- Selected MAE: 0.892016
- Improvement vs anchor: +0.003326 (95% CI +0.001431 to +0.005196)

### Corners intensity

- Anchor hl180_inf075_tcp08: 2.394946
- Selected hl180_inf100_tcp04: 2.389049
- Selected MAE: 2.115908
- Improvement vs anchor: +0.005897 (95% CI +0.002174 to +0.009341)

## Goals distribution: Poisson vs Dixon–Coles

- N: 3812
- Poisson joint NLL: 2.893527
- Dixon–Coles joint NLL: 2.893698
- Joint NLL delta Poisson - Dixon–Coles: -0.000171 (95% CI -0.000772 to +0.000521)
- Event LL delta Poisson - Dixon–Coles: -0.000048
- Decision: reject current Dixon–Coles candidate.

## Corners distribution: Poisson vs NB2

- N: 3783
- Poisson joint NLL: 4.778099
- NB2 joint NLL: 4.689435
- Joint NLL delta Poisson - NB2: +0.088664 (95% CI +0.065998 to +0.113344)
- Event LL delta Poisson - NB2: +0.003205 (95% CI +0.001851 to +0.004680)
- Decision: select NB2 for the next stage.

### Corners joint-NLL delta by competition

| Competition | Poisson - NB2 |
|---|---:|
| comp_0256 | +0.121074 |
| comp_0976 | +0.072432 |
| comp_3039 | +0.121530 |
| comp_8321 | +0.052377 |
| comp_8814 | +0.089239 |
| comp_9777 | +0.104545 |

## Scientific interpretation

Development evidence supports stronger dynamic intensities for both
targets and NB2 overdispersion for corners. It does not support the
tested Dixon–Coles correction for goals on this development window.

This is not protected OOS evidence. Additional DEVELOPMENT candidates
must be evaluated under the same frozen chronology before the
standalone component set is frozen for CALIBRATION.
