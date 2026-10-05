# QFE V2 Implementation Ledger

Last updated: 2026-10-05 (America/Bogota)

Status: **ACTIVE GOVERNANCE / IMPLEMENTATION TRACKER**

This document is the living implementation ledger for QFE V2. It complements
`QUANT_FOOTBALL_SOURCE_OF_TRUTH.md`: the Source of Truth defines what QFE must
be; this ledger records what has actually been implemented, verified, frozen,
merged, rejected, or remains open.

The ledger must be updated in the same PR as a material architecture milestone.
A checkbox means code/evidence exists and passed the stated gate; it does not
mean commercial validation.

## Current certified state — 2026-10-05

- **Certified repaired foundation:** PR #40 merge `651b98fb82e3cf3cc0a47da13f95cebe5fb1862a`.
- **PIT contract:** source kickoff + 6h reconstructed availability embargo <= target kickoff - 6h decision horizon.
- **Foundation validation:** 334 repository tests passed at the exact PR #40 merge; focused PIT call-path audit passed.
- **PR #41 Layer 2 replay:** **ABORTED on independent audit** — all-corpus scoring included 959 CALIBRATION + 317 later-designated PROTECTED fixtures; V3 successor required.
- **PR #42 Layer 3 replay / PR #47 certification:** **INDEPENDENT AUDIT PASS WITH RESEARCH CAVEATS** — valid DEVELOPMENT candidate-selection evidence only; no final-model or holdout claim.
- **PR #43 Layer 3.1 replay / PR #48 certification:** **INDEPENDENT AUDIT PASS WITH RESEARCH CAVEATS** — valid DEVELOPMENT component-eligibility evidence only; SIDE NB2 eligible for Layer 4, TOTAL NB2 not promoted.
- **Layer 4 repaired replay:** **V2 model freeze ABORTED** for exact-boundary probability output; **V3 bounded calibrated p_model CERTIFIED operationally** as repair evidence, not fresh OOS validation.
- **Former 317-fixture PROTECTED cohort:** **EXPOSED PRE-FREEZE / NOT VALID AS FINAL HOLDOUT**. Membership remains immutable for diagnostics; a new future prospective holdout is required.
- **Goals market comparison:** eligible under the accepted regulation-time contract.
- **Corners:** modelable, but bookmaker comparison remains fail-closed until provider corner settlement equivalence is independently proven and frozen.
- **Bookings:** model/market comparison blocked; provider market availability must not be confused with QFE target-comparison eligibility.
- **Layer 5 V1.2:** **CERTIFIED / ACTIVE** — bound to Layer 4 V3; V1.1 numerical market policy unchanged; former 317 cohort diagnostic-only; corners bookmaker comparison fail-closed; new future cohort machinery outcome-blind and pre-T6 enforced.
- **Prospective V1 writer:** **CERTIFIED** — exact historical counterfactual replay reproduces 19/19 frozen Layer 4 probabilities with zero drift; target outcome/stat leakage, stale history, post-T6 capture and non-cohort targets fail closed.
- **Prospective incremental history V1:** **CERTIFIED / PREDICTION-ELIGIBLE** — 92 new finished fixtures across all six frozen competitions, 92/92 stats captured, 0 base overlap, combined 5,732-row PIT rebuild PASS.
- **Prospective Cohort V1:** **FROZEN / CERTIFIED** — 135 fixtures, all scheduled fixtures in the preregistered Oct 7–21 UTC window, no cap or model/market filter; earliest T-6h cutoff is Oct 9 12:00 UTC.
- **Prospective T-6h runner:** **CERTIFIED / TIMER-READY** — 5-minute cadence, complete pre-cutoff history refresh, all p_model bundles frozen before odds, late backfill forbidden, schedule-change abstention immutable.
- **Prospective T-6h deployment:** **CERTIFIED / DEPLOYED** — prediction runner validated from canonical main; temporarily paused only during scanner branch work and must be re-enabled after scanner deployment.
- **Odds price movement scanner V1:** **CERTIFIED / DEPLOYMENT-READY** — passive Goals O/U 2.5 capture every 5 minutes from T-6 to kickoff; operational close uses latest valid pre-kickoff quote within 600s under fixed bookmaker hierarchy; no post-kickoff provider call, no price-shopping, no p_model feedback.
- **Operational gate:** merge/deploy the scanner as a separate timer and re-enable both services from canonical main. Then freeze the stack. Earliest registered T-6h cutoff remains **2026-10-09 12:00 UTC**. No live prediction, price path, closing line, or outcome score exists yet.

Historical sections below remain audit evidence. Where an older status conflicts with this current-state block, this block governs operational sequencing.

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
- [x] Goals bookmaker settlement compatibility verified; corners comparison remains unverified; bookings comparison remains blocked.
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

Independent PR #47 audit:
- Audit evidence: evidence/layer3/QFE_PR47_INDEPENDENT_AUDIT_V1.json and .md.
- Audit hash: 90f427a82bf215ac7ee0884e04fe78fe40502562dc362747c615868bb20da3b7.
- Exact independent regeneration passed for chronology, tournament, goals/corners OOF, structured fold OOF and component evaluation.
- Exact-SHA validation: 35 focused tests passed; 338 full repository tests passed; 86 research modules imported; diff check passed.
- Scope: DEVELOPMENT selection only. Research caveats include non-selection-adjusted winner uncertainty, edge-of-grid selected intensities, near-tied top configurations and non-nested intensity hyperparameter selection.

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

Independent PR #48 audit:
- Audit evidence: evidence/layer31/QFE_PR48_INDEPENDENT_AUDIT_V1.json and .md.
- Audit hash: c0d33ba10991aae66100e2186781c6c0100657db1fea882aa9f5488d2cdba7fc.
- Byte-exact regeneration passed for the compact summary, Markdown and deterministic 94,752-row gzip evidence; full artifact verifier reproduced the scientific artifact hash.
- Exact-SHA validation: 42 focused tests passed; 338 full repository tests passed; 86 research modules imported; diff check passed.
- Scope: DEVELOPMENT component eligibility only. Important caveats: same-era reuse of the Layer 3-selected NB2 candidate, non-nested intensity selection, correlated multi-line cells summarized through 49 time blocks, and an imprecise UTC_CALENDAR_WEEK label for epoch-aligned 7-day blocks. Audit-only ISO-week sensitivity leaves both frozen decisions unchanged.
- Provider-to-bookmaker corner settlement equivalence remains unverified; no bookmaker corner comparison is authorized.

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

## PIT horizon repair — scientific abort/version event

Status: **ACTIVE REPAIR / PROTECTED STILL UNOPENED**

A pre-protected Layer 5 audit discovered that `DynamicHierarchicalCountBaseline.walk_forward()` updated historical state immediately after earlier kickoffs, while the registered Foundation PIT contract admits a result only when `source kickoff + 6h embargo <= target kickoff - 6h prediction horizon`. Foundation PIT features were correct; the dynamic walker was not.

- Defect report: `evidence/pit_horizon_repair/QFE_PIT_HORIZON_DEFECT_V1.json`.
- Protected outcomes opened/scored at discovery: **0**.
- Corrected dynamic model version: `qfe-conservative-dynamic-count-v2-pit-horizon`.
- Goals DEVELOPMENT rows changed under identical config: **2021/2650 (76.3%)**; mean absolute probability movement **0.018 pp**, max **0.323 pp**.
- Corners rows changed: **2013/2632 (76.5%)**; mean absolute movement **0.027 pp**, max **0.360 pp**.
- Aggregate DEVELOPMENT LL differences are tiny, but the old evidence is still point-in-time invalid.

Scientific consequence:
- Foundation V1 and frozen chronology remain valid.
- Dynamic-derived Layer 2, Layer 3 structured/component evidence, Layer 3.1, and Layer 4 V1 model freeze are **SUPERSEDED / NOT ELIGIBLE FOR PROTECTED SCORING**.
- Old artifacts remain immutable for audit; they are not rewritten or deleted.
- The 959 previously called CALIBRATION are now acknowledged as **exposed pre-protected repair data**.
- Historical note at the time: the 317 fixtures were then treated as the final protected test. **Current correction:** later audit proved this cohort had already been consumed by Layer 2 V1 before protected designation; it is exposed and not eligible as a final holdout.
- Layer 5 protected evaluation is paused until repaired Layers 2–4 and Layer 5 policy are frozen.

### Layer 4 — ensemble and calibration

Status: **V1 MERGED BUT SUPERSEDED BY PIT-HORIZON REPAIR / PROTECTED UNOPENED**

Layer 4 merge record:
- Protocol commit: `7a73e1ac2`.
- Audit/governance commit: `9a628a286`.
- DEVELOPMENT ensemble commit: `f528f7a6e`.
- Raw CALIBRATION + selector commit: `2c020913d`.
- Final model-freeze commit: `5ab2380e7`.
- PR: `#36` — QFE V2 Layer 4: ensemble, calibration and standalone p_model freeze.
- Main merge commit: `4858281f9e7dc3613fa7b0bb12b939521ce3b87c`.

Frozen artifacts and sequence:
- Protocol commit: `7a73e1ac2`; protocol hash `80f3f0c61fbd9e707a28376fc9745a16df468cb04fb34e4e3191ee391cb7d1ee`.
- Protocol audit hash: `cb919516908b7b3e57b48e787fb71d7f61ba741af5a8956c52f360f4805c0800`.
- DEVELOPMENT ensemble selection hash: `3cf13c8e2e4c625ab8798a7f633fee58dd2ac8e1dd14e718b755c5fae47ef41f`.
- Goals similar-context weight: **0.20**; the preregistered grid is not expanded after observing that the maximum grid point won.
- Corners coherent Poisson/NB2 joint-mixture weight: **0.75**.
- Execution contract hash: `a09ec9b617507654ad390f1edb4e980b6d4a5049e46049bb23f0f61cb29f5d95`.
- Raw CALIBRATION substrate hash: `94d29f3d396f802049e45b58b45c4115e926ba40d0e715ff27864939a4ec20c4`; **959 fixtures / 18,203 event cells / 0 protected / 0 market inputs**.
- CALIBRATION split: **755 FIT fixtures / 204 SELECT fixtures**.
- Pre-calibration common corner NB2 alpha: **0.0998810331361972** from 8,668 eligible side observations strictly before CALIBRATION.
- Calibrator selector implementation commit: `2c020913d`; frozen before SELECT outcomes were scored.
- Calibration run hash: `f3770a8bc5fe80c36cb3dcf52d3dc56671bcdfcea3097be5ef17debe278192f2`.
- Standalone model freeze hash: `e33af913f4c27ce33355c78792419ad8cee73e3f16ce7c685781a010d386b3ea`.
- Independent Layer 4 integrity-audit hash: `78f5925fc6cc1821e35724663da28a91a82390eab02c87cfdb03a0e07ed8b9e2`; selector recomputation, monotonicity, full artifact regeneration and code/source bindings all PASS.

Frozen model stack:
- **Goals total 2.5:** dynamic hierarchical Poisson + 0.20 similar-context expected-total diversifier → **ISOTONIC_GLOBAL** calibration. SELECT LL: `0.677879` identity → `0.671208` isotonic.
- **Corner sides 2.5–7.5:** coherent 0.75 NB2/0.25 Poisson mixture → **PLATT_GLOBAL** calibration. SELECT LL: `0.579224` identity → `0.578956` Platt. Ridge L1 had slightly lower LL but was inside the frozen `0.0005` tie tolerance, so the simpler Platt mapping correctly won.
- **Corner totals 7.5–12.5:** same coherent 0.75 NB2/0.25 Poisson joint mixture → **PLATT_ROLE_COMP_RIDGE_L1** calibration. SELECT LL: `0.618977` identity → `0.613974` ridge.

Prediction-support boundary:
- Goals raw-probability support is strongest in `0.30–0.60`; the `0.60–0.70` bin has only 29 unique fixtures and remains unsupported.
- Corner-side calibration has ≥30 unique fixtures in every frozen raw-probability bin.
- Corner-total extremes `<0.10` and `>=0.80` remain unsupported.
- Reliability intervals are empirical calibration-support bands, **not individual-fixture confidence intervals**.
- OOD/support metadata remain diagnostics in Layer 4; Layer 5 must preregister any abstention/eligibility policy.

Layer 4 completion gates:
- [x] Fit constrained ensemble weights on DEVELOPMENT OOF only.
- [x] Preserve coherent count distributions across corner side/total lines.
- [x] Materialize odds-blind CALIBRATION raw predictions with protected rows structurally excluded.
- [x] Fit Platt, beta, isotonic and partially pooled role/competition ridge challengers under frozen fixture-balanced weights.
- [x] Select calibrators on CALIBRATION_SELECT only; refit the selected method on all CALIBRATION only after selection.
- [x] Enforce calibrated cross-line monotonicity.
- [x] Attach component-dispersion, history support, OOD and calibration-region support metadata.
- [x] Freeze the standalone candidate `p_model` stack.
- [x] Complete exact-state repository validation and merge Layer 4. Independent integrity audit: selector/monotonicity/regeneration/code-binding PASS; merged via PR #36.

#### Current repaired Layer 4 successor — V3

Status: **OPERATIONAL CALIBRATED p_model CERTIFIED AS REPAIR EVIDENCE / NOT FRESH VALIDATION**

The historical V1 record above remains immutable. After the repaired PIT chain and independent Layer 2/3/3.1 audits:

- V2 repaired protocol commit on the certified chain: `c9866caaeea1f928e6cbd04b8e9ccaed11a6c7b0`.
- V2 protocol hash: `be4f49babfb3e345d457bfe1ca87542888cfc0c6078e0a2427c3d7c18014f7e3`.
- Repaired DEVELOPMENT ensemble selection hash: `3ab75a1be4a0193b3b0f47ef46201c966b4555b3a3573531fd7cd666d9897213`.
- Repaired goals similar-context weight: **0.20**.
- Repaired coherent corner Poisson/NB2 mixture weight: **0.75**.
- Raw CALIBRATION repair substrate: **959 fixtures / 18,203 event cells / 755 FIT / 204 SELECT / 0 market / 0 former-PROTECTED rows**.
- Raw calibration hash: `ac4e24650f7f138db89306d74f4ea0d8010e369f8e64951f8aad9dba8b5050c5`.
- Common pre-CALIBRATION corner NB2 alpha: **0.0999085576** from 8,668 side observations.
- V2 calibration run hash: `d6a0b7f6b98acbccc54033371c2c2cad785bc18575a651296aed8913370e7346`.

V2 calibrator selection on the frozen CALIBRATION FIT/SELECT policy:

- **GOALS_TOTAL:** IDENTITY LL `0.677835` / Brier `0.242427` → `ISOTONIC_GLOBAL` LL `0.671897` / Brier `0.240025`.
- **CORNERS_SIDE:** IDENTITY LL `0.579235` / Brier `0.197500` → `PLATT_GLOBAL` LL `0.578967` / Brier `0.197404`. Ridge L1 had lower LL but fell within the frozen `0.0005` tie tolerance, so the simpler global Platt mapping correctly won.
- **CORNERS_TOTAL:** IDENTITY LL `0.619012` / Brier `0.214717` → `PLATT_ROLE_COMP_RIDGE_L1` LL `0.613997` / Brier `0.212549`.

**V2 standalone p_model freeze was ABORTED** after audit found the goals isotonic mapping emitted exact `p_model=1.0` on three rows. The protocol already declared `probability_clip=1e-6`, but the implementation did not enforce that bound on emitted isotonic probabilities. V2 abort hash: `7bbab3206446421f3a6166c975fe224f14ac2fbf46744bf53acc5d7156b8438b`.

V3 output-bound repair:

- V3 preregistration commit: `6245413ca95377be61973c4f5a1356399eb917aa`.
- V3 repair protocol hash: `61aa74a54086ba99bd34110f377d157dc11fea5027e7df0d7b01acb1aa89202a`.
- No calibration search was reopened; methods, refit specs, weights, FIT/SELECT chronology and thresholds are identical to V2.
- Deterministic output contract: `p_model = clip(calibrator(raw_probability), 1e-6, 1-1e-6)`.
- Only **3 / 18,203** probabilities changed versus V2, all goals rows, each by at most ~`1e-6`.
- V3 calibration run hash: `6d5da381803d60000ae8cc52477e66f06644910f8271d155f6401784a330fc5c`.
- V3 standalone model-freeze hash: `bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2`.
- V3 certification hash: `1a0e34e1473b22088b9d9340393034a2e2f829ad93790afbbd5f66bb7c560503`.
- Final validation: **343 repository tests passed; 87 research modules imported; diff check and exact V3 regeneration PASS**.

Scientific interpretation:

- DEVELOPMENT selection passed.
- Calibration was required: IDENTITY did not win any of the three groups.
- The operational odds-blind calibrated `p_model` is now frozen.
- The 959 CALIBRATION fixtures were historically exposed under V1, so the repaired calibration metrics are **not fresh confirmatory OOS evidence**.
- The former 317-fixture cohort was exposed before its protected designation and remains **ineligible as a final holdout**.
- Genuine pass/fail for the complete calibrated model requires a **new future prospective cohort frozen after the Layer 5 successor policy is frozen**.
- Goals market comparison may proceed under the accepted settlement contract.
- Corners bookmaker comparison remains fail-closed until provider-to-bookmaker corner settlement equivalence is independently proven and frozen.
- Bookings market comparison remains blocked.

### Layer 5 — market-relative research

Status: **V1.2 ACTIVE / CERTIFIED FOR NEW FUTURE PROSPECTIVE COHORT / NO NEW OUTCOMES OPENED**

Current successor:
- Active protocol: qfe-layer5-market-surface-disagreement-v1.2.
- V1.2 protocol hash: ae39008016b66f27c279bd2d47093e679ff46458fb44226d2b373983d42bb46a.
- Frozen numeric-policy fingerprint: 0871ae9c1eb92d858b5f11551b339959e63870b52a1c936069236eb493ef5e51.
- Layer 4 V3 model binding: bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2.
- Layer 4 V3 certification binding: 1a0e34e1473b22088b9d9340393034a2e2f829ad93790afbbd5f66bb7c560503.
- V1.2 preregistration commit: 92e0f70b50650355495ab53c5f73f5121902e39f.
- V1.2 implementation commit: 324d5b2f2739bc72abdbc06051519e5507018a89.
- Numerical/selection policy exactly unchanged from V1.1: T-6h, bookmaker hierarchy/no fallback, proportional no-vig, Shin sensitivity-only, gap/support/CDF thresholds, and non-max-gap selection.
- Former 317-fixture cohort: **EXPOSED / DIAGNOSTIC ONLY / FINAL SCORING FORBIDDEN**.
- Historical V1.1 market manifest 6f43bd3cc224cc9e42515d6c187b1de7bfff822324aa5cbc4a4b0cbfcb74b54f regenerates byte-exactly but is implementation/coverage evidence only.
- Goals O/U 2.5 bookmaker comparison remains eligible.
- Match/team corners bookmaker comparison: **FAIL CLOSED** pending provider-to-bookmaker settlement equivalence.
- Future cohort manifest requires exact outcome-blind fixture schema and rejects any cohort frozen after a fixture's T-6h cutoff.
- V1.2 integrity audit: 5a18914704641eeaa5af7e0af8226464aee6a977d04809211515bf72991cdb0e; 40 focused tests, 354 full-repo tests, 88 imports, 19,000 adversarial cases / 0 violations.
- Prospective Execution V1 protocol: bf5b1ba2b15be8db74618754028a34c9568dc281e2fb26a9d0e174552681ca4c, frozen before new cohort selection.
- Prospective writer commit: 2388826ce293d5b6804eba9646291d4d93954da5.
- Prospective writer certification: f5e1fb54bbdd6f78be9d27c720a37cc61f46042189d3d9afaaabae6d27121648.
- Counterfactual fixture THESTATSAPI:mt_585222974 reproduced all 19 raw/calibrated probabilities exactly twice; bundle hash 00d09da33020f7038ebbfaf2149477b03332ff9163dc103f2415cb3939fa88ec.
- Writer certification validation: 28 focused tests, 362 full-repo tests, 89 imports, diff check PASS.

Historical V1/V1.1 record follows.

Frozen protocol:
- Protocol version: `qfe-layer5-market-surface-disagreement-v1`.
- Layer 5 V1 hash: `ecb72d508f421fbbcd45e4623acc50df882c178af83743365ed4be4e2dcebf65` — **ABORTED PRE-PROTECTED** because bookmaker selection among multiple same-bookmaker candidates was underspecified; no protected outcome/score had been opened.
- Historical Layer 5 V1.1 hash: `0e3928354f7da00e74c9bacd43b02cdace1556d0d8e11544f9ae0bb49fab2fe5` — preserved as pre-repair historical apparatus; no longer active.
- V1.1 bookmaker hierarchy: `pinnacle → bet365 → betmgm-uk → paddy-power`; structural availability only, with no price-driven fallback.
- Frozen Layer 4 model binding: `e33af913f4c27ce33355c78792419ad8cee73e3f16ce7c685781a010d386b3ea`.
- Layer 4 integrity-audit binding: `78f5925fc6cc1821e35724663da28a91a82390eab02c87cfdb03a0e07ed8b9e2`.
- Registered decision horizon: **T-6h**.
- No protected outcome or protected market-relative score was opened to design this policy.

Key frozen policy choices:
- Primary no-vig: **multiplicative/proportional**; Shin is sensitivity-only and cannot be selected because it enlarges disagreement.
- Same-bookmaker/timestamp-proven market bundles only; max age 30 minutes, max intra-surface skew 120 seconds.
- Corner surfaces require at least 3 adjacent quoted lines and bounded equal-weight monotone isotonic repair; max repair 3 pp / mean repair 1 pp.
- Goals remain total **2.5 only** in Layer 5 V1; no unsupported goal ladder is invented.
- Disagreement requires at least **5 pp** selected-line gap and at least **2 pp** after the empirical calibration-reliability penalty.
- Corner surfaces require at least 2 adjacent corroborating lines at ≥3 pp, with one ≥5 pp, and no opposite strong gap.
- **Maximum gap is never a selection criterion or tie-breaker.** The selected line is the central corroborated line whose cleaned market probability is closest to 0.50.
- Calibration support, dynamic support, OOD/component-dispersion and cross-line consistency can force abstention.
- The reliability-adjusted gap is an eligibility diagnostic, **not** an individual-fixture confidence bound.
- Primary market benchmark remains the unmodified preregistered no-vig probability; any market-only calibration is a diagnostic benchmark and cannot replace `p_market` for eligibility.

Layer 5 gates:
- [x] Freeze the Layer 5 market/disagreement protocol **before opening PROTECTED**.
- [x] Execute protocol regression tests on the compute host and bind the exact implementation audit `e317cd9eadbfb236e516b859be38bbf35582ad799d03e11d7509550ca6cf00c3`: 319 repo tests, 86 imports, 21 focused Layer 5 tests, and adversarial property gates all PASS.
- [x] Freeze horizon-matched timestamped same-bookmaker market manifest `6f43bd3cc224cc9e42515d6c187b1de7bfff822324aa5cbc4a4b0cbfcb74b54f` from the exact QFE prospective-capture prefix; 3 goals and 3 match-corner protected comparators qualify at T-6h.
- [x] Implement primary proportional no-vig and Shin sensitivity diagnostics exactly as preregistered.
- [x] Market Surface Engine implemented: same-bookmaker line ladders, bounded monotone CDF repair, raw quote preservation and fail-closed semantics.
- [x] Fail closed on incomplete, stale, cross-book or materially time-incoherent ladders; selected-book price/coherence failure cannot fall through to another book.
- [x] Preserve raw quotes/timestamps alongside bounded deterministic monotonic cleanup.
- [ ] QFE CDF vs market CDF diagnostics: broad signed gap, absolute gap, sign consistency and median-crossing displacement; no implied mean claim without proven tail coverage.
- [x] Cross-line robustness and deterministic non-max-gap line selection implemented and adversarially validated; maximum-gap selection is structurally excluded.
- [ ] Market-only calibrated comparator and separate market+QFE incremental-information arm.
- [x] Implement disagreement eligibility/abstention using calibration support, dynamic support, OOD/component dispersion, reliability penalty and adjacent-line robustness.
- [x] Freeze final V1.1 implementation integrity audit `3a93b1954e66515275d5965dbf833c502b5fc5849fcd1eda32c333934ebb856b` and matched-market manifest `6f43bd3cc224cc9e42515d6c187b1de7bfff822324aa5cbc4a4b0cbfcb74b54f`. Coverage remains intentionally sparse: 3 goals / 3 corner surfaces / 0 team corners.
- [x] Freeze bookmaker, line-selection and abstention implementation before any protected outcome is opened.
- [x] **V1.2 successor frozen:** bind to Layer 4 V3 while preserving the V1.1 numerical market policy exactly.
- [x] Historical V1.1 317-fixture market manifest regenerates byte-exactly but is diagnostic-only.
- [x] Corner bookmaker comparison fails closed on unverified settlement semantics.
- [x] Future prospective cohort/market-manifest machinery enforces exact outcome-blind membership and pre-T6 freezing.
- [x] V1.2 exact-implementation validation: 40 focused tests, 354 repository tests, 88 imports, 19,000 adversarial cases / 0 violations.
- [x] Freeze Prospective Execution V1 before live cohort selection.
- [x] Certify the outcome-blind/odds-blind V3 p_model writer by exact historical counterfactual replay.
- [x] Build/freeze live incremental history across all six frozen model competitions: 92 fixtures / 92 stats / 0 missing / snapshot hash 2fe64b6004e6bf2f3348a765ee4d08640bbedb39694206c52f5ce908a7cd56d0.
- [x] Verify zero base overlap and rebuild the combined 5,732-row PIT dataset.
- [x] Preregister fixed Oct 7–21 UTC cohort window with all scheduled fixtures included and no sample cap/model/market filter.
- [x] Freeze Cohort V1: 135 unique fixtures; cohort hash f3d5bb667f8849b33baf29fb9666400427a17c4cf02f47e9dc0e0a098af6f8f0; all members frozen before T-6h.
- [ ] **NEXT:** freeze/certify the T-6h execution runner; membership and numerical policies are now immutable.

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

## 6. Historical pre-repair gate — superseded operationally

This section records the sequence that produced the original Layer 4/Layer 5 state before the T-6h PIT repair. It is preserved as historical evidence and is not the current operational gate.

Layer 4 merge gate:

1. [x] Freeze protocol before CALIBRATION (`7a73e1ac2`).
2. [x] Audit protocol against partial pooling, coherence, support metadata and protected-data rules.
3. [x] Freeze DEVELOPMENT ensemble selection before CALIBRATION.
4. [x] Freeze raw CALIBRATION substrate and calibrator execution implementation before SELECT scoring (`2c020913d`).
5. [x] Run FIT/SELECT calibrator selection exactly once under V1; no post-result candidate/grid changes.
6. [x] Refit selected calibrators on all CALIBRATION after selection and freeze standalone `p_model`.
7. [x] Confirm protected rows scored = 0 and market inputs used = 0.
8. [x] Prove Layer 4 evidence regeneration/idempotence and code/source bindings. Full raw CALIBRATION → calibrator selection/refit → model-freeze rebuild reproduced hashes `94d29f3d...20c4`, `f3770a8b...92f2`, and `e33af913...6b3ea` exactly.
9. [x] Run complete repository tests/import sweep and verify Foundation/Layers 2–3.1 plus prospective evidence unchanged: 298 tests passed; 82 research modules imported; 0 failures; prior evidence unchanged; active legacy-product refs = 0.
10. [x] Commit, PR and merge Layer 4 if every gate remains green. Merged via PR #36 at `4858281f9e7dc3613fa7b0bb12b939521ce3b87c`.
11. [x] Preregister Layer 5 market-surface/disagreement policy hash `ecb72d50...bf65`; protected remains sealed. Historical next step was to execute protocol tests and freeze the Layer 5 implementation/matched-market manifest.

## 7. Current immediate gate

1. [x] Repair and merge the T-6h PIT horizon defect (PR #40).
2. [x] Independently certify the repaired scientific foundation for offline replay.
3. [x] Complete repository/worktree hygiene remediation on the compute host: standalone canonical clone at /srv/qfe/football-quant-engine; 5 dead registrations pruned; 38 historical linked worktrees classified/quarantined; 5 legacy project cron jobs paused.
4. [x] Separate provider-market availability, verified mapping and QFE market-comparison eligibility; corners remain modelable but comparison-fail-closed pending settlement-equivalence proof; bookings remain blocked.
5. [x] Clean canonical checkout validation: 71 focused foundation tests passed; 337 full repository tests passed; 86 research modules imported with 0 failures; git diff --check PASS.
6. [x] Freeze Foundation Certification V2 in evidence/foundation_v2/QFE_REPAIRED_FOUNDATION_CERTIFICATION_V2.{json,md}. PROTECTED remains sealed; old Protected Protocol V1 is explicitly superseded for repaired T-6h update semantics while its 317-fixture membership remains frozen.
7. [x] Audit merged PR #41 Layer 2 replay: **ABORT** because the claimed DEVELOPMENT-only report scored all 5,640 fixtures, including 959 CALIBRATION and 317 later-designated PROTECTED fixtures.
8. [x] Freeze and run Layer 2 V3 under true DEVELOPMENT-only scoring: 552 WARMUP state-only, 3,812 DEVELOPMENT scored, 959 CALIBRATION + 317 exposed former-PROTECTED excluded from model input; exact rebuild PASS.
9. [x] Independently audit merged PR #42 Layer 3: exact regeneration of chronology, tournament, 3,812 goals OOF rows, 3,783 corners OOF rows, structured fold OOF and component evaluation; 0 CALIBRATION / 0 exposed former-PROTECTED rows scored.
10. [x] Independently audit merged PR #43 Layer 3.1: protocol preregistration confirmed; 94,752 event cells regenerated exactly; SIDE NB2 passes the preregistered DEVELOPMENT gate, TOTAL NB2 remains weak/inconclusive; no CALIBRATION, exposed former-PROTECTED or market inputs.
11. [x] Audit/rebuild Layer 4 from the certified corrected chain; V3 bounded calibrated p_model frozen.
12. [x] Rebind/certify Layer 5 V1.2 without changing the frozen numerical market policy; former 317 cohort retired as final holdout and corners comparison fail-closed.
13. [x] Freeze Prospective Execution V1 and certify the p_model writer by exact historical counterfactual replay.
14. [x] Build/freeze live incremental history across all six frozen model competitions; 92 normalized matches, 0 missing stats, combined PIT PASS.
15. [x] Preregister and freeze Prospective Cohort V1: 135 scheduled fixtures, no cap/subsampling/model/market filter, all frozen before T-6h.
16. [x] Freeze/certify/deploy the T-6h execution runner without altering cohort membership or model/market thresholds.
17. [x] Preregister/certify the passive odds price-movement scanner and operational-close rule; no live price path observed before freeze.
18. [ ] Deploy the scanner alongside the T-6h runner from canonical main, verify zero-eligible operation, then make no further model/policy changes during the cohort.
