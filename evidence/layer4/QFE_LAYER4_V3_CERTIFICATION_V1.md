# QFE V2 Layer 4 — V3 Certification V1

Certification hash: 1a0e34e1473b22088b9d9340393034a2e2f829ad93790afbbd5f66bb7c560503

Status: **PASS — OPERATIONAL CALIBRATED p_model REPAIR EVIDENCE; NOT FRESH VALIDATION**

## What Layer 4 established

The repaired model required calibration: IDENTITY did not win any group on the frozen CALIBRATION_SELECT slice.

- Goals: Log Loss 0.677835 → 0.671897; Brier 0.242427 → 0.240025; selected ISOTONIC_GLOBAL.
- Corner sides: Log Loss 0.579235 → 0.578967; Brier 0.197500 → 0.197404; selected PLATT_GLOBAL under the frozen complexity tie rule.
- Corner totals: Log Loss 0.619012 → 0.613997; Brier 0.214717 → 0.212549; selected PLATT_ROLE_COMP_RIDGE_L1.

CALIBRATION outcomes were historically exposed under Layer 4 V1. Therefore these improvements are repair/development evidence, not a fresh confirmatory holdout.

## V2 abort and V3 repair

V2 emitted p_model=1.0 on three goals rows and was aborted before prospective use.

V3 was preregistered before V3 output generation. It reuses the exact V2 selected methods/specs and changes only the final probability bound:

p_model = clip(calibrator(raw_probability), 1e-6, 1-1e-6)

Only 3 of 18,203 p_model values changed, all by at most 1e-6. There are now no exact 0 or 1 probabilities.

V3 model freeze hash: bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2

## Frozen operational stack

- Goals O2.5: dynamic + similar-context weight 0.20; ISOTONIC_GLOBAL.
- Corner sides: coherent Poisson/NB2 mixture weight 0.75; PLATT_GLOBAL.
- Corner totals: same mixture; PLATT_ROLE_COMP_RIDGE_L1.
- Common corner NB2 alpha: 0.099909.
- Output bound: [0.000001, 0.999999].

## Validation

- Final repository suite: **343/343 PASS**.
- Research imports: **87/87 PASS**.
- Diff check: **PASS**.
- Exact V3 regeneration under immutable writer: **PASS**.

## What this does NOT mean

This does not mean the complete model has passed final OOS validation. DEVELOPMENT selected the model; CALIBRATION selected calibration methods, but CALIBRATION was already exposed historically. A new future prospective cohort is required to measure genuine post-freeze Log Loss, Brier, calibration/ECE and market-relative performance.

Corners remain modelable, but bookmaker corner comparison is fail-closed until provider-to-bookmaker settlement equivalence is proven and frozen.

## Next gate

Rebind and revalidate Layer 5 to the V3 model freeze. Do not reuse the exposed former-317 cohort as a final holdout. After Layer 5 is frozen, create a new future prospective outcome-blind cohort for genuine validation.
