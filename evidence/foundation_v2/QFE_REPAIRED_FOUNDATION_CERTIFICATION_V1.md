# QFE V2 — Repaired Foundation Certification & Repository Hygiene Audit V1

Audit date: 2026-10-04 (America/Bogota)

Status: **CONDITIONAL PASS FOR OFFLINE MODEL REPLAY / HYGIENE HOLD FOR FURTHER ADVANCEMENT**

## 1. Certified scientific foundation

Certified repair merge:

- PR #40 merge SHA: `651b98fb82e3cf3cc0a47da13f95cebe5fb1862a`
- Core PIT repair: `64234a45c`
- Call-path closure: `5bc9aedcb`

The repaired contract is:

`source kickoff + 6h availability embargo <= target kickoff - 6h decision horizon`

Exact equality is admissible and regression-tested.

The audit confirms that the repaired Foundation PIT dataset and the dynamic hierarchical walker use the same horizon semantics. Same-kickoff forecasts remain isolated.

## 2. Validation evidence

At the exact PR #40 merge SHA:

- full repository suite: **334 passed / 0 failed**;
- independent rerun runtime: **17.68 s**;
- committed PIT call-path audit: **25 focused integrity tests passed**;
- `git diff --check`: PASS;
- active scientific callers of `DynamicHierarchicalCountBaseline` use the repaired walk-forward path;
- no active scientific caller uses the immediate `process_batch()` primitive.

Foundation regression coverage includes:

- provider contract provenance;
- missing != zero;
- target settlement semantics;
- extra-time exclusion;
- current-fixture self-leakage rejection;
- result availability/embargo;
- exact cutoff equality;
- deterministic input ordering;
- immutable/content-addressed PIT artifacts;
- chronology partition boundaries;
- DEVELOPMENT-only selection;
- CALIBRATION-only fitting;
- dynamic same-kickoff isolation;
- reordered-input determinism.

## 3. Governance

`QUANT_FOOTBALL_SOURCE_OF_TRUTH.md` at the certified foundation explicitly states that the 2026-10-01 deterministic architecture governs future QFE work and supersedes the 2026-09-27 / 2026-09-29 direction without rewriting historical evidence.

The implementation ledger correctly records the PIT defect as a scientific abort/version event and marks the old dynamic-derived Layers 2–4 as:

**SUPERSEDED / NOT ELIGIBLE FOR PROTECTED SCORING**

Historical artifacts remain immutable.

## 4. Provider / target / PIT foundation

### PASS

- TheStatsAPI fields are provider-scoped under an explicit capability registry.
- Registry provenance is pinned to a provider document hash.
- Semantically unaudited npxG fields are not eligible for the default history path.
- PIT construction rejects provider mismatches.
- Missing values are preserved as missing rather than coerced to zero.
- Historical post-match stats are labelled reconstructed and use an explicit embargo.
- Extra-time / shootout fixtures are rejected from regulation targets/history where required.
- Stable fixture identity is mandatory.
- Goals and corners are modelable targets.
- Bookings targets remain model-ineligible pending settlement reconciliation.
- Model feature construction is odds-blind.

### MATERIAL CONTRACT DEFECT F1 — CORNERS MARKET COMPATIBILITY

The frozen Foundation capability audit states:

> Corners are modelable, but commercial bookmaker comparison remains blocked until provider `corner_kicks` is proven equivalent to bookmaker corners-taken settlement.

However `TARGET_REGISTRY_V1` marks home, away and total corner market mappings as `ProviderMarketStatus.VERIFIED`, and the tests explicitly assert those mappings as verified.

No change to the target contract or Foundation audit occurred between PR #40 and current `main`.

**Classification:** does not invalidate offline corner model fitting; **does block certification of corner market-relative/protected scoring** until resolved.

Required action:

- either produce and freeze a genuine settlement-semantic equivalence proof;
- or change corner market comparison status to fail closed / UNVERIFIED.

No retrospective result may be used to choose between those actions.

### CONTRACT API DEFECT F2 — MARKET AVAILABILITY VS TARGET COMPATIBILITY

`bookings_total_regulation` is correctly `model_eligible=False`, yet its market status is `VERIFIED` and `provider_market_mapped=True`.

The existing test deliberately encodes this state because the provider exposes a `total_cards` market while the QFE realized bookings target is unresolved.

The API therefore conflates:

1. provider market key exists;
2. QFE target is settlement-compatible and eligible for comparison.

Required action: expose separate concepts, for example:

- `provider_market_available`;
- `market_comparison_eligible`.

The second must require target/model settlement semantics to be accepted.

## 5. Protected firewall

As checked immediately before this audit:

- protected branch: `344767a904036c2f42e91044221e7ad93f5c367a`;
- no protected result artifact;
- no protected score artifact;
- no protected settlement artifact;
- no protected outcome artifact;
- protected outcomes opened/scored: **0**.

The worktree contains the previously known untracked `src/research/protected/predictions.py`. It predates the repaired T-6h semantics and must not be executed.

**Protected remains sealed.**

## 6. Repository hygiene audit

### H1 — HOME DIRECTORY IS A GIT WORKTREE — HIGH RISK

The primary registered worktree is `/home/ubuntu`, currently on legacy branch `feat/item6-novel-hypothesis-discovery`.

Its untracked namespace includes host/user material such as:

- `.aws/`
- `.ssh/`
- `.git-credentials`
- `.env.cron`
- other home-directory application/configuration state

No evidence was found that these files are committed, but keeping the repository root at the user home directory makes a careless broad add operation an avoidable credential/secrets risk.

**Required hygiene:** all future QFE work must use a dedicated repository directory. The home-directory worktree should be migrated/quarantined deliberately; do not delete its Git metadata while linked worktrees depend on it.

### H2 — WORKTREE SPRAWL

Registered worktrees observed: **41**.

Of those:

- **5** were already marked prunable because their filesystem locations no longer exist;
- at least **9** active worktrees were dirty/untracked;
- several are obsolete legacy research branches unrelated to the current QFE V2 critical path.

This makes branch provenance, accidental edits and broad filesystem searches unreliable.

### H3 — STALE LOCAL MAIN

The local `main` branch observed on the compute host was **64 commits behind `origin/main`**.

All future work must bind to explicit `origin/main` SHAs, not an assumed local `main`.

### H4 — OBSOLETE PIT REPAIR WORKTREE

`.qfe_horizon_fix` remains dirty with old uncommitted replay/version artifacts on the superseded repair branch.

It must be preserved only as historical scratch evidence or archived; it is **not merge-eligible**.

### H5 — LAYER 4 REPLAY OUTPUTS EXIST BEFORE UPSTREAM CERTIFICATION

`.qfe_layer4_pit_v2` contains untracked Layer-4 PIT replay outputs. Its protocol commit exists, but those outputs must remain quarantined until the repaired Layer 2 → Layer 3 → Layer 3.1 chain is independently certified.

Do not promote or merge those outputs merely because they exist.

### H6 — PROTECTED PREDICTION DRAFT IS OBSOLETE

The untracked protected `predictions.py` encodes pre-repair availability semantics. It must be disabled/quarantined and replaced only after the repaired Layer-4 model freeze is certified.

### H7 — MAIN ADVANCED AHEAD OF THE AUDIT GATE

Current `origin/main` at audit start:

`c5f7b66b3c04826dff9fdc06dc510bddb31d21c0`

It already contains:

- PR #41 — repaired Layer 2 replay;
- PR #42 — repaired Layer 3 replay;
- PR #43 — repaired Layer 3.1 replay.

These commits are **not invalidated by this fact**, but they were merged before this explicit repaired-foundation certification completed.

Therefore their status is:

**MERGED BUT NOT YET INDEPENDENTLY CERTIFIED**

No further scientific promotion should rely on them until audited in order.

### H8 — IMPLEMENTATION LEDGER STATUS DRIFT

Current `main` contains the repaired Layers 2–3.1, but the central implementation ledger still says:

- `ACTIVE REPAIR / PROTECTED STILL UNOPENED`;
- old `Layer 4 merge gate` as the “Current immediate gate”;
- old Layer-5 next-step language pointing toward protected scoring.

The ledger is therefore no longer a reliable operational status page.

Required action: update it with a single current-state section that distinguishes:

- certified foundation;
- merged-but-uncertified repaired replays;
- paused Layer 4 replay;
- sealed protected cohort;
- explicit next gate.

Historical ledger text should remain intact.

## 7. Operational tooling finding

A broad repository-wide streamed search caused Remote Desktop Commander to become unresponsive while the device still reported online.

Future heavy commands must:

- scope paths;
- redirect large output to files;
- inspect summaries/tails;
- avoid large recursive streams across dozens of worktrees;
- run heavy research serially.

This is operational hygiene, not a scientific model failure.

## 8. Certification verdict

### Scientific foundation

**PASS — OFFLINE MODEL-REPLAY ELIGIBLE**

The repaired PIT/data/model foundation at PR #40 is coherent for goals/corners offline model research and replay.

### Market-comparison foundation

**FAIL / HOLD**

Corner settlement compatibility is overclaimed in the target registry relative to the frozen Foundation audit. Bookings market availability and target compatibility are also conflated at the API level.

No corner protected market-relative claim should be certified until this is resolved.

### Repository / organizational hygiene

**FAIL / REMEDIATION REQUIRED**

The worktree topology, home-directory repository root, stale local main, obsolete dirty worktrees and stale implementation ledger should be cleaned before further model promotion or protected work.

## 9. Required next gate

Do **not** open PROTECTED and do **not** advance Layer 4.

Next work should be a bounded hygiene/contract remediation:

1. create a dedicated canonical QFE repository/work directory;
2. quarantine the home-directory worktree without destroying linked history;
3. prune only provably dead worktree metadata;
4. inventory and classify remaining worktrees as ACTIVE / HISTORICAL-READONLY / DELETE-AFTER-BACKUP;
5. update the implementation ledger current-state section;
6. repair the corner/bookings market-compatibility contract API;
7. rerun foundation-focused tests + full suite;
8. freeze a Foundation Certification V2 hash;
9. only then audit PR #41 Layer 2.

No model hyperparameters, thresholds, protected fixtures or frozen market policy may be changed as part of this hygiene work.
