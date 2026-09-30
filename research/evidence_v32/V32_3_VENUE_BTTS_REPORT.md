# QFE V3.2.3 — venue-conditioned goals / BTTS development report

Status: **DEVELOPMENT_ONLY / NOT PROMOTED**

Parent: V3.2.2 at `29f61b2`.
Preregistration: `d36c55b`.
Frozen apparatus: `6463c93`.

No live provider, bookmaker, LLM or Telegram calls were made. V3.2.2 results,
corners, cards and settlement history were not rewritten.

## Question tested

Does conditioning the goal-distribution model on the historical venue role add
predictive information beyond the same V3.2.2 deep model that only knows the
current fixture venue?

For the target home team, the challenger uses prior non-neutral matches where
that team was home. For the target away team, it uses prior non-neutral matches
where that team was away. Venue-only observations are shrunk toward the same
team's point-in-time all-venue profile.
## Added venue-conditioned evidence

Each matched venue profile contains:

- goals for / against;
- clean-sheet rate;
- failed-to-score rate;
- BTTS rate;
- shots for / against;
- shots on target for / against;
- shots inside the box for / against;
- big chances for / against.

Provider xG for / against is evaluated only in a separate support-matched arm.
Missing xG is never imputed from another field.

The current target match's statistics never enter its own features. Neutral
historical matches do not enter the home/away split. A venue profile requires
at least three eligible prior venue matches and is shrunk by five matches toward
the team's all-venue profile.

## Support

- Evidence panel: 8,625 fixtures.
- Venue-conditioned supported fixtures: 3,574.
- Venue + xG supported fixtures: 2,482.
- Non-overlapping walk-forward test observations: 1,784.
- Uncertainty blocks: 44 ISO weeks.

Colombia `comp_720692` has only 22 venue-supported fixtures in this current
rich-evidence corpus, so no Colombia-specific model conclusion is authorized.
## Primary matched comparison

The control and challenger are fitted/evaluated on exactly the same
venue-supported fixtures.

| Target | Control log loss | Venue log loss | LL gain | Brier change | Venue calibration intercept / slope |
| --- | ---: | ---: | ---: | ---: | --- |
| BTTS | 0.686399 | 0.685950 | +0.000450 | -0.000221 | +0.093 / 0.995 |
| Home >1.5 | 0.663195 | 0.662473 | +0.000722 | -0.000368 | +0.044 / 0.982 |
| Away >1.5 | 0.628177 | 0.627844 | +0.000334 | -0.000115 | -0.075 / 0.855 |
| Total >2.5 | 0.681327 | 0.680129 | +0.001198 | -0.000580 | +0.062 / 1.082 |
| Total >3.5 | 0.587401 | 0.586680 | +0.000721 | -0.000343 | -0.136 / 0.875 |

Positive LL gain and negative Brier change favor the venue challenger.

BTTS's week-block 95% development interval is
[-0.000261, +0.001164], so the BTTS gain is directionally favorable but
inconclusive. Total >2.5 is the only registered target whose nominal development
interval is fully positive: [+0.000284, +0.002137].
## BTTS interpretation

The venue-conditioned joint goal model improves BTTS calibration materially:
the diagnostic slope moves from 0.948 to 0.995 while retaining a similar
intercept. The proper-score improvement is much smaller than the calibration
improvement, so venue conditioning is retained as a prospective challenger,
not promoted as a proven superior model.

A separate direct venue-conditioned logistic BTTS classifier performs much worse:
log loss 0.699846 versus 0.685950 for the coherent joint venue goal model.
Its paired LL gain relative to the joint model is -0.013896 with the development
interval fully below zero. The direct YES/NO shortcut is therefore rejected.

## xG

On the venue+xG matched cohort (1,332 test observations), adding venue-conditioned
xG worsens BTTS log loss by 0.001045 and worsens Brier by 0.000514.
The corresponding week-block interval for the LL comparison is entirely negative.
xG remains preserved evidence but is not a mandatory BTTS feature.
## Decision

1. Keep explicit historical home-at-home and away-away performance in the
   prospective **challenger** feature bundle.
2. Keep clean-sheet, failed-to-score and venue BTTS rates.
3. Keep matched-venue shots, SoT, box shots and big chances for and against.
4. Keep xG optional/support-matched; do not force it into BTTS.
5. BTTS continues to come from the coherent calibrated joint goal distribution.
6. Do not use the direct venue logistic BTTS model.
7. Do not promote V3.2.3 from exposed development data. Freeze it for prospective
   shadow comparison against the non-venue deep control.
8. Do not infer league-specific winners from these exposed results.
