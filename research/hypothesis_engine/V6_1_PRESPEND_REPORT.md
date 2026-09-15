# V6.1 GROUNDED RESEARCH GENERATOR — EVALUATOR REPAIR — PRE-SPEND REPORT

Experiment: `V6.1_GROUNDED_RESEARCH_GENERATOR_EVALUATOR_REPAIR`.
Status: **pre-spend, frozen.** ZERO model observations exist. This document does NOT
authorize spend.

All numbers below were produced by scripts in `research/hypothesis_engine/` reading frozen
artifacts in `research/hypothesis_oos/out/v6/` (V6, immutable) and
`research/hypothesis_oos/out/v6_1/` (V6.1, frozen). Every claim is re-derivable by running
the named script.

---

## 1. Executive verdict

**V6_1_PRESPEND_READY.**

All twelve required pre-spend states validated against concrete evidence
(`out/v6_1/V6_1_STATES.json`, `_v6_1_states.py`). The terminal state is
`V6_1_SPEND_AUTHORIZATION_REQUIRED` — a STOP. No `Converse`/`InvokeModel` call has been made
or is authorized by this work. Provider-native `CountTokens` was used only as
zero-generation infrastructure validation after the requests were frozen.

---

## 2. V6 historical preservation (immutable)

V6 is untouched. Verified this session by re-hashing every artifact:

| artifact | SHA-256 | status |
|---|---|---|
| `v6_verdict.py` (frozen evaluator) | `f195cf7f2db48d47d1bedc20cf6a364efc7b7efca46f5089045d3803b4d99854` | unchanged |
| `v6_scorecard.py` | `0b89e96ec042a762bbaf78b4e3cdb9e65054b9514688d6d0c260663f86a13bcf` | unchanged |
| `out/v6/EVALUATOR_FREEZE.json` | `d0c78442df6d63fba5a1fd83d0d5ad80d84691ae2da1c039e8b427032690d71c` | unchanged |
| `out/v6/execution/V6_VERDICT.json` | `0225963d1ca6e0ca2accaf6f1e9c84ff1a9077816dd99d4675922782ceac86d6` | unchanged |
| `out/v6/execution/scores.json` | `4ba5f37b98aec2ad2a04cf62f3b40587786a907dd6abe19c6939d2f26cf5ec3c` | unchanged |
| `out/v6/execution/EVIDENCE_CHAIN_MANIFEST.json` | `361ed76ee679e80b62627c3348c575e3cf3cd7388036a60b8453b03d869c2109` | unchanged |
| `out/v6/execution/V6_EXECUTION_STATES.json` | `0ad3f5871a0a0bcb192e9b3d0c773ac8e2b0b523cbc3a3a15047f950b389a6e3` | unchanged |
| 36 raw responses in `out/v6/execution/raw/` | present, unmodified | unchanged |

Durable separation of mechanical vs scientific interpretation
(`out/v6/execution/V6_POSTRUN_AUDIT.json`, forensic report
`V6_POSTRUN_EVALUATOR_DEFECT_REPORT.md` sha
`63d80da6f5da13fa688d73614dcfc037ce43f4e1d2cdccecccde07a0d32e314d`):

```
V6_EXECUTION_STATUS            = COMPLETE       (immutable mechanical fact)
V6_FROZEN_EVALUATOR_VERDICT    = FAIL           (immutable mechanical verdict)
V6_POSTRUN_AUDIT               = DECISIVE_EVALUATOR_DEFECT_DISCOVERED
V6_SCIENTIFIC_INTERPRETABILITY = COMPROMISED
V6_SCIENTIFIC_VERDICT          = None           (non-confirmatory)
```

The frozen FAIL is preserved and NOT overwritten. V6 yields **no confirmatory scientific
conclusion**.

---

## 3. Exact evaluator defect

**Location:** `v6_verdict._compile_rate` (frozen), consumed by the §25 discipline gate,
which runs before the primary gate.

**Old numerator logic:** `num += s["n_compiler_valid"]` for each response.
`n_compiler_valid` (from `v6_scorecard.score_response`) counts EVERY recovered hypothesis
that compiles — **including abstaining hypotheses**, which compile.

**Old denominator logic:** `den += s["n_nonabstaining"]` — only NON-abstaining hypotheses.

The numerator is drawn from a superset of the denominator's population, so a compilable
abstention pushes `numerator > denominator`, and the pooled rate can exceed 1.0.

**Counterexample (the real V6 run, 36 responses):** 33 abstentions, 28 compiler-valid; 399
non-abstaining, all compiler-valid.

| arm | old numerator (all compilable) | denominator (non-abstaining) | old rate | corrected numerator (non-abst ∩ compilable) | corrected rate |
|---|---|---|---|---|---|
| base | 211 | 183 | **1.1530** | 183 | 1.0000 |
| research | 216 | 216 | 1.0000 | 216 | 1.0000 |

The higher-abstaining base arm inflated to 1.153; degradation delta base−research = 0.153 >
tolerance 0.05, forcing **FAIL** before the primary was consulted.

**Corrected semantics** (`v6_1_verdict.compile_rate`): numerator = hypotheses that are BOTH
non-abstaining AND `compiler_valid`; denominator = non-abstaining. Invariant
`0 ≤ num ≤ den` holds by construction, so `0 ≤ rate ≤ 1`; empty denominator → `None`
(preregistered undefined convention), never 0 or 1.

---

## 4. Metric registry

`v6_1_metrics.REGISTRY` (11 metrics) declares, for every rate: numerator, denominator,
eligibility population, abstention treatment, availability treatment, zero-denominator
convention, legal domain, aggregation level, arm-comparison direction. Highlights:

| metric | numerator | denominator | eligibility | abstention | zero-denom | domain |
|---|---|---|---|---|---|---|
| **compiler_valid_rate** (repaired) | non-abstaining ∧ compiler-valid | n_nonabstaining | non-abstaining | **excluded from num AND den** | None | [0,1] |
| qualified_rate (PRIMARY input) | n_qualified | n_nonabstaining | non-abstaining | excluded from num AND den | None | [0,1] |
| fabricated_evidence_rate (DISCIPLINE) | n_fabricated_refs | n_refs | all refs | abstention refs included | None | [0,1] |
| redundancy_rate (DISCIPLINE) | n_redundant | n_recoverable | all recovered | included in denom | None | [0,1] |
| discipline_violation_rate (DISCIPLINE) | firewall/numeric/grounding/availability violations | n_recoverable | all recovered | included in denom (not a violation) | None | [0,1] |
| valid_evidence_reference_rate | n_valid_refs | n_refs | all refs | included | None | [0,1] |
| abstention_rate | n_abstentions | n_recoverable | all recovered | abstentions ARE numerator | None | [0,1] |
| grounded_abstention_rate | n_abstentions_with_refs | n_abstentions | abstaining only | denom IS abstaining pop | None | [0,1] |
| meaningful_interaction_rate | n_meaningful_interactions | n_interactions | interactions only | n/a | None | [0,1] |
| evidence_specific_qualified_rate | n_evidence_specific_qualified | n_nonabstaining | non-abstaining | excluded | None | [0,1] |
| paired_qualified_rate_diff (PRIMARY) | per-fixture research−base qualified_rate | n/a (a delta) | paired fixtures | inherited from qualified_rate | fixture excluded if either arm empty | [-1,1] |

Full registry: `out/v6_1/PREREGISTRATION.json → metric_registry`.

---

## 5. Invariant test results

`tests/research/hypothesis_oos/test_v6_1_prespend.py` — **38 passed.**

- **Metric contracts** (`TestMetricContracts`): `check_rate(211,183)` raises (the exact V6
  defect); zero-denominator → `None`; negatives/non-finite rejected; SIGNED_RATE_DELTA in
  [-1,1]; COUNT rejects negatives, floats and bool; SD ≥ 0; PROBABILITY in [0,1]; every
  registry metric declares full semantics; compiler repair excludes abstentions.
- **Property-based** (`TestPropertyBased`, `hypothesis` lib, ~900 generated examples):
  over randomized legal scorecards — 0 / all / many / asymmetric abstentions, compilable
  abstentions, no/all qualified, zero/one-element denominators, large counts, fatal
  responses — **no legal scorecard produced a rate < 0 or > 1**, and an impossible metric
  always surfaced as `EVALUATOR_INVALID`, never a scientific verdict.
- **Abstention contract** (`TestAbstentionContract`, Task 15): abstentions never inflate
  compiler validity, never enter an inapplicable denominator, never auto-qualify;
  abstention-heavy asymmetric arms never break the verdict.

---

## 6. V6 corrected replay — **POSTHOC / DIAGNOSTIC / NON_CONFIRMATORY**

`_v6_1_replay.py` → `out/v6_1/V6_POSTHOC_CORRECTED_REPLAY.json`. This is **NOT** a verdict on
V6 and **NOT** confirmatory evidence for V6.1. It does not reinterpret V6.

- Old defective compiler rate: base 211/183 = **1.153**, research 216/216 = 1.000.
- Corrected compiler rate: base **1.000**, research 1.000, delta 0.000 → the spurious FAIL
  gate no longer fires.
- Corrected diagnostic status/verdict: EVALUABLE / **MIXED** (mean paired diff 0.113384 is
  positive but within the self-noise benchmark 0.12812).

This MIXED is **diagnostic only** and was NOT used to select any V6.1 threshold, fixture,
model or score.

---

## 7. Second-order audit

`_v6_1_replay.py → second_order_audit` over the real 36 scores:
**`material_second_order_defect_found = False`.**

- No per-response rate out of [0,1]; no repaired compiler numerator > denominator.
- Arm-symmetric eligibility (both arms measured on the same fixtures; 0 fixtures only-in-one-arm).
- Simpson check on the decisive compiler axis: pooled (hypothesis-weighted) delta 0.0 and
  fixture-balanced delta 0.0 — signs agree.
- No null-treated-as-zero; no duplicate observations (keyed on fixture|arm|rep|seq).
- Abstention asymmetry confirmed as the sole defect driver: base abstention rate 0.1528,
  research 0.0.

No further scientifically material evaluator defect was found. Nothing blocks the V6.1
freeze on second-order grounds.

---

## 8. V6.1 fixture design

`v6_1_fixtures.select_fresh_fixtures` → `out/v6_1/fixture_selection.json`.

**Deterministic selection rule, fixed before generation, independent of V6 outcomes:**
1. eligible = competition ∈ V6's four (epl, laliga, laliga2, champ) AND both teams have ≥ 6
   PIT-safe prior matches AND packet builds in BOTH arms AND fixture ∉ held-out V5A/V6 set;
2. order candidates by **SHA-256(fixture_id)** — a hash of the identifier, which cannot
   encode any outcome;
3. take V6's exact per-competition count (5 epl, 1 laliga, 2 laliga2, 2 champ = 10).

**Independence:** the rule reads no hypothesis, qualified rate, primary difference, Arm-B
outcome, or corrected replay. Asserted in `fixture_selection.json →
independence_assertion` (all outcome fields `False`).

**Selected fresh held-out fixtures (10):** `mt_363781453, mt_581123873, mt_893327866,
mt_626435889, mt_979109898, mt_257078511, mt_191506144, mt_196566575, mt_979812440,
mt_361806675`. Zero overlap with the V6/V5A held-out set; deterministic across runs; no
shortfalls (eligible pool: champ 1538, epl 696, laliga 697, laliga2 832).

---

## 9. Scientific design comparison (`out/v6_1/V6_1_DESIGN_COMPARISON.json`)

| element | V6 | V6.1 | changed? | reason |
|---|---|---|---|---|
| evaluator `compiler_valid_rate` | abstentions in numerator (defect, rate>1) | numerator = non-abstaining ∧ compiler-valid | **YES** | repairs the demonstrated decisive defect |
| metric contract layer | none (impossible metric fed the verdict silently) | generic contracts enforced in production path | **YES** | impossible metric now aborts as EVALUATOR_INVALID |
| fixtures | 10 V5A.2 fixtures (V6 outcomes now known) | 10 FRESH held-out, deterministic outcome-blind | **YES** | confirmatory evidence must be fresh; size unchanged |
| model_id | us.anthropic.claude-sonnet-4-6 | same | no | frozen |
| temperature / max_tokens | 0.0 / 8192 | same | no | frozen |
| prompt / schema / firewall / validator | v6 versions | same | no | frozen |
| qualification / arm contrast / packet surface | v6 / v5a2_packet_v1 | same | no | frozen |
| schedule design | 36 calls (10×2 + 4×2×2) | same | no | frozen design |
| self-noise design (Z, floor, groups) | v6 | same | no | frozen |
| discipline tolerance | 0.05 | 0.05 | no | frozen (NOT tuned to V6's 0.153) |
| evaluability minimums | 8 / 8 / 3 / 20 | same | no | frozen |
| gate order | EVALUABILITY→DISCIPLINE→PRIMARY | same | no | frozen |
| cost architecture | CountTokens/byte-bound, retries off, round up | same mechanism | no | bound recomputed on V6.1 requests |
| sample size | 36 calls | 36 calls | no | NOT enlarged for V6's +0.1134<benchmark |

The evaluator defect repair (plus its metric-contract layer and the necessarily-fresh
fixtures) is the only substantive change.

---

## 10. Threshold integrity

No threshold, tolerance, floor, Z-multiplier, minimum, qualified-rate definition, firewall
threshold, stop-rule threshold, PASS/MIXED/FAIL ordering, or gate order was altered.
`v6_1_verdict` imports every threshold VERBATIM from the frozen `v6_verdict`
(`discipline_tolerance = 0.05`, `min_paired_fixtures = 8`, `min_repeat_groups_per_arm = 3`,
`min_qualified_denominator = 20`). Sample size is unchanged (36 calls). Knowledge of V6's
+0.1134 primary and 1.153 compiler rate influenced **no** parameter. Confirmed by
`test_Q_stop_rules_and_thresholds_frozen` and the design comparison
`threshold_integrity` field.

---

## 11. Cost proof (Task 17)

Recomputed **fresh** from V6.1's own frozen requests (V6's $8.79 ceiling NOT assumed).
Provider-native `bedrock:CountTokens` (`_count_tokens_v6_1.py`, non-generative, zero-charge,
retries-disabled no-Converse client) counted all 36 requests, each bound to its frozen
request SHA-256, model-mapping verified (profile `us.anthropic.claude-sonnet-4-6` →
foundation model `anthropic.claude-sonnet-4-6`):

- total exact input tokens: **1,312,305** (conservative UTF-8-byte bound 3,894,073 — every
  exact count ≤ its byte bound, confirming the bound is conservative);
- min / max input tokens per request: 17,729 / 60,685;
- max output tokens: 8,192 per call on every call (the true worst case);
- **hard ceiling = $8.52** (sum of per-request cent-up maxima; input exact, output at max,
  retries disabled → ≤ 1 billable attempt per logical call).

Artifacts: `out/v6_1/EXACT_INPUT_TOKEN_MANIFEST.json`
(sha `583593c992743c6333500bbbafd15ec49d097b6ec6b1739c84b12ac96354fc9c`),
`out/v6_1/INPUT_TOKEN_MANIFEST.json` (now built from the exact method).

---

## 12. Reproducibility

All 10 frozen V6.1 artifacts are **byte-identical under `PYTHONHASHSEED = 1, 2, 3, 12345`**
(verified by re-running `_freeze_v6_1.py` under each seed and diffing SHA-256). The freeze is
deterministic and network-free (exact counts read from a frozen file). Baseline hashes:

| artifact | SHA-256 |
|---|---|
| PREREGISTRATION.json | `93c2374248ec1c2f14a144205ebb198ec46f6c1dc65a98a00793918fce901cfc` |
| EVALUATOR_FREEZE.json | `4fe9c18b3a18f0a481072035ef96f0e49f3636b52699cd1d84da727bcd9eb8be` |
| fixture_selection.json | `557c5f4ea67e29d65708380a3a7e1878b0dc8dd7ce5cca1ca6e5da376c0d7625` |
| packets_base.json | `d8d86e8a89f440e9da801120f8f7d2c794129e14b591e4e0a83ea14999341d9b` |
| packets_research.json | `0c9e3ddf74d474f1bf5de9d6b56f92ce679e7b60330ff6e0e7d0cdfa189b5071` |
| EXACT_INPUT_TOKEN_MANIFEST.json | `583593c992743c6333500bbbafd15ec49d097b6ec6b1739c84b12ac96354fc9c` |

Frozen V6.1 evaluator modules: `v6_1_metrics.py`
`ad0711a89deb3070069ba73a389d613421cd66599ada993e9523d0e5d4593957`, `v6_1_verdict.py`
`421e43a725080978b03dc9dab0db3fca33dc2e50ce52920be8ae1e84ccda4e42`, `v6_1_fixtures.py`
`9053f60d60ce920707f30026782731b8e0a85a02f624f43ca17837c6fcbaf2d7`.

---

## 13. Tests

- `tests/research/hypothesis_oos/test_v6_1_prespend.py`: **38 passed** — metric contracts,
  ~900 property-based examples, all pre-spend path proofs A–R (below), abstention contract,
  V6 immutability guard.
- Pre-spend path proofs A–R (each a named test, all green):
  A corrected compiler rate ≤ 1 · B all contracts hold on an evaluable run · C invalid
  metric → EVALUATOR_INVALID never a verdict · D V6 diagnostic replay succeeds · E V6 frozen
  FAIL immutable · F replay labelled NON_CONFIRMATORY · G PASS path · H MIXED path · I FAIL
  path · J NON_EVALUABLE/null path · K discipline-gate path · L abstention-heavy base ≤ 1 ·
  M abstention-heavy research ≤ 1 · N zero-denominator explicit `None` · O fixture-balanced
  primary equals the frozen V6 value exactly · P verbosity does not change fixture weight ·
  Q stop rules/thresholds frozen · R CHAMPION isolation intact.
- Inherited V6 suites: 87 pass. **3 fail** —
  `test_no_inference_artifacts_before_authorization`,
  `test_count_tokens_generates_no_v6_response_artifact`,
  `test_zero_experimental_observations_remain`. These are **stale V6 pre-spend guards** that
  assert the ABSENCE of V6 execution artifacts; they fail only because V6 was authorized and
  executed (immutable history). They are not V6.1 regressions and V6 must not be edited to
  satisfy them.

---

## 14. CHAMPION isolation

`data/discovery/pilotC_stat_mixer.json` SHA-256 =
`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` — **unchanged**. No
production/prediction path imports any V6.1 module (only research scripts and tests do). The
V6.1 modules contain no reference to `p_model`, `pilotC`, `stat_mixer`, `predict` or
`champion`. A V6.1 failure cannot affect `p_model`; no V6.1 hypothesis becomes a model
feature. Confirmed by `test_R_champion_isolation_intact` and a repo-wide import scan.

---

## 15. Final states (`out/v6_1/V6_1_STATES.json`)

```
V6_1_V6_HISTORY_PRESERVED            [VALIDATED]
V6_1_EVALUATOR_DEFECT_REPRODUCED     [VALIDATED]
V6_1_COMPILER_RATE_FIXED             [VALIDATED]
V6_1_ALL_RATE_CONTRACTS_VALIDATED    [VALIDATED]
V6_1_POSTHOC_REPLAY_DIAGNOSTIC_ONLY  [VALIDATED]
V6_1_FRESH_FIXTURE_SELECTION_FROZEN  [VALIDATED]
V6_1_PIT_VALIDATED                   [VALIDATED]
V6_1_EVALUATOR_FROZEN                [VALIDATED]
V6_1_EXECUTION_DESIGN_FROZEN         [VALIDATED]
V6_1_EXACT_COST_BOUND_VALIDATED      [VALIDATED]
V6_1_FULLY_PREREGISTERED             [VALIDATED]
V6_1_SPEND_AUTHORIZATION_REQUIRED    [VALIDATED]  ← STOP
```

**STOP.** This prompt does not authorize execution. No `Converse`/`InvokeModel` call has
been made. No V6.1 model observation exists. Human spend authorization is required before any
paid inference.

---

## Governing principle honoured

V6.1 does not ask "how can we make the richer-evidence arm pass?" It repairs a demonstrated
evaluator defect, freezes generic metric invariants, selects fresh outcome-blind fixtures,
reuses every threshold verbatim, and leaves the answer open: after the repair, on fresh
PIT-safe evidence, a PASS, MIXED, FAIL or NON_EVALUABLE result are all acceptable. Knowledge
of V6's results was not allowed to make a favourable outcome easier.
