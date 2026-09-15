# V7 — Control-B Pre-OOS Comparability Closure

**Executive verdict: `V7_CONTROL_B_REPAIRED_AND_REFROZEN`** → state `V7_CONTROL_B_READY_FOR_OOS`.

```
CONFIRMATORY_OOS_COMPUTED   = false
CONFIRMATORY_OOS_VIEWED     = false
CANDIDATE_FEATURE_PROMOTION = false
BEDROCK_CHANGE_REQUIRED     = false
```

No Bedrock/IAM/inference-profile/runtime/SDK change was needed or made — this stage is entirely
local deterministic statistics. **No `KIRO_HANDOFF_REQUIRED` section applies.** CHAMPION
unchanged: `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9`.

---

## 1. Control A infeasibility (confirmed)

Base-vs-Research matched downstream comparison is unavailable, and the cause is structural, not
statistical: across the 10 V6.1 fixtures **not one canonical specification was produced by both
arms** (`n_families_both_arms = 0`). Restricted to measurable families that leaves 5 matched
cells over 3 fixtures, against frozen minima of 12 cells / 5 fixtures / 12 families per arm.

The arm contrast stays **descriptive only** and is blocked in code from becoming the
confirmatory primary (`test_21_16`). V6.1 already answered the generator-quality treatment
question; V7 asks whether the frozen universe contains quantitative signal.

## 2. Control B: three generation defects found and repaired

Broad tolerance gates (measurability gap 0.189, comparator gap 0.047) had **masked** a fatal
problem. Inspecting the slot-level structure showed the v1 null could not inhabit two of the
nine canonical slots at all:

| slot | LLM | null v1 | verdict |
|---|---|---|---|
| `SIMILARITY_DIMENSIONS` non-empty | 33/132 (25%) | **0/400** | empty cell — unweightable |
| `PROVIDER_REQUIREMENTS` non-empty | 123/132 | **0/400** | never inhabited |
| `CONDITIONS` token type | structured dicts | plain strings | can never collide |

A quarter of the LLM universe — including the `OPPONENT_PROFILE_INTERACTION` family the brief
calls central — had **no possible comparator**. That is a generation defect under Task 10, so
the pool was regenerated (`v7_null_v2`), not merely reweighted. The repair is anchored on the
one capability relationship that is deterministic in V6.1: `opponent_profile` capability ⟺
opponent_profile condition, **33/33, zero discordant**. The null now emits the same structured
`{dimension, axis, value}` tokens and reaches the similarity slot.

### Two frozen pools, because one cannot serve both endpoints

| pool | sampling | families | serves |
|---|---|---|---|
| `NULL_UNIFORM` | uniform over the grammar | 1,980 | endpoint A + data compatibility |
| `NULL_MATCHED` | V6.1 **structural marginals** | 15,738 | endpoint B |

Endpoint A must *not* condition away the LLM's metric preferences — that difference is the
finding. Endpoint B must control for structure. `NULL_MATCHED` samples **independently** from
the LLM's marginals, so it reproduces the composition without reproducing the joint choices —
and the joint choice is exactly the LLM contribution under test. Marginals are read from
canonical structure only; no outcome is touched (`test_21_15`).

## 3. Universes

| | LLM | null (uniform) | null (matched) |
|---|---|---|---|
| canonical families | 132 | 1,980 | 15,738 |
| measurable | 53 (40.2%) | 1,167 (58.9%) | 6,056 |
| eligible for endpoint B | 53 | — | 6,056 |

## 4. Endpoints (both frozen, never collapsed)

**A. `END_TO_END_RESEARCH_YIELD`** — denominator is **all** canonical families, unmeasurable
included. Ladder `canonical → measurable → adequate_support → oos_survives`, attrition reasons
preserved. Deliberately **not** matched: matching on measurability would condition away the
failure this endpoint measures. Frozen ladder carries `oos_survives: null`,
`oos_stage_computed: false`.

**B. `CONDITIONAL_SIGNAL_QUALITY`** — the same eligibility (`MEASURABLE` + `ADEQUATE_SUPPORT`)
applied symmetrically to both origins, then the frozen matched design. Primary statistic chosen
now, before any OOS: the **continuous** `OOS_QUALITY_SCORE_DIFFERENCE` (mean over folds of the
sign-consistent shrinkage-adjusted standardized effect × fold direction-agreement rate), chosen
over a binary survival indicator so no information is discarded at an arbitrary threshold. A
sign-reversing family is pulled toward 0 by construction, not by a post-hoc rule.

**`DATA_COMPATIBILITY_RATE` (descriptive, explicitly not football evidence):**

| origin | rate | names a coverage-failing metric | drivers |
|---|---|---|---|
| LLM | **0.4015** | **59.9%** | xg 58, touches_in_penalty_area 44 |
| null (uniform) | 0.5894 | 41.1% | xg 225, offsides 253, np_xg 241, touches 237 |

The LLM generates more contextually interesting but **less corpus-compatible** questions. Kept
separate from every OOS number and asserted non-hideable in code (`test_21_17b`).

## 5. Structural covariates (Task 3)

28 covariates built from structure + the effect-blind coverage contract. 12 are used for
matching: `uses_similarity, comparator, target_band, time_scope, metric_group,
measurability_status, subject, side, n_conditions, support_risk_class, coverage_class,
requires_half_resolution`.

**Two fields are recorded but excluded from matching**, both because they are *generator
self-description* rather than properties of the statistical question:

- **raw `PROVIDER_REQUIREMENTS`.** Measured: `xg` capability vs an xg target = 53 agree / 5 / 5;
  `target_fixture_venue_context` vs a venue comparator = **0 agree / 30 / 17**;
  `match_level_observations` present in only 65/132. Only `opponent_profile` is deterministic,
  and that is carried explicitly as `uses_similarity`.
- **`research_family` label.** Identical structure carries `FORM_VS_BASELINE` 22× but six other
  families 16×. Replaced for matching by `metric_group`, computed identically from `TARGET` on
  both sides. The label still drives the confounder and multiplicity plans.

`canonical.py` was **not** modified, so canonical ids, dedup families and the candidate lock are
untouched.

## 6. Matching and weighting (Tasks 4, 5)

Hierarchy `TIER_1_EXACT → TIER_2_CEM → TIER_3_COARSE → NO_COMPARABLE_CONTROL`. Every tier shares
a `CORE_KEY` pinning `uses_similarity, comparator, n_conditions, measurability_status,
requires_half_resolution, support_risk_class, coverage_class` — `support_risk_class` is a
deterministic function of the first three, so pinning them balances it automatically instead of
letting it drift in the coarse tier.

**Inferential unit:** one LLM family ↔ its weighted control set, **total control weight exactly
1**. Verified: `total_control_weight = 48.0` = number of matched families, against a raw pool of
6,056. The pool buys matching flexibility and can never become nominal N (`test_21_03`).

| | value | threshold |
|---|---|---|
| matched | 48 / 53 | — |
| `NO_COMPARABLE_CONTROL` | 5 (**0.094**) | ≤ 0.25 ✓ |
| tiers | EXACT 28, CEM 13, COARSE 7 | — |

The 5 unmatched are all non-similarity families, 4 of them `SUBJECT_VENUE_BASELINE`. They are
labelled and excluded, never force-matched — and their composition is recorded in the balance
artifact so the restriction of the estimand to the matched region of common support is visible.

## 7. Balance (Task 6)

Assessed on matched LLM families vs their weighted control sets, per covariate **level**,
categorical SMD with binomial pooled SD.

**Worst |SMD| = 0.1859; 0 of 31 levels out of balance** (threshold 0.25). Raw-vs-weighted
columns are reported for every level in `V7_CONTROL_B_BALANCE_REPORT.json`.

> **Threshold discipline.** All thresholds (`MAX_STANDARDIZED_DIFF = 0.25`,
> `MAX_NO_COMPARABLE_FRACTION = 0.25`, `MAX_CONTROL_WEIGHT_SHARE = 0.25`,
> `MIN_EFFECTIVE_N = 20`) were frozen **before** any cross-tabulation was computed. The tier
> keys and pool size were then selected as the smallest configuration meeting them, using
> structural balance diagnostics **only**. No outcome, effect, fold or OOS quantity entered
> that selection — which is precisely the latitude Task 4 grants.

## 8. Effective sample size (Task 7)

| quantity | value |
|---|---|
| raw null N | 6,056 |
| controls carrying weight | 452 |
| total control weight | 48.0 |
| **Kish ESS** | **153.91** (≥ 20 ✓) |
| max single-control share | **0.0208** (≤ 0.25 ✓) |
| unmatched fraction | 0.094 |

No handful of generic controls carries the comparison. Control weights and ESS are stored
**unrounded** — they feed the balance and ESS math, and the `total = n_matched` invariant must
hold exactly (a rounding bug that broke it by 1e-8, plus an ESS precision loss, were caught by
`test_21_01` and `test_21_12` and fixed).

## 9. Comparability decision

**Control B is a valid comparator.** All four frozen gates pass: unmatched fraction 0.094 ≤ 0.25;
worst |SMD| 0.186 ≤ 0.25 with zero levels failing; ESS 153.9 ≥ 20; max control share 0.021 ≤ 0.25.
Every input is outcome-blind and every threshold predates the diagnostics.

## 10. Regression locks

**Provider provenance (Task 15).** `cross_provider_invariant` proves single-provider with
evidence; every contracted metric resolves to `thestatsapi` regardless of storage block; a
target set spanning base+rich+extra pools freely; and a **synthetic genuine** two-provider set is
driven through `classify_measurability` to an actual `UNMEASURABLE_PROVIDER` rejection
(`test_21_20`). A separate test asserts the contract's provenance claim still matches what
`championship_adapter` / `multisrc_corpus` really do.

**Coverage (Task 16).** `shots`, `possession`, `saves` all pass the gate with zero excluded
competitions and resolve MEASURABLE; `shots` must read the provider's own `total_shots`, never a
sum of the box split. **Ligue 2 xG is asserted to be exactly 0.000**, the gate fails, the verdict
propagates to `UNMEASURABLE_COVERAGE`, and no similarity dimension may use xG.

**Shrinkage (Task 17).** `shrinkage_integrity()` is a *functional* check: it verifies the
published k equals the code constant, that `shrink_profile` actually moves the value, and that
the movement matches the closed form at the code's own k. Mutating the **spec** while the code is
unchanged fails it, and the freeze driver treats that as a blocking problem — no published
parameter may exist only as prose.

## 11. Tests and blast radius (Task 14)

- `test_v7_control_b.py` — **36 passed**, 0 skipped, 0 xfail (all 23 Task-21 cases + Task-11
  fairness nulls + Task 15/16/17 locks + the blast-radius locks).
- `tests/research/hypothesis_oos/` — **439 passed**, 0 skipped, 0 xfail.

**Task 14 is discharged by route B, with route A attempted.** The full `tests/research/` suite
was launched in background and had still not finished when this work completed, so it is
reported as **not run** — never as passing. In its place, `_v7_blast_radius.py` produces a
machine-generated transitive-import proof (`V7_BLAST_RADIUS.json`):

| | |
|---|---|
| test modules scanned | **219** |
| modules that can transitively reach changed V7 code | **2** |
| modules that cannot | **217** |

The two reaching modules are exactly `test_v7_pre_oos.py` and `test_v7_control_b.py`, both run
to completion and green. The analysis walks the full AST (so function-level imports are caught,
not just top-level ones), and two tests keep it honest: one regenerates the proof and asserts it
still matches while requiring every file in `hypothesis_v7/` to be declared, and a **negative
control** asserts the analyser genuinely finds a dependency rather than vacuously passing.

Task-11 fairness null is the load-bearing one: with downstream quality made **identical** and
only composition differing, the matched estimator returns a difference of 0 to within 1e-9 — the
design cannot manufacture an advantage from structure. Bad overlap returns
`NO_COMPARABLE_CONTROL` or a blocked verdict, never forced significance.

Three of my own defects were caught by these tests and fixed rather than papered over: the
weight-rounding invariant break, an ESS precision loss, and a token scan that flagged the guard
list naming the tokens it exists to forbid.

## 12. Reproducibility

All **28** artifacts byte-identical under `PYTHONHASHSEED = 1, 2, 3, 12345` **and** under a
second interpreter (`.venv/bin/python`). The null RNG is a SHA-256 counter stream with a frozen
seed — never `random`, never Python `hash()`.

## 13. Frozen artifacts

`V7_CONTROL_B_COVARIATE_SPEC` · `V7_CONTROL_B_MATCHING_SPEC` · `V7_CONTROL_B_BALANCE_REPORT` ·
`V7_CONTROL_B_WEIGHTS` · `V7_CONTROL_B_EFFECTIVE_SAMPLE` · `V7_ENDPOINT_SPEC` ·
`V7_DATA_COMPATIBILITY_ENDPOINT` · `V7_CONDITIONAL_SIGNAL_ENDPOINT` · `V7_CONTROL_B_FREEZE` ·
(+ the 19 prior artifacts) — **28 artifacts, all inside the freeze driver's hash map and
therefore inside the four-seed byte-identity check**. Schema/matching/endpoint hashes in
`V7_CONTROL_B_FREEZE.json` are recomputable from code and asserted to match
(`test_control_b_artifacts_frozen_and_hashed`).

`V7_BLAST_RADIUS.json` is written by a separate static-analysis script and is a **diagnostic
artifact outside the hashed freeze set** — it is regenerated and asserted current by test rather
than hash-frozen.

## 14. Final states

```
V7_V6_1_HISTORY_FROZEN                      V7_CONTROL_A_INFEASIBLE
V7_HYPOTHESIS_UNIVERSE_FROZEN               V7_CONTROL_B_STRUCTURAL_COVARIATES_FROZEN
V7_CANONICALIZATION_VALIDATED               V7_CONTROL_B_MATCHING_FROZEN
V7_DEDUPLICATION_VALIDATED                  V7_CONTROL_B_BALANCE_VALIDATED
V7_MEASURABILITY_RULES_FROZEN               V7_CONTROL_B_EFFECTIVE_SAMPLE_VALIDATED
V7_PROVIDER_SEMANTICS_VALIDATED             V7_END_TO_END_ENDPOINT_FROZEN
V7_PIT_ENGINE_VALIDATED                     V7_CONDITIONAL_SIGNAL_ENDPOINT_FROZEN
V7_SIMILARITY_ENGINE_VALIDATED              V7_EVALUATOR_FROZEN
V7_SUPPORT_RULES_FROZEN                     V7_CHAMPION_ISOLATED
V7_CONFOUNDER_PLAN_FROZEN                   V7_FULLY_PREREGISTERED
V7_MULTIPLICITY_PLAN_FROZEN                 V7_OOS_EXECUTION_AUTHORIZATION_REQUIRED
V7_WALKFORWARD_DESIGN_FROZEN
```

**STOP.** No confirmatory OOS computed or viewed.
