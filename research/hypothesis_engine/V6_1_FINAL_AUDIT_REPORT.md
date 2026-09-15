# V6.1 FINAL PRE-SPEND INDEPENDENT AUDIT

Experiment: `V6.1_GROUNDED_RESEARCH_GENERATOR_EVALUATOR_REPAIR`.
Standard applied: falsify readiness, not confirm it. Every reported PASS was re-verified from
production code and immutable artifacts. This document does NOT authorize spend.

---

## 1. Executive verdict

**V6_1_FINAL_AUDIT_FIXED_AND_REFROZEN**

The only defect found was the three stale lifecycle tests already flagged. They were repaired
with lifecycle-aware semantics (engineering only — no scientific parameter changed). All
frozen scientific artifacts are byte-unchanged. No genuine pre-spend scientific defect was
found across 24 investigative phases. V6.1 returns to explicit human spend authorization at
`V6_1_SPEND_AUTHORIZATION_REQUIRED`.

---

## 2. Findings by severity

**BLOCKING:** none.

**HIGH:** none.

**MEDIUM:** none.

**LOW**
- L1 — `tests/research/hypothesis_oos/{test_v6_prespend, test_v6_exact_tokens}.py`: 3 tests
  asserted "V6 execution artifacts must not exist", an invariant valid only before V6 was
  authorized. Risk: red suite masks real regressions / invites unsafe silencing. Fix:
  replaced with lifecycle-aware validation (Phase 1). Tests: 9 new lifecycle tests + the 3
  repaired in place. **Resolved.**

**INFORMATIONAL**
- I1 — V6.1 has no dedicated executor yet (correct: it is pre-spend). The pre-call cost
  guard (`would_exceed_ceiling`) and observed-vs-frozen-bound reconciliation are proven in
  `research/hypothesis_engine/_execute_v6.py`. A V6.1 executor MUST reuse that exact guard
  and `v6_transport.build_client` (retries disabled). Pre-EXECUTION requirement, not a
  pre-spend blocker.
- I2 — Registry declares only RATE and SIGNED_RATE_DELTA metric types (the only ones the
  verdict consumes). COUNT/PROBABILITY/SD/SAMPLE_SIZE contract checkers exist and are tested
  but no such metric is in the verdict path. Consistent, not a defect.
- I3 — Added a root `tests/conftest.py` Hypothesis profile (`ci` = derandomize, print_blob)
  for reproducible property testing. Test infrastructure only; the `asymmetric` suite has
  its own conftest and still passes (448 tests).

---

## 3. Lifecycle-test repair

The obsolete invariant was "execution artifacts must not exist" — correct only for a
never-authorized experiment. After V6's authorized run it became historically false.

New module `src/research/hypothesis_oos/experiment_lifecycle.py` reads the lifecycle PHASE
from the experiment's immutable execution-state artifact (never the filesystem):
- **NEVER_EXECUTED** (no state artifact, or no `execution_status` in {COMPLETE, STOPPED}):
  execution artifacts MUST NOT exist (`scores.json`, `raw/`, `execution_summary.json`,
  `execution_log.jsonl`).
- **COMPLETE / STOPPED**: execution artifacts MUST exist, be complete, and hash-match the
  preserved hashes.

Seven required regression cases (all pass, `test_experiment_lifecycle.py`):
1 completed-valid → PASS; 2 complete-but-missing → FAIL; 3 hash-mutated → FAIL; 4 pre-spend
+ dir absent → PASS; 5 pre-spend + model response → FAIL; 6 pre-spend + ledger pretending
calls → FAIL; 7 state/filesystem disagree → FAIL. The original 3 tests were repaired in
place (not skipped/xfailed/deleted). V6 history untouched.

---

## 4. Evaluator call graph (actual)

```
final_verdict (v6_1_verdict)                     ← the ONLY verdict entry point
├─ _check_per_response_rates → MC.check_value_in_unit_interval   [contract]
├─ V6.evaluability(scorecards, repeat_groups)                    [frozen, outcome-neutral]
├─ discipline (v6_1_verdict, MODULE-LOCAL)                       [REPAIRED]
│   ├─ V6._arm / V6._pooled_rate → MC.check_value_in_unit_interval
│   ├─ compile_rate (v6_1_verdict) → _nonabstaining_compiler_valid → MC.check_rate
│   └─ MC.check_signed_rate_delta
├─ V6.primary(scorecards, self_noise)                            [frozen, fixture-balanced]
│   └─ SN.paired_differences / SN.benchmark (v6_selfnoise)       [frozen]
└─ verdict decision: EVALUABILITY → DISCIPLINE → PRIMARY
   (MetricContractViolation anywhere → EVALUATOR_INVALID, scientific_verdict=None)
```

The legacy buggy `v6_verdict._compile_rate` is reachable ONLY from `v6_verdict.discipline`,
which `v6_1_verdict.final_verdict` never calls. Proven by runtime tripwire: monkeypatching
both `V6._compile_rate` and `V6.discipline` to raise, then running the V6.1 verdict over the
real 36 scores, completes cleanly (→ MIXED, compiler 1.0/1.0). Test:
`test_legacy_compile_rate_unreachable_from_v6_1_verdict`.

---

## 5. Metric registry audit (11 metrics)

Every metric declares numerator, denominator, eligibility, abstention, availability,
zero-denominator, domain, aggregation, arm-direction. Contract enforcement is mechanical:
`RATE` requires finite `0 ≤ num ≤ den` and `0 ≤ value ≤ 1` (else raise); zero-denominator →
`None`; `SIGNED_RATE_DELTA ∈ [-1,1]`; COUNT/SAMPLE_SIZE integer ≥ 0; SD finite ≥ 0;
PROBABILITY ∈ [0,1]. A violation raises `MetricContractViolation` → `EVALUATOR_INVALID`,
never a scientific verdict.

| metric | type | numerator | denominator | eligibility | abstention | zero-denom | range | role |
|---|---|---|---|---|---|---|---|---|
| compiler_valid_rate | RATE | non-abst ∧ compiler-valid | n_nonabstaining | non-abstaining | excl num+den | None | [0,1] | discipline (repaired) |
| qualified_rate | RATE | n_qualified | n_nonabstaining | non-abstaining | excl num+den | None | [0,1] | primary input |
| evidence_specific_qualified_rate | RATE | n_evidence_specific_qualified | n_nonabstaining | non-abstaining | excl | None | [0,1] | diagnostic |
| valid_evidence_reference_rate | RATE | n_valid_refs | n_refs | all refs | incl | None | [0,1] | diagnostic |
| fabricated_evidence_rate | RATE | n_fabricated_refs | n_refs | all refs | incl | None | [0,1] | discipline |
| abstention_rate | RATE | n_abstentions | n_recoverable | all recovered | is numerator | None | [0,1] | descriptive |
| grounded_abstention_rate | RATE | n_abstentions_with_refs | n_abstentions | abstaining only | is denom | None | [0,1] | descriptive |
| meaningful_interaction_rate | RATE | n_meaningful_interactions | n_interactions | interactions | n/a | None | [0,1] | descriptive |
| redundancy_rate | RATE | n_redundant | n_recoverable | all recovered | incl denom | None | [0,1] | discipline |
| discipline_violation_rate | RATE | fw/num/grnd/avail violations | n_recoverable | all recovered | incl denom | None | [0,1] | discipline |
| paired_qualified_rate_diff | SIGNED_RATE_DELTA | research−base per fixture | n/a | paired fixtures | inherited | fixture excluded | [-1,1] | primary |

---

## 6. Original defect reproduction

- OLD frozen `v6_verdict._compile_rate` on a synthetic case (3 non-abstaining compile + 2
  compilable abstentions): **5/3 = 1.667 > 1**.
- OLD frozen logic on the real V6 base scores: **211/183 = 1.1530054644808743** (exact
  historical value).
- V6.1 `compile_rate` on the identical inputs: **1.0** (synthetic 3/3, historical 183/183).
- Root cause: 28 compilable abstentions entered the numerator against a non-abstaining
  denominator. The fix is structural (numerator population ⊆ denominator population), so
  `num ≤ den` by construction — not merely a different output.
Tests: `test_old_logic_reproduces_gt_one_new_logic_bounded`,
`test_exact_historical_v6_numbers_reproduced`.

---

## 7. Property-based testing

Generators (`hypothesis`, derandomized `ci` profile): random hypothesis sets over
{abstaining, compiler_valid, qualified, redundant}; response measured/fatal; per-arm lists
0–25 responses; 0–40 hypotheses each. Coverage confirmed non-vacuous (400/300/150/200/300
generated examples per property). Explicit cases: asymmetric/all/no abstention, all
compiler-valid/invalid, zero/one-element denominators, extreme sizes, malformed rate fields
(NaN/inf/negative/>1 → EVALUATOR_INVALID), one-arm verbosity, one-fixture domination. No
legal scorecard produced a rate <0 or >1; no impossible metric ever produced a scientific
verdict. Failing examples persist to `.hypothesis/examples`; `print_blob` reproduces them.

---

## 8. V6 replay isolation

The corrected replay (`out/v6_1/V6_POSTHOC_CORRECTED_REPLAY.json`) is tagged
`["NON_CONFIRMATORY","DIAGNOSTIC_ONLY"]`, `is_v6_scientific_verdict=false`,
`is_v6_1_confirmatory_evidence=false`, `must_not_tune_v6_1=true`. Structural firewall:
`_freeze_v6_1.py` contains no reference to `out/v6/execution`; the V6.1 freeze/verdict read
only fresh corpus fixtures. V6 fixtures are held out of the eligible universe, so a V6
observation cannot populate V6.1 confirmatory data. Tests: `TestReplayFirewall` (4).

---

## 9. Fixture selection proof

- Eligible universe: 5319 index records → 4100 in V6's four competitions → 11 held-out
  removed (10 V6 + 1 V5A.1-excluded) → **3763 priors-eligible** (epl 696, champ 1538,
  laliga2 832, laliga 697).
- Rule: eligible = competition ∈ {epl,laliga,laliga2,champ} ∧ both teams ≥ 6 PIT-safe priors
  ∧ builds in both arms ∧ not held-out; ordered by **SHA-256(fixture_id)**; take V6's
  per-competition count (5/1/2/2).
- Selected 10: `mt_363781453, mt_581123873, mt_893327866, mt_626435889, mt_979109898,
  mt_257078511, mt_191506144, mt_196566575, mt_979812440, mt_361806675`.
- Held-out: 0 overlap with V6/V5A.
- Outcome-blind: module imports only `corpus_adapter` + `v5a1_packet`; reads no
  hypothesis/rate/paired-diff/replay. The competition mix equals the composition of V6's
  fixture identities (design-level, verified by recomputation), a permitted reuse.
- Deterministic under PYTHONHASHSEED 1/2/3/12345 (identical selection hash).

---

## 10. PIT proof

All 10 fixtures: every match observation strictly before the fixture cutoff (verified
per-fixture; e.g. mt_191506144 max_obs 1764511500 < cutoff 1764878400). `pit_audit.json`
`n_problems=0`. Leakage mutations rejected: future match (cutoff+1d), observation at cutoff,
target-id leak. No market/odds evidence exists — `market_prices` appears only in the
AVAILABILITY_MAP/METRIC_SEMANTICS as `corpus_supported:false / deliberately absent`. Tests:
`TestArmIsolationAndPIT`.

---

## 11. Treatment isolation

For all 10 fixtures the canonical Converse requests are byte-identical across arms in
`system`, `modelId`, `inferenceConfig` (temperature 0.0, maxTokens 8192) and `toolConfig`
(schema); only `messages` (the evidence payload) differs — base ≈ 45 KB, research ≈ 141 KB,
research a strict superset of base evidence. 0 identity leaks, no treatment labels. The
richer arm receives no extra coaching, looser schema, larger budget, or easier compiler.

---

## 12. Self-noise / sample design

Frozen formula `benchmark = Z·sqrt( Σ_f sd²(1/n_base_f + 1/n_research_f) / F² )`, Z=1.645,
`MIN_SELF_NOISE_SD=0.05`, `MIN_REPEAT_GROUPS_PER_ARM=3`. Evaluability minimums 8/8/3/20.
Discipline tolerance 0.05. 36 calls (10 paired ×2 + 4 repeat ×2 ×2). Every value is
identical to V6 and none was altered after seeing V6's +0.1134 / 0.1281 / MIXED. The formula
consumes NEW V6.1 repeat observations at run time; it consumes no V6 outcome.

---

## 13. Stop rules

| rule | trigger | threshold | eligibility | class |
|---|---|---|---|---|
| firewall/numeric/grounding/schema rate | per-category / n_hypotheses | 0.30 | 3 fixtures ∧ 2 valid/arm ∧ 6 calls | MODEL (gated) |
| response_parse_fatal rate | fatal / calls | 0.30 | same | MODEL (gated) |
| infrastructure failure | count | ≥1 | none | APPARATUS (immediate) |
| consecutive transport failure | count | ≥3 | none | APPARATUS (immediate) |
| cost ceiling | spend > ceiling | $8.52 | none | APPARATUS (immediate) |

Proven: 10/10 firewall violations at ONE fixture does NOT stop (model rules diversity-gated,
`model_rules_gated=True`); infra failure at 1 call and spend>ceiling stop immediately. Fixes
the V5A.2 one-fixture-halt defect.

---

## 14. Exact cost proof (independent Decimal)

From `EXACT_INPUT_TOKEN_MANIFEST.json` (36 provider-native CountTokens entries), recomputed
with `Decimal` and `ROUND_CEILING`: per-request `ceil(exact_in·$0.003/1k + 8192·$0.015/1k)`
summed = **$8.52**, matching the manifest. Total exact input 1,312,305 tokens (each ≤ its
UTF-8-byte bound), max output 294,912 (36×8192), `max_billable_attempts=1` per call. Global
round-up $8.37 ≤ per-call sum $8.52. Expected/p90 are not used as bounds. Pre-call guard
(`_execute_v6.would_exceed_ceiling`) refuses to start a call that would breach the ceiling
and aborts if observed input exceeds the frozen bound.

---

## 15. Reproducibility

All 10 deterministic V6.1 artifacts (fixture_selection, packets_base/research, pit_audit,
arm_isolation_audit, call_schedule, INPUT_TOKEN_MANIFEST, EVALUATOR_FREEZE,
V6_1_DESIGN_COMPARISON, PREREGISTRATION) rebuild byte-identical under PYTHONHASHSEED
1/2/3/12345. `EXACT_INPUT_TOKEN_MANIFEST.json` stable. Operational CountTokens metadata is
isolated in `count_tokens_audit_log.jsonl`.

---

## 16. CHAMPION isolation

`data/discovery/pilotC_stat_mixer.json` SHA-256
`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` — unchanged. Executable
check: importing all three V6.1 modules loads zero pilot/mixer/champion/p_model modules into
`sys.modules`. No production/prediction source imports V6.1. CHAMPION is a pure-data JSON
artifact (no code to import). A V6.1 failure cannot touch `p_model`. Bidirectional isolation.

---

## 17. Full test results (no hidden expected failures)

| suite | result |
|---|---|
| V6.1 pre-spend (`test_v6_1_prespend.py`) | 68 passed |
| lifecycle (`test_experiment_lifecycle.py`) | 9 passed |
| V6 pre-spend + exact tokens (repaired) | 90 passed |
| full `tests/research/hypothesis_oos/` | 294 passed |
| `hypothesis_engine` + `hypothesis_oos` | 805 passed |
| `tests/asymmetric/` (heavy Hypothesis) | 448 passed |
| full tree collection | 4823 collected, no errors |

0 failed, 0 skipped, 0 xfail across all relevant suites. The full `tests/` tree is too large
to execute in a single pass here; it collects cleanly and every suite touching the audited
code passes.

---

## 18. V6 vs V6.1 parameter diff

| parameter | V6 | V6.1 | changed? | reason |
|---|---|---|---|---|
| discipline_tolerance | 0.05 | 0.05 | no | frozen |
| min_paired_fixtures | 8 | 8 | no | frozen |
| min_valid_responses_per_arm | 8 | 8 | no | frozen |
| min_repeat_groups_per_arm | 3 | 3 | no | frozen |
| min_qualified_denominator | 20 | 20 | no | frozen |
| Z_MULTIPLIER | 1.645 | 1.645 | no | frozen |
| MIN_SELF_NOISE_SD | 0.05 | 0.05 | no | frozen |
| stop fixtures/valid/calls/rate | 3/2/6/0.30 | 3/2/6/0.30 | no | frozen |
| discipline axes + compile axis | same | same | no | frozen |
| gate order | EVAL→DISC→PRIMARY | EVAL→DISC→PRIMARY | no | frozen |
| output limits (max_tokens) | 8192 | 8192 | no | frozen |
| model / temperature | sonnet-4-6 / 0.0 | sonnet-4-6 / 0.0 | no | frozen |
| n_calls | 36 | 36 | no | frozen |
| compiler_valid_rate numerator | incl abstentions (bug) | non-abst ∧ compiler-valid | **YES** | demonstrated defect repair |
| metric contract layer | none | enforced | **YES** | impossible metric → EVALUATOR_INVALID |
| fixture identities | V6 set | fresh held-out | **YES** | confirmatory evidence must be fresh |

No scientific parameter changed after seeing V6. The three changes are the mandated repair,
its safety layer, and fresh fixtures.

---

## 19. Spend state

```
V6_1_CONVERSE_CALLS            = 0
V6_1_INVOKEMODEL_CALLS         = 0
V6_1_EXPERIMENTAL_OBSERVATIONS = 0
V6_1_SPEND_AUTHORIZATION       = NOT_GRANTED
```

No Converse/InvokeModel call was made. Provider-native CountTokens was used only as
zero-generation infrastructure verification against the already-frozen requests. No V6.1
model observation exists.

---

## 20. Final machine states

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
V6_1_FULL_TEST_SUITE_GREEN           [VALIDATED]
V6_1_FINAL_INDEPENDENT_AUDIT_PASSED  [VALIDATED]
V6_1_FULLY_PREREGISTERED             [VALIDATED]
V6_1_SPEND_AUTHORIZATION_REQUIRED    [VALIDATED]  ← STOP
```

**STOP.** This audit does not authorize paid V6.1 execution. Human spend authorization is
required before any Converse/InvokeModel call.
