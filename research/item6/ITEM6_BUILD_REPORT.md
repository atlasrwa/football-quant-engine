# ITEM 6 — FALSIFIABLE DISCOVERY EXPERIMENT BUILD REPORT

Zero-spend build of `ITEM6_NOVEL_HYPOTHESIS_DISCOVERY_AND_INCREMENTAL_VALUE`. No paid model call
was made. CHAMPION untouched. Stage-1 live execution awaits explicit human spend authorization.

---

## Build head / branch

```
START_HEAD      = bb85637c27233dc5981b968430cbff3260cd3817
END_HEAD        = <set by commit step>
PUSHED_HEAD     = <not pushed; awaiting authorization>
BRANCH          = feat/item6-novel-hypothesis-discovery
COMMITS_ADDED   = 1 (item6 build)
```

## Frozen questions

```
ITEM6_RESEARCH_QUESTION =
  Can an LLM, given point-in-time-safe football evidence and an explicit description of what the
  deterministic engine already covers, discover novel, grounded, falsifiable hypothesis families
  that expand the measurable search space and subsequently produce incremental OOS predictive
  information?

STAGE1_SCIENTIFIC_QUESTION =
  Does the redesigned generation instrument produce grounded, falsifiable, provider-safe football
  hypothesis families that are not baseline-equivalent, repeatably across a fresh cohort, and that
  survive deterministic formalization?

STAGE2_SCIENTIFIC_QUESTION =
  Do hypotheses instantiated from LLM-discovered novel families provide OOS predictive information
  beyond hypotheses available from the deterministic baseline family universe?

TWO_STAGE_DESIGN               = true
STAGE1_REQUIRED_BEFORE_STAGE2  = true
```

## Artifact paths + SHA256

```
ITEM6_PROTOCOL_PATH   = research/item6/ITEM6_RESEARCH_PROTOCOL_V1.md
ITEM6_PROTOCOL_SHA256 = 4ba1c40f9fc047e0247944c0c5cb29355c90b196952bc8dcbdf0392301cb4839

BASELINE_COVERAGE_SPEC_PATH   = research/item6/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.md
BASELINE_COVERAGE_SPEC_SHA256 = 05fd187979f2dba866b8ed55974ce7ea0e532cb68d0649fdbc0ccb480a438542
BASELINE_COVERED_FAMILIES     = BC_SAME_METRIC_MIRROR, BC_UNIVARIATE_PROFILE_SPLIT,
  BC_SIMPLE_VENUE_CONTRAST, BC_RECENT_VS_LONGRUN, BC_TEAM_METRIC_X_OPP_CONCESSION,
  BC_ENVIRONMENT_BASELINE, BC_SINGLE_DIM_PROFILE_ALREADY_EXPRESSIBLE, BC_SIMILAR_OPPONENT_COHORT,
  BC_COVERED_TWO_DIM_INTERACTION, BC_SALIENCE_RANKING  (10 covered structural families)

BASELINE_EQUIVALENCE_DETECTOR_PATH   = src/research/item6/baseline_equivalence.py
BASELINE_EQUIVALENCE_DETECTOR_SHA256 = e85527015d351a90c29a60294e4e839b400d8c6c002f7307d40587ed83817993

MECHANISM_PROMPT_PATH   = research/item6/ITEM6_MECHANISM_PROMPT_V1.md
MECHANISM_PROMPT_SHA256 = 36b98540db4beb4ee8f7c70f919a179019f450ec3ebce96d9a28b50f95e171f0
NO_WORKED_FOOTBALL_EXAMPLE = true  (enforced by tests/research/item6/test_anti_imitation.py)

MECHANISM_SCHEMA_PATH   = research/item6/ITEM6_MECHANISM_SCHEMA_V1.md
MECHANISM_SCHEMA_SHA256 = 13b0296d14bf4d63cc23ff0b10b67eb90a7fc8ed7fdd5aa097370e21ec0e34da

K_MECHANISMS_PER_FIXTURE = 5
ABSTENTION_ALLOWED       = true  (token NO_NOVEL_GROUNDED_MECHANISM)

OLD_GRAMMAR_FORCED_DURING_DISCOVERY = false

MECHANISM_FORMALIZER_PATH   = src/research/item6/formalizer.py
MECHANISM_FORMALIZER_SHA256 = 212a14a90ba31f950b69238aba8340c9859150f2f46affacc5f6d14252d71936

NOVEL_FAMILY_REGISTRY_SCHEMA_PATH   = research/item6/NOVEL_FAMILY_REGISTRY_SCHEMA_V1.md
NOVEL_FAMILY_REGISTRY_SCHEMA_SHA256 = 95bf6671e06dd610f0154c34c65347e1e76cb4052528ea485f6d709c920d1c93

STAGE1_QUALITY_PROTOCOL_PATH   = research/item6/STAGE1_QUALITY_PROTOCOL_V1.md
STAGE1_QUALITY_PROTOCOL_SHA256 = 24c1d810b3e3471071ee69d678fab766b1038085ee9020dbac7894e17686bfcb

STAGE1_GATE_PATH   = research/item6/STAGE1_GATE_V1.md
STAGE1_GATE_SHA256 = ef0b0d9566c707200ad4af699314165d555c54fa38119f74f40e3b157aa653a4

STAGE1_POWER_COST_PATH   = research/item6/STAGE1_POWER_AND_COST_V1.md
STAGE1_POWER_COST_SHA256 = a2d31d1d1c71e71ad3a4ba482962453e7a93ea3358b1b11247f3524462b8d80b

STAGE1_COHORT_MANIFEST_PATH   = research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json
STAGE1_COHORT_MANIFEST_SHA256 = f92cd6a23c1bc3a8e7f8fe5eabff9d1bf643802f42c6261ba069f128bfeaf54b

STAGE2_FRAMEWORK_PATH   = research/item6/STAGE2_FRAMEWORK_V1.md
STAGE2_FRAMEWORK_SHA256 = 2e5dea746f55af5c03ff190db80b84e93481bde5a281ad25544d884e7b5445c8

FREEZE_MANIFEST_PATH   = research/item6/ITEM6_FREEZE_MANIFEST.json
FREEZE_MANIFEST_SHA256 = b32e42c5f8adc90ceccedde2fd923f1dfeefb21cd4b2ddab3d3a9b34da79c523
FREEZE_SELF_HASH       = 9e4ae678ea8a118f62c762ee0dec9262d85d092bfe264a659970c4771cba55c0
```

## Stage-1 endpoints (frozen) + gate thresholds

```
STAGE1_PRIMARY_ENDPOINTS = BASELINE_EQUIVALENT_RATE, SEMANTIC_DUPLICATE_RATE,
  NOVEL_MEASURABLE_FAMILY_RATE, NEW_FAMILY_COUNT, MULTIVARIABLE_INTERACTION_RATE,
  FORMALIZATION_SURVIVAL_RATE  (primary; all must pass)
  + GROUNDING_PASS_RATE, FALSIFIABILITY_PASS_RATE, ABSTENTION_RATE (diagnostic)

BASELINE_EQUIVALENT_RATE_MAX        = 0.60
SEMANTIC_DUPLICATE_RATE_MAX         = 0.50
NOVEL_MEASURABLE_FAMILY_RATE_MIN    = 0.30
MULTIVARIABLE_INTERACTION_RATE_MIN  = 0.20
NEW_FAMILY_COUNT_MIN                = 3
GROUNDING_PASS_RATE_MIN             = 0.90   (diagnostic)
FALSIFIABILITY_PASS_RATE_MIN        = 0.80   (diagnostic)
FORMALIZATION_SURVIVAL_RATE_MIN     = 0.50

GATE_THRESHOLD_JUSTIFICATIONS = see STAGE1_GATE_V1.md. Prior corpus reference: dup ~0.80,
  baseline/mirror ~0.51, novel families 0, interaction ~0.009. Thresholds demand a regime
  change (not prior+epsilon); primary = the six above; diagnostics do not gate (avoids the V3
  fail-closed-on-N cascade).
```

## Power / cost (pre-spend)

```
STAGE1_SELECTED_N_FIXTURES = 120
EXPECTED_GENERATED_MECHANISMS = ~600 (K=5; fewer with abstentions)
EXPECTED_STAGE1_SPEND_USD  = ~5.58
P90_STAGE1_SPEND_USD       = ~7.99
MAX_STAGE1_SPEND_USD       = ~15.64 (incl. retry buffer)
Precision: fixture-level 95% CI half-width ~±0.08 at N=120; mechanism-level design-effect-adjusted
  effective N 176-333 (rho 0.2-0.6), half-width ~±0.05-0.07. Within-fixture dependence handled.
```

## Fresh Stage-1 cohort

```
V1_FIXTURE_OVERLAP = 0
V2_FIXTURE_OVERLAP = 0
V3_FIXTURE_OVERLAP = 0
n_selected = 120, prospective pool (kickoff > prior cohort max) = 1488, no rehearsal fallback used.
Selection = availability-only, competition-proportional, SHA256-ordered, chronological. Not chosen
for novelty-conduciveness. Reads no outcome/effect/LLM output.
NOTE: the prospective pool is drawn from post-prior-era season files; several competition_id values
are outside the six legacy labels and appear as comp_<id> strata. This does not affect overlap=0
or prospectivity; it is a labelling artifact of newer seasons and is reported transparently.

STAGE1_OOS_DATA_VISIBLE = false
```

## Semantic rating plan

```
SEMANTIC_RATING_PLAN = PASS A deterministic structural classifier (reproducible, no model) +
  PASS B blinded semantic rater (separately cost-authorized; OOS-blind; sees only pre-target
  packet + mechanism + evidence refs + coverage spec). Per-dimension exact agreement reported.
  Rehearsal uses a deterministic Pass-B stub for offline agreement machinery only (no claim).
```

## Deterministic Stage-1 control

```
DETERMINISTIC_STAGE1_CONTROL_SPEC = ARM G-D (src/research/item6/control_generator.py). Draws only
  from the baseline grammar; not deliberately weakened; every proposal formalizes to
  F1_BASELINE_EQUIVALENT. Establishes the covered space ARM G-L must exceed.
```

## Stage-2 framework (prospective placeholder only)

```
STAGE2_BASE_MODEL       = M0: deterministic baseline family universe only
STAGE2_AUGMENTED_MODEL  = M1: M0 + frozen LLM-discovered novel families (only difference)
STAGE2_PRIMARY_METRIC   = incremental OOS log loss (co: Brier delta, calibration/ECE); NOT hit rate
STAGE2_WALK_FORWARD_POLICY = strict chronological walk-forward; no future leakage; no tuning on
  final OOS block; families frozen before the folds they influence
STAGE2_MULTIPLICITY_POLICY = regularization / hierarchical shrinkage; nested regularized models with
  identical pre-specified selection; BH-FDR for family-level diagnostics; no cherry-picking
STAGE2_BLOCKED_UNLESS_STAGE1_PASS = true
```

## Stand-in rehearsal (zero spend, apparatus self-test)

```
STANDIN_FIXTURES = 120  (K=5)
MODE_RICH  : gate_passed=True   novel_families=69  be_rate=0.20 dup_rate=0.00 novel_rate=1.00
             interaction=0.587 grounding=1.00 falsifiability=1.00 survival=1.00 abstention=0.092
             F-classes: F1=109, F4=436  (proves the apparatus can register a PASS)
MODE_POOR  : gate_passed=False  novel_families=0   be_rate=1.00 dup_rate=0.80 novel_rate=0.00
             F-classes: F1=327, F2=218  (proves the instrument is falsifiable)
ARM_GD_CTRL: gate_passed=False  novel_families=0   be_rate=1.00 F1=600 (covered-space baseline)

STANDIN_GENERATED_MECHANISMS (RICH) = 545 across non-abstaining fixtures
STANDIN_BASELINE_EQUIVALENT (RICH)  = 109 (F1)
STANDIN_NOVEL (RICH)                = 436 (F4)
STANDIN_REJECTED (POOR traps)       = 218 (F2 provider-unsafe / future-leakage)
STANDIN_ABSTENTIONS                 = ~11 fixtures per mode (deterministic ~1/12)
Pass A / Pass B(stub) agreement (RICH): grounding 1.0, information_gain 1.0, interaction_depth 1.0,
  novelty 1.0 over n=545.
```

## Tests

```
TEST_COMMAND    = .venv/bin/python -m pytest tests/research/item6 -q
TESTS_COLLECTED = 66
TESTS_PASSED    = 66
TESTS_FAILED    = 0
TESTS_SKIPPED   = 0
TEST_DURATION   = ~20s

ANTI_IMITATION_TESTS_PASSED  = true (no worked example / metric pair / candidate id / template;
                                     no prior-audit leak; K=5; abstention present)
ANTI_BASELINE_TESTS_PASSED   = true (mirror/venue/profile -> BASELINE_EQUIVALENT; multi-signal ->
                                     novel; unsupported/ future -> reject; control never novel)
PROVIDER_SAFETY_TESTS_PASSED = true (each unsafe/future concept rejected; half-state requires
                                     half-resolution; schema firewall blocks numeric keys/claims)
POINT_IN_TIME_TESTS_PASSED   = true (cohort overlap=0; no outcome fields; outcome-blind modules;
                                     registry has no predictive result; harness deterministic)
```

## Integrity

```
V1_ARTIFACTS_UNCHANGED    = true (nothing under prior V1/V2/V3 dirs modified by this build)
V2_ARTIFACTS_UNCHANGED    = true
V3_ARTIFACTS_UNCHANGED    = true
QUALITY_AUDIT_UNCHANGED   = true (prior audit artifacts untouched; corrected rubric is new)

CHAMPION_BEFORE     = 0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9
CHAMPION_AFTER      = 0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9
CHAMPION_UNCHANGED  = true
CHAMPION_INDEPENDENT = true

LIVE_SONNET_CALLS = 0
BEDROCK_PAID_CALLS = 0
NEW_SPEND_USD = 0
```

## True-blocker checklist (all cleared)

```
1.  prompt contains a worked football hypothesis .......... NO  (anti-imitation tests pass)
2.  baseline-covered families not clearly specified ....... NO  (spec + JSON + detector)
3.  LLM output forced into old V2/V3 grammar at discovery . NO  (controlled free text)
4.  novelty gate not frozen ............................... NO  (stage1_gate.py frozen + doc)
5.  Stage-1 evaluator can see OOS outcomes ................ NO  (OOS-blind by construction)
6.  semantic duplicate procedure is outcome-aware ......... NO  (deterministic signature dedup)
7.  fresh cohort overlaps V1/V2/V3 ........................ NO  (overlap=0 verified + tested)
8.  provider-unsafe concepts silently accepted ............ NO  (F2 reject + tests)
9.  LLM numerical predictions enter the pipeline .......... NO  (FORBIDDEN_KEYS firewall + tests)
10. CHAMPION changes ...................................... NO  (hash identical)
11. paid call occurs ...................................... NO  (zero spend)
12. Stage 2 can proceed despite Stage-1 failure ........... NO  (BLOCKED_UNLESS_STAGE1_PASS)

TRUE_BLOCKERS_FOUND = 0
TRUE_BLOCKERS_FIXED = 0
TRUE_BLOCKERS_REMAINING = 0
```

## P2/P3 log (non-blocking)

```
P2-COHORT-LABELS: prospective-pool competition_id values from post-prior-era seasons are outside
  the six legacy league labels and appear as comp_<id> strata. Does not affect overlap=0 or
  prospectivity. At live time the cohort re-selects under the identical rule; league labelling can
  be enriched then. Logged, not blocking.
P3-PASS-B: the blinded semantic Pass B is a separate cost-authorized rater; only a deterministic
  stub runs in this zero-spend build. Logged.
P3-EXTENSION-PRIORITY: a mechanism carrying multiple escape-hatch signals is labelled by the most
  specific extension (two-axis > threshold > half-state > sequence > asymmetry > multi-metric).
  Reported for transparency.
```

## Success criteria

```
ITEM6_RESEARCH_QUESTION_FROZEN = true
TWO_STAGE_DESIGN = true
STAGE1_REQUIRED_BEFORE_STAGE2 = true
NO_WORKED_FOOTBALL_EXAMPLE = true
DETERMINISTIC_BASELINE_COVERAGE_FROZEN = true
BASELINE_EQUIVALENCE_DETECTOR_IMPLEMENTED = true
MECHANISM_DISCOVERY_PRECEDES_FORMALIZATION = true
MULTIPLE_MECHANISMS_PER_FIXTURE = true
ABSTENTION_ALLOWED = true
OLD_GRAMMAR_NOT_FORCED_DURING_DISCOVERY = true
STAGE1_PRIMARY_ENDPOINTS_FROZEN = true
STAGE1_PASS_FAIL_GATE_FROZEN = true
QUALITY_RUBRIC_CORRECTED = true
OOS_BLINDED_DURING_STAGE1 = true
FRESH_STAGE1_COHORT = true
V1_OVERLAP = 0 · V2_OVERLAP = 0 · V3_OVERLAP = 0
POINT_IN_TIME_SAFE = true
PROVIDER_DISCIPLINE = true
NO_LLM_NUMERICAL_PREDICTION = true
STAGE2_INCREMENTAL_VALUE_DESIGN_PROSPECTIVE = true
STAGE2_CANNOT_RUN_IF_STAGE1_FAILS = true
CHAMPION_UNCHANGED = true
LIVE_SONNET_CALLS=0 · BEDROCK_PAID_CALLS=0 · NEW_SPEND_USD=0
NO_TRUE_BLOCKERS_REMAIN = true

READY_FOR_ITEM6_STAGE1_HUMAN_SPEND_AUTHORIZATION = true
```

---

## Summary

### 1. What capability Item 6 actually tests

Whether a redesigned LLM instrument can perform **repeatable research-space expansion** — discover
grounded, falsifiable, provider-safe football hypothesis *families* that the deterministic baseline
enumeration cannot naturally produce (Stage 1) — and, only if that is demonstrated, whether those
families add **incremental OOS predictive information** over the baseline universe (Stage 2). It
tests discovery of *what to measure*, never prediction.

### 2. How this fixes the previous generation instrument

The prior instrument anchored generation with a fully worked football example, never told the model
what was already covered, and forced outputs back into the existing grammar — so the corpus was
disciplined but low-entropy (single-condition dominant, ~80% duplicate, zero novel families). Item 6
removes the worked example (enforced by tests), states the covered families abstractly, separates
mechanism discovery from formalization, requests K=5 distinct mechanisms with honest abstention, and
lets discovery use controlled free text so it can transcend the grammar. A deterministic
baseline-equivalence detector and an F0-F5 formalizer decide measurability — not the model.

### 3. How Stage 1 can fail

If the generator produces mostly baseline-equivalent ideas (BASELINE_EQUIVALENT_RATE > 0.60),
repeats itself within fixtures (SEMANTIC_DUPLICATE_RATE > 0.50), yields novel measurable families in
< 30% of fixtures, produces < 3 distinct new families, shows < 0.20 multivariable interaction, or its
novelty evaporates at formalization (survival < 0.50). The MODE_POOR and ARM_GD rehearsals confirm
the gate returns FAIL in exactly these regimes.

### 4. How Stage 2 can fail

If, under strict walk-forward with matched multiplicity and regularization, M1 (baseline + novel
families) does not improve OOS log loss / Brier / calibration over M0 (baseline only) — i.e. the
novel families carry no information beyond what regularization shrinks away.

### 5. Why a positive result would be credible

Because novelty is earned structurally (a conservative detector defaults to baseline-equivalent),
grounded (evidence refs validated, provider-safe, PIT-safe), measurable (survives deterministic
formalization to F3/F4), and repeatable (fixture-level, corpus-wide thresholds on a fresh
zero-overlap cohort), with an OOS-blind Stage-1 evaluator and a champion firewall. Stage 2 then
demands incremental predictive value under regularized, multiplicity-controlled, walk-forward
evaluation the LLM cannot game.

### 6. Why a negative result would be credible

Because the instrument was made deliberately *fairer* than before (no anchoring, explicit coverage,
free-text discovery, multiple mechanisms, abstention), the apparatus demonstrably can register a
PASS (MODE_RICH), and the gate thresholds are frozen before any output is seen. A failure therefore
reflects the generator, not a rigged instrument — the experiment is equally capable of disproving the
LLM hypothesis-layer thesis.

---

**ITEM6_FALSIFIABLE_DISCOVERY_EXPERIMENT_BUILD = PASS**
**NEXT_ACTION = AWAIT_EXPLICIT_HUMAN_STAGE1_SPEND_AUTHORIZATION**
