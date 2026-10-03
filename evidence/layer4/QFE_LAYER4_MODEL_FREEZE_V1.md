# QFE V2 Layer 4 — Standalone p_model Freeze

Model freeze hash: `e33af913f4c27ce33355c78792419ad8cee73e3f16ce7c685781a010d386b3ea`

> Odds-blind standalone model only. PROTECTED remains unopened. No market or commercial claim is authorized.

## Frozen stack

- Goals O2.5: dynamic + similar-context weight **0.20**, calibrated by **ISOTONIC_GLOBAL**.
- Corner sides: Poisson/NB2 mixture weight **0.75**, calibrated by **PLATT_GLOBAL**.
- Corner totals: same coherent mixture, calibrated by **PLATT_ROLE_COMP_RIDGE_L1**.
- Common pre-calibration corner alpha: **0.099881**.

## SELECT evidence versus identity

- Goals: identity LL 0.677879 → selected LL 0.671208.
- Corner sides: identity LL 0.579224 → selected LL 0.578956.
- Corner totals: identity LL 0.618977 → selected LL 0.613974.

## Support boundary

Unsupported raw-probability bins remain explicit metadata and must not be treated as equally credible by Layer 5.

Next: freeze the Layer 5 market-surface/disagreement policy before opening protected outcomes.
