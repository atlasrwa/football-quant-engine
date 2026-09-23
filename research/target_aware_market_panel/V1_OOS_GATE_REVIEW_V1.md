# Target-Aware Market Panel V1 — OOS Gate Review

**Decision:** **ABORT V1 predictive OOS before outcome access**

**Support freeze:** `ac0dc462b7fec730a58e29068682464bfea3d924`  
**Outcomes read:** no  
**Market results read:** no  
**Model fit:** no  
**OOS executed:** no  
**CHAMPION changed:** no

## Why

The frozen V1 predictive protocol requires a 60% feature-coverage screen computed on each fold's training rows. The outcome-blind support freeze shows that this gate makes V1 structurally unable to test its dominant Sol hypothesis class.

- Frozen class-C templates: **124**
- Opponent-similarity templates: **116**
- Opponent-similarity templates ever eligible on a frozen training fold: **0 / 116**
- Fold 0 eligible class-C features: **0**
- Fold 1 eligible class-C features: **0**
- Fold 2 eligible class-C features: **1**
- Fold 3 eligible class-C features: **0**
- Fold 4 eligible class-C features: **1**

The only feature that clears the frozen training screen is `mt_377417012_GOALS_RECIPROCAL_CHANCE_MATCHUP`, a `MULTI_DIMENSION_MATCHUP` for total goals, and it clears only folds 2 and 4.

Therefore BOOKINGS, CORNERS and TEAM_TOTALS would have **M1 = M0 by construction in every fold**. The OOS experiment would not evaluate Sol's central similar-opponent idea for those families.

## Why this is an apparatus issue, not a negative predictive result

The similarity features do acquire substantial support later in the panel:

- Fold 2 segment: **116 / 116** have >=60% coverage; median 0.661.
- Fold 3 segment: **116 / 116**; median 0.928.
- Fold 4 segment: **116 / 116**; median 0.951.

Their structural requirements—venue-matched style history, >=15 prior subject matches, >=5 neighbours—create a long warm-up. The cumulative training coverage screen counts that left-censored warm-up as missingness forever. V1 therefore confounds **not yet historically computable** with **operationally missing**.

## Scientific action

Do **not** lower the V1 60% threshold, alter the 124 hypotheses, move folds, or inspect outcomes to rescue the experiment.

Keep V1 frozen as a valid generation + support experiment and mark its predictive OOS stage non-evaluable.

Create **TARGET_AWARE_MARKET_PANEL_V1_2_EVALUABILITY_REPAIR** (V1.1 remains reserved for half markets) with a preregistered, outcome-blind fix: adequate prehistory and/or explicit warm-up semantics, plus a minimum evaluability gate frozen before labels are read.

Only after the repaired apparatus proves that the intended Sol feature class is actually exercised should M0-vs-M1 OOS run.
