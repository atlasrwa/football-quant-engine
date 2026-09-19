# FDR Analysis: Corners & Cards Robustness Results

## Family Definition

**Family size: 2 hypotheses** (corners model, cards model)

**Rationale:** Each league-season result is not an independent hypothesis — it's a
*replicate* of the same hypothesis ("the model works"). The claim being tested for
quarantine eligibility is "the corners model beats naive across leagues" and "the
cards model beats naive across leagues" — two hypotheses total, not 150.

Treating each league-season as a separate hypothesis would be analogous to treating
each match as a separate test — it conflates statistical power of individual replicates
with the question of whether the effect exists. The appropriate approach is to combine
evidence across replicates (meta-analysis) and then apply FDR to the resulting model-level
p-values.

For completeness, we also report individual BH on all 150 league-seasons to show that
even with that (inappropriately conservative) framing, 40% survive — which itself is
highly non-null behavior under H0 (where 5% would survive by chance).

## Results

### Meta-analytic approach (primary)

| Model | z-statistic | p-value | Survives BH (2-family)? |
|-------|-------------|---------|------------------------|
| Corners O/U 9.5 | 15.33 | < 1e-50 | Yes |
| Cards O/U 3.5 | 15.12 | < 1e-50 | Yes |

Method: Stouffer's weighted z (fixed-effects), combining 75 independent league-seasons
per model. Total effective N = 16,440 predictions per model.

### Nonparametric (binomial hit-rate test)

| Model | Positive rate | p-value | Survives BH? |
|-------|--------------|---------|-------------|
| Corners | 68/75 (91%) | 5.8e-14 | Yes |
| Cards | 72/75 (96%) | 1.9e-18 | Yes |

H0: P(model beats naive in a random league-season) = 0.5

### Individual BH (150-family, for completeness)

60/150 league-seasons survive BH at alpha=0.05. This reflects low power of individual
tests (100-300 matches each) rather than absence of effect. Under H0, we'd expect
~7.5/150 to survive by chance — observing 60 is itself strongly inconsistent with H0.

## Variance Estimation

Per-match Brier difference standard deviation measured empirically from EPL walk-forward:
- Corners: sigma = 0.139
- Cards: sigma = 0.127

## Judgment

**PASS.** Both corners and cards survive BH correction at alpha=0.05 under the
appropriate 2-hypothesis family definition. The meta-analytic p-values are effectively
zero (z > 15 for both). Quarantine enrollment may proceed.
