# QFE V2 Layer 4 — Standalone p_model Freeze

Model freeze hash: `97b0852b75c1191c603d9857a2ba8a1276be9c4a24057d9c2bbf0edafbde2e8a`

> Odds-blind standalone model only. PROTECTED remains unopened. No market or commercial claim is authorized.

## Frozen stack

- Goals O2.5: dynamic + similar-context weight **0.20**, calibrated by **ISOTONIC_GLOBAL**.
- Corner sides: Poisson/NB2 mixture weight **0.75**, calibrated by **PLATT_GLOBAL**.
- Corner totals: same coherent mixture, calibrated by **PLATT_ROLE_COMP_RIDGE_L1**.
- Common pre-calibration corner alpha: **0.099909**.

## SELECT evidence versus identity

- Goals: identity LL 0.677835 → selected LL 0.671897.
- Corner sides: identity LL 0.579235 → selected LL 0.578967.
- Corner totals: identity LL 0.619012 → selected LL 0.613997.

## Support boundary

Unsupported raw-probability bins remain explicit metadata and must not be treated as equally credible by Layer 5.

Next: freeze the Layer 5 market-surface/disagreement policy before opening protected outcomes.
