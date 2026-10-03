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

Status: **MERGED TO `main`**

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

Layer 2 merge record:
- Feature commit: `e9eafabff`
- PR: `#30` — QFE V2 Layer 2: multi-season PIT corpus and dynamic hierarchical baseline
- Main merge commit: `477d7594e0fa042c28bb84430a681010d22acbf8`

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

Status: **MERGED TO `main`**

- [x] Freeze development/calibration/protected chronological folds.
- [x] Conservative dynamic-Poisson anchor.
- [x] Dynamic hierarchical baseline evaluation.
- [x] Structured goals comparison: Poisson, NB2, rho correction, full competition Dixon-Coles.
- [x] Structured corners comparison: Poisson vs NB2 dispersion.
- [x] BTTS dependence comparison for Dixon-Coles.
- [x] Nonlinear PIT-only HistGradientBoosting Poisson benchmark.
- [x] Deterministic same-competition similar-context benchmark.
- [x] Immutable component OOF prediction artifacts.
- [x] Paired LL/Brier/count-NLL comparisons with weekly-block bootstrap uncertainty.
- [x] Calibration outcomes remain unscored.
- [x] Protected 2026/27 outcomes remain unscored.

Layer 3 merge record:
- Chronology commit: `da2f072c4`
- Component-evaluation commit: `f7dcbbfe7`
- PR: `#32` — QFE V2 Layer 3: frozen chronology and component OOF evaluation
- Main merge commit: `34edf14550b301987db4c1d60eaf266aecf4a9dd`

Frozen chronology:
- Warm-up: 552 fixtures.
- Development: 3,812 fixtures.
- Calibration: 959 fixtures.
- Protected: 317 fixtures from 2026-08-01 onward across all six competitions.
- Chronology manifest: `9cf5e680174b78b639a80bd85498ed04f3f79482634ced8194ae5c9192495269`.

Frozen Layer 3 evidence:
- Final component-evaluation bundle: `bc7ca4aa57577cd15902062718125537afacc6aaa04092322ffb3d27be28ee5c`.
- Structured-development diagnostic bundle V2: `709c1daf0eea03fb439460d41cd4f3f3152009963bad69a77a2cf28c72f26c62`.
- Structured OOF semantic hash: `c41dcacca9ccb47b5bbeb2f732b8398ff0a2ba7fbf6430bd430132e79385400d`.
- Tabular OOF semantic hash: `c9fd3c986ee5bbcfe9b00aef242a2929ccec04d08a53bdeb63df3a68744f3e4f`.
- Similar-context OOF semantic hash: `8388c6604750ea1f8cfe9435ecf26dd20fd5a044bc6af553f2c75dab65896c23`.
- Development fold manifest: `b019226b8ff7ff278cb334909becc847642838ca9fe3fca269a5332565123e1a`.
- Provenance repair: preliminary structured evidence V1 (`5a0eef3917312c775ac0e7cfe8588ba42a5848ac977f46905b6be02f24fc9b1d`) was superseded before merge because `chronology.py` gained the frozen OOF-fold definitions after that report was generated. The tournament scientific payload/decisions were asserted identical; V2 rebinds the same results to the final implementation fingerprints.
- `evidence/layer3/QFE_LAYER3_COMPONENT_EVALUATION.json`
- `evidence/layer3/QFE_LAYER3_COMPONENT_EVALUATION.md`

Development conclusions:
- **Corners side-NB2 = BINARY_MARKET_CANDIDATE_MIXED_TOTAL_DISTRIBUTION.** On fold OOF it improves fixed-line binary Log Loss by `+0.002443` (95% weekly-block CI `+0.000771` to `+0.004025`) and Brier by `+0.001134` (CI `+0.000336` to `+0.001881`), but worsens total-count NLL by `-0.011440` (CI `-0.021534` to `-0.000997`). The earlier full-development side-joint likelihood diagnostic is positive; these are different scoring objects and are preserved separately.
- **Goals similar-context = WEAK_MIXED_SIGNAL_CIS_CROSS_ZERO.** Mean total-count NLL, binary LL and Brier improvements are positive, but all paired CIs cross zero; retain only as a possible ensemble diversifier.
- Goals dynamic Dixon-Coles / goal NB2 / full competition Dixon-Coles: not supported or inconclusive as standalone replacements.
- Nonlinear HistGradientBoosting: materially worse on both goals and corners; rejected as standalone.
- Similar-context corners: weak/inconclusive as standalone.

Scientific state: **DEVELOPMENT_OOF_ONLY**. No calibration, ensemble fitting, market comparison, or protected scoring has occurred.

### Layer 3.1 — multi-line / team-side corner market-event coverage

Status: **MERGED TO `main`**

Layer 3.1 merge record:
- Protocol commit: `b4311cf72`
- Implementation/evidence commit: `54088a373`
- PR: `#34` — QFE V2 Layer 3.1: multi-line team corners and prospective evidence warehouse
- Main merge commit: `5dc01b60930ff62ac2aa9f443962c8f59c384b0f`

Preregistration was committed before scoring:
- Protocol commit: `b4311cf72`
- Protocol hash: `565aaf432f64b8b1110cf94aa8f702dfb128d07fe578a54c69e13c0b92aa4f69`
- SIDE lines: 2.5, 3.5, 4.5, 5.5, 6.5, 7.5.
- TOTAL lines: 7.5, 8.5, 9.5, 10.5, 11.5, 12.5.
- Roles: HOME and AWAY.
- Primary hypotheses are pooled SIDE and pooled TOTAL; no best-line search is permitted.
- Per-line, role and competition slices are diagnostic only.
- Market odds, CALIBRATION outcomes and PROTECTED outcomes are forbidden.

Implementation/evidence:
- [x] Reuse the frozen Layer 3 corner dynamic-intensity configuration.
- [x] Refit NB2 dispersion inside each earlier-only DEVELOPMENT OOF fold.
- [x] Assert refitted fold alphas exactly match frozen Layer 3 fold values.
- [x] Generate coherent Poisson and side-NB2 probability ladders.
- [x] Enforce monotonic decreasing P(OVER) with increasing line.
- [x] Pool all preregistered lines rather than selecting the best line.
- [x] Weekly-block paired uncertainty for Log Loss and Brier.
- [x] Missing corner labels excluded, never imputed.

Preregistered DEVELOPMENT result (94,752 candidate rows / 47,376 paired market-event cells):
- **SIDE_CORNERS: `NB2_DEVELOPMENT_CANDIDATE`.** 31,584 paired fixture-role-line cells. Binary Log Loss improvement `+0.00473845`, 95% weekly-block CI `+0.00349661` to `+0.00606511`; Brier improvement `+0.00142206`, CI `+0.00101278` to `+0.00183213`.
- HOME role: Log Loss improvement `+0.00567222`, CI `+0.00350617` to `+0.00788121`.
- AWAY role: Log Loss improvement `+0.00380469`, CI `+0.00249668` to `+0.00517553`.
- **TOTAL_CORNERS: `NB2_WEAK_OR_INCONCLUSIVE`.** 15,792 paired fixture-line cells. Log Loss improvement `+0.00154705`, CI `-0.00014111` to `+0.00315432`; Brier improvement `+0.00041332`, CI `-0.00023313` to `+0.00102977`.
- Full scientific artifact hash before storage compaction: `5ce882ec18bf40dbe3d7d29d43a79c21e1885c6a64046c0d70bb5fe8b9769e75`. Storage compaction does not alter this scientific artifact hash.
- Compact summary file SHA256: `4419d2fe579a51131515556e338bc01a26017dee80dbb186e53e054c1f6e27f0`.
- Deterministic compressed OOF rows SHA256: `57579cb15c7ea497d57f9b3ceb7037874f74e8cdd3543a419cbf01e5e76f476e`; semantic rows hash `2828d67342cd0a6a06400acb8ff2fe336fdd6483b2bf075456b86bf6a09231ba`.
- Compact verifier reconstructs the complete 94,752-row scientific artifact and reproduces `5ce882ec18bf40dbe3d7d29d43a79c21e1885c6a64046c0d70bb5fe8b9769e75`; canonical JSONL and deterministic gzip encoding are verified.

Interpretation: side-specific NB2 is eligible for the Layer 4 corners component set. Match-total NB2 is not promoted by Layer 3.1 and remains weak/inconclusive. This does not authorize calibration, market comparison, protected scoring or commercial claims.

### Prospective experiment evidence warehouse

Status: **SNAPSHOT V1 FROZEN / EXTERNAL EVIDENCE ONLY**

The implementation ledger tracks code progress; this warehouse separately snapshots real prospective research evidence. It is explicitly **not V2 training data**.

Snapshot V1:
- Frozen at: `2026-10-03T03:34:04Z`.
- Snapshot semantic hash: `afb62230b658aa74fce6feba5f7f0912c53817e526fcac6d07122aa02aec44e1`.
- Snapshot JSON SHA256: `6c3e77bc776bed004c1d3934913e8e8bc02929dfeeea774d97e4ea933808ce73`; normalized declaration JSONL SHA256: `0c6435b742327bbdce934b243a80a8e71b21cc06b2c879a8f7dc70f691e1b0bb`.
- 30 normalized declaration-arm records; 12 settled; 18 open at the frozen timestamp.
- Source event hash chains, chain heads and market-observation hashes verified before normalization.
- Every source ledger, fixture ledger, market ledger, prediction freeze, experiment model freeze and experiment spec is SHA256 fingerprinted in the snapshot.
- Snapshot builder aborts if an actively-running source bundle changes during ingest.

Source bundles:
- V3.7.1 Future-50: 5 normalized declarations / 1 settled; source bundle `4d0a7670d6d5348baf0cfc6410519065659c50c8e247a097eb45d10b3337f344`.
- V3.8.1 Paired-50: 6 normalized arm records / 2 settled; source bundle `3f31cbf902cbdbb185233177eecf80772bb6f3f2630d0a8fd9eac72e572b6caa`.
- Team Corners V1: 19 declarations / 9 settled; source bundle `4060c6b1c4322998913f584e4abc127df0dbe6c36627b5620dc079be342b87e0`.

The normalized records preserve source event/freeze hashes, entry model/market probabilities, offered price, disagreement, relevant market vintages, settlement, proper scores, unit P&L and CLV/closing probability when source evidence supports it. No unsettled record is assigned an outcome.

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

Layer 3.1 / evidence-warehouse merge gate:

1. [x] Freeze Layer 3.1 protocol in Git before scoring.
2. [x] Score only DEVELOPMENT OOF; CALIBRATION/PROTECTED outcomes and market odds remain inaccessible.
3. [x] Preserve whole-ladder/role aggregation and no-best-line multiplicity policy.
4. [x] Build read-only prospective evidence warehouse from the three authoritative versioned experiment stores.
5. [x] Verify all source ledger chains and market observation hashes.
6. [x] Regenerate compact Layer 3.1 evidence from scratch; reproduce the same scientific artifact hash and verify lossless deterministic compact storage.
7. [x] Run full repository suite, import sweep, Git integrity and prior-layer hash checks: 283 tests passed; 75 research modules imported; 0 failures; prior tracked evidence unchanged.
8. [x] Exact staged-state validation passed; branch authorized for PR/merge.
9. [x] Commit and merge via PR #34 at `5dc01b60930ff62ac2aa9f443962c8f59c384b0f`; merge record added in this docs-only follow-up.

The 959 CALIBRATION fixtures and 317 PROTECTED fixtures remain unopened for Layer 4 selection/protected scoring respectively.
