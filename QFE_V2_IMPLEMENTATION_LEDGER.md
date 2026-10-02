# QFE V2 Implementation Ledger

Last updated: 2026-10-02 (America/Bogota)

Status: **ACTIVE GOVERNANCE / IMPLEMENTATION TRACKER**

This document is the living implementation ledger for QFE V2. It complements
`QUANT_FOOTBALL_SOURCE_OF_TRUTH.md`: the Source of Truth defines what QFE must
be; this ledger records what has actually been implemented, verified, frozen,
merged, rejected, or remains open.

The ledger must be updated in the same PR as a material architecture milestone.
A checkbox means code/evidence exists and passed the stated gate; it does not
mean commercial validation.

## 1. Product status

- [x] **QFE V2 is the sole active product on `main`.**
- [x] Legacy CHAMPION deprecated and prevented from re-entering active source.
- [x] Frozen V3/V3.7/V3.8 worktrees classified as experiment evidence only.
- [x] No LLM in the QFE V2 probability, feature, calibration, ensemble, or
  disagreement-selection path.
- [x] Independent `p_model` architecture remains odds-blind.

Current governing main after deprecation:
- Foundation V1 merge: `e68d9addc346bec96754d8633c76622f855a1010`
- Single-product/deprecation merge: `5b2abf9565221f01cd60f9592357592f466c72fc`

## 2. Foundation V1 — data/semantic integrity

Status: **MERGED / FROZEN**

- [x] Stable provider fixture/team/competition/season identity.
- [x] Provider-scoped semantic capability registry.
- [x] Regulation-time goals/corners/bookings target contracts.
- [x] Bookmaker-specific settlement compatibility contracts.
- [x] Missing != zero enforcement.
- [x] Extra-time/shootout fail-closed target handling.
- [x] Integer/half/quarter Asian settlement states.
- [x] Odds-blind PIT historical feature reconstruction.
- [x] Same-row target leakage structurally prevented.
- [x] Global / competition / venue historical contexts.
- [x] Content-addressed immutable dataset artifacts.
- [x] Atomic staged write + fsync + publish.
- [x] Exact source-file SHA256 provenance.
- [x] Exhaustive canonical cached-season audit.

Frozen Foundation V1 evidence:
- Bundle hash: `e3055bc0ed5afed16e2230d177f8ac4a641092c79d0511fcbba26d0efdb2cf52`
- 19 canonical seasons / 6 competitions.
- 5,640 normalized finished fixtures.
- 5,636 canonical stats payloads selected.
- 4 genuinely missing canonical stats payloads.
- 0 canonical stats conflicts.
- Goals labels: 5,640 / 5,640 available.
- Corners labels: 5,609 / 5,640 available.
- Bookings: blocked by source/bookmaker settlement semantics.

Foundation evidence files:
- `evidence/foundation_v1/QFE_FOUNDATION_V1_CAPABILITY_COVERAGE.json`
- `evidence/foundation_v1/QFE_FOUNDATION_V1_AUDIT.md`

## 3. Layer 2 — multi-season state and conservative baseline

Status: **READY FOR MERGE on `feat/qfe-v2-layer2`**

### 3.1 Canonical multi-season PIT corpus

- [x] Compose every audit-usable canonical season into one chronology.
- [x] Re-verify exact season audits before composition.
- [x] Load only source files fingerprinted by accepted season audits.
- [x] Detect duplicate fixture identity across seasons.
- [x] Carry team-global history across season boundaries.
- [x] Carry team-global history across competition transitions.
- [x] Keep team-in-competition history separate from global team history.
- [x] Bind season-audit hashes, source bundle, match-content hash and PIT manifest
  into a multi-season corpus manifest.
- [x] Freeze a real-corpus Layer 2 manifest/evidence artifact.

Implementation:
- `src/research/dataset/multiseason.py`

### 3.2 Dynamic target-specific hierarchical strength

Architecture:

`global environment -> competition environment -> team global venue-role -> team-in-competition venue-role -> opponent-adjusted forecast`

- [x] Goals target implementation.
- [x] Corners target implementation.
- [x] Separate HOME_ATTACK / HOME_DEFENCE / AWAY_ATTACK / AWAY_DEFENCE states.
- [x] Exponential time decay.
- [x] Partial pooling at every hierarchy layer.
- [x] Team strength transfer across competition changes via shrunk global factor.
- [x] New-competition team-specific support resets to zero instead of pretending
  old-competition observations were directly comparable.
- [x] Same-kickoff forecasts emitted before any same-kickoff update.
- [x] Missing target rows abstain from updating that target state.
- [x] Extra-time/shootout fixtures excluded from regulation-state updates.
- [x] Explicit effective support and supported/unsupported state.
- [x] No odds or market probability input.
- [ ] Chronological development procedure for decay/prior hyperparameters.
- [ ] Uncertainty intervals beyond effective-support diagnostics.

Implementation:
- `src/research/models/dynamic_count_strength.py`

### 3.3 Conservative count baseline

Current benchmark distribution: **independent Poisson**, used as a conservative
baseline rather than a final distributional claim.

- [x] Home/away expected count forecast.
- [x] Coherent total mean (`lambda_home + lambda_away`).
- [x] Integer-line over/under/push probability handling.
- [x] Half-line binary over/under probability handling.
- [x] Quarter lines rejected at probability interface and left to split-stake
  settlement contract.
- [x] One-step-ahead walk-forward forecast generator.
- [x] Poisson count NLL diagnostic primitive.
- [x] Real 5,640-match walk-forward smoke/evidence run.
- [x] Paired comparison versus competition-only climatology baseline.
- [ ] Chronological development/protected split definition.
- [ ] Goals dependence candidate (Dixon-Coles/bivariate) benchmark.
- [ ] Corners overdispersion candidate (NB2 or other) benchmark.

Important: current default hyperparameters are **benchmark defaults**, not
promoted values. They must not be tuned on future protected/prospective data.

Frozen Layer 2 development evidence:
- Evidence bundle: `evidence/layer2/QFE_LAYER2_DEVELOPMENT_SMOKE.json`
- Human summary: `evidence/layer2/QFE_LAYER2_DEVELOPMENT_SMOKE.md`
- Bundle hash: `9fea7028abf12961990723aebb5008ab86d1f38ce08fbf3c3e2bb5feae9d9b0d`
- Multi-season corpus manifest: `bde8a51688674f0ca5d7b17426327cc55d5d44ce4106443eb1a2f5b780419e22`
- Multi-season PIT manifest: `6aeb680aa82e1a9468a44396eab41e33bc7e3daefab8ace6ad17aa11ca8085e8`
- Real corpus: 5,640 fixtures / 19 seasons / 6 competitions / 5,655 source files.
- Goals development smoke: dynamic NLL improvement vs competition climatology `+0.015567`; MAE improvement `+0.021007`; 85.21% support.
- Corners development smoke: dynamic NLL improvement `+0.027386`; MAE improvement `+0.043232`; 85.18% support; 31 missing corner outcomes remain excluded.
- Dynamic NLL delta is positive in all six competitions for both goals and corners.
- Weak seasons are retained in the frozen report and were not tuned away.

Scientific state: **DEVELOPMENT_SMOKE_ONLY**. This is evidence that dynamic
team/opponent state contains useful count-predictive information relative to a
competition-only climatology. It is not protected OOS evidence, calibrated
market-event probability evidence, or commercial validation.

## 4. Next required modeling layers

### Layer 3 — chronological component evaluation

- [ ] Freeze development/calibration/protected chronological folds.
- [ ] Conservative climatology baseline.
- [ ] Dynamic hierarchical baseline evaluation.
- [ ] Structured goals model comparison.
- [ ] Structured corners model comparison.
- [ ] Nonlinear tabular candidate with leakage-safe preprocessing.
- [ ] Deterministic similar-opponent candidate.
- [ ] Immutable component OOF prediction artifacts.
- [ ] Paired LL/Brier/count-distribution comparisons with fixture/time blocks.

### Layer 4 — ensemble and calibration

- [ ] Fit constrained non-negative ensemble on earlier OOF predictions only.
- [ ] Compare equal-weight / best-single / conservative anchor.
- [ ] Platt calibration.
- [ ] Beta calibration.
- [ ] Isotonic only where support is sufficient.
- [ ] Calibration intercept/slope/reliability/probability-region support.
- [ ] Freeze candidate standalone `p_model` stack.

### Layer 5 — market-relative research

- [ ] Horizon-matched timestamped market snapshots.
- [ ] Preregister primary no-vig method.
- [ ] Market-only calibrated comparator.
- [ ] QFE-vs-market incremental information analysis.
- [ ] OOD/support/component-consensus diagnostics.
- [ ] Freeze disagreement eligibility policy.
- [ ] Separate global and disagreement-subset scorecards.

### Layer 6 — prospective commercial evidence

- [ ] New QFE V2 shadow pilot; no reuse of legacy CHAMPION product path.
- [ ] Immutable pre-outcome prediction commitments.
- [ ] Genuine closing lines from QFE-owned pre-kickoff snapshots.
- [ ] Prospective LL/Brier/calibration.
- [ ] CLV / closing movement diagnostics.
- [ ] Settlement/economic evaluation under frozen policy.

## 5. Non-negotiable gates

A Layer 2+ model is not promoted because it:
- finds larger disagreement;
- wins a small set of fixtures;
- has higher hit rate;
- looks better on exposed pilot outcomes.

Promotion requires chronological OOS probability evidence. Any protected-design
defect discovered after freeze requires abort/version/new experiment.

## 6. Current immediate gate

Layer 2 merge gate status:

1. [x] Run canonical multi-season builder over the complete cached corpus.
2. [x] Verify 5,640 fixture identity and exact source lineage.
3. [x] Generate goals and corners walk-forward baseline forecasts.
4. [x] Inspect support/cold-start/competition-transition and competition slices.
5. [x] Final full repository tests and import sweep on the exact staged state: 235 tests / 61 research modules / 0 import failures.
6. [x] Freeze Layer 2 implementation/development evidence.
7. [x] Final review passed; branch authorized for PR/merge. Post-merge commit is recorded in a ledger-only follow-up.
