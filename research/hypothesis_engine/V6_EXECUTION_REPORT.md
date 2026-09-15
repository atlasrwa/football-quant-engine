# V6_GROUNDED_RESEARCH_GENERATOR — EXECUTION REPORT

Live frozen experiment, executed once under explicit human authorization.

- **EXECUTION_STATUS:** COMPLETE (all 36 planned calls; no stop rule fired)
- **SCIENTIFIC_EVALUABILITY:** EVALUABLE
- **SCIENTIFIC_VERDICT:** **FAIL** (frozen discipline gate §25; see §I)
- **Actual spend:** $7.226406 of the $8.79 hard ceiling (never breached)
- **CHAMPION:** unchanged, isolated throughout.

The verdict was produced by the frozen `v6_verdict.final_verdict` on the immutable execution
scores. Nothing was patched, rerun, reinterpreted, or rescued after the first Converse call.

---

## A. Preflight (zero-dollar)

All Phase 1–6 checks passed at $0.00 before the first call.

| check | result |
|---|---|
| `reverify()` (21 modules + 27 upstream + 10 artifacts + 36 per-request + champion) | NONE (all match preregistration) |
| PREREGISTRATION.json | `f123e8b47894a3e0bb4febda54ff252b82c872579faf99901c939c533de83864` |
| EVALUATOR_FREEZE.json | `d0c78442df6d63fba5a1fd83d0d5ad80d84691ae2da1c039e8b427032690d71c` |
| V6_STATES.json (pre-run) | `81241f4076676c10eb594dcf53f80b74a06796d4b39103fcaf8d1af2412d04d3` |
| EXACT_INPUT_TOKEN_MANIFEST.json | `d156be1d466da380c47de385e7348d511ceb54fef5857254d13325b81a29a5ae` |
| INPUT_TOKEN_MANIFEST.json | `d65f45a029613bfe0434b3b758eb3af8eaafcd26c1db4bf4ecf7d6ac1634ae5a` |
| 36/36 canonical request SHA-256 | rebuilt and matched frozen manifest |
| model / profile | `us.anthropic.claude-sonnet-4-6` (Claude Sonnet 4.6, AWS Bedrock, us-east-1) |
| max_tokens / temperature | 8192 / 0.0 on every request |
| environment | boto3 / botocore 1.43.93 |
| retry configuration | `total_max_attempts = 1` asserted on the constructed client (retries disabled) |
| read / connect timeout | 900s / 20s |
| pricing verification | $0.003/1k in, $0.015/1k out (us-east-1 standard); revalidated current; no long-context surcharge |
| CountTokens manifest | 36/36 exact entries bound to request hashes; totals 1,402,204 in / 294,912 out |
| HARD_MAX_COST | $8.79 (independently recomputed) |
| CHAMPION hash | `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` (unchanged) |
| spend before first call | $0.00 |

No paid probe call was made during preflight.

## B. Execution

| quantity | value |
|---|---|
| planned calls | 36 |
| attempted calls | 36 |
| successful responses | 36 |
| billable attempts | 36 (1 per logical call; no retries) |
| transport failures | 0 |
| infrastructure failures | 0 |
| fatal responses | 0 |
| actual input tokens | 1,401,592 |
| actual output tokens | 201,442 |
| actual spend | $7.226406 |
| stop point | none (natural completion) |

Model failures by hypothesis class (aggregate, both arms): MODEL_AVAILABILITY_VIOLATION 149,
MODEL_COMPARATOR_INVALID 55, MODEL_FIREWALL_VIOLATION 47, MODEL_DEGENERATE_HYPOTHESIS 9;
VALID_HYPOTHESIS 172. Zero SCHEMA_INVALID / GROUNDING / NUMERIC_CONTRACT / REDUNDANT /
COMPILER_INVALID / INFRASTRUCTURE / VALID_ABSTENTION.

## C. Fixture coverage

All 10 paired fixtures completed in both arms. First four fixtures carry 3 replicates per arm
(self-noise repeats); the rest carry 1.

| fixture | A resp | B resp | A qualified/denom | B qualified/denom | paired |
|---|---|---|---|---|---|
| mt_010243515 | 3 | 3 | 9/28 = 0.321 | 27/36 = 0.750 | yes |
| mt_010243537 | 3 | 3 | 28/31 = 0.903 | 24/36 = 0.667 | yes |
| mt_010243938 | 3 | 3 | 5/30 = 0.167 | 17/36 = 0.472 | yes |
| mt_010244159 | 3 | 3 | 0/33 = 0.000 | 16/36 = 0.444 | yes |
| mt_010244193 | 1 | 1 | 3/9 = 0.333 | 6/12 = 0.500 | yes |
| mt_010441320 | 1 | 1 | 0/11 = 0.000 | 0/12 = 0.000 | yes |
| mt_010441491 | 1 | 1 | 5/9 = 0.556 | 4/12 = 0.333 | yes |
| mt_010444904 | 1 | 1 | 0/11 = 0.000 | 10/12 = 0.833 | yes |
| mt_012232295 | 1 | 1 | 3/11 = 0.273 | 3/12 = 0.250 | yes |
| mt_012232411 | 1 | 1 | 6/10 = 0.600 | 0/12 = 0.000 | yes |

No fixture is incomplete. Valid responses per arm: base 18, research 18.

## D. Hypothesis outcomes (arm-separated aggregate)

| class | base | research |
|---|---|---|
| VALID_HYPOTHESIS (qualified) | 59 | 113 |
| MODEL_AVAILABILITY_VIOLATION | 138 | 11 |
| MODEL_FIREWALL_VIOLATION | 19 | 28 |
| MODEL_COMPARATOR_INVALID | 0 | 55 |
| MODEL_DEGENERATE_HYPOTHESIS | 0 | 9 |
| MODEL_SCHEMA_INVALID | 0 | 0 |
| MODEL_GROUNDING_VIOLATION | 0 | 0 |
| MODEL_NUMERIC_CONTRACT_VIOLATION | 0 | 0 |
| MODEL_REDUNDANT_HYPOTHESIS | 0 | 0 |
| MODEL_COMPILER_INVALID | 0 | 0 |
| VALID_ABSTENTION | 0 | 0 |
| INFRASTRUCTURE_FAILURE | 0 | 0 |
| parse-fatal responses | 0 | 0 |

Observation (not a verdict input): the base arm's dominant failure is availability
(proposing conditions the compressed packet does not expose); the research arm converts many
of those into valid hypotheses but incurs more comparator/degenerate failures.

## E. Self-noise (frozen estimator, V6 replicate observations)

- repeat groups available: base 4, research 4 (each with 3 measured repeats)
- pooled within-(fixture,arm) SD: **0.203369**
- floor (`MIN_SELF_NOISE_SD` = 0.05) applied: **no**
- `sd_used`: **0.203369**
- Z multiplier: 1.645
- resulting self-noise superiority benchmark (SE of paired mean diff × Z): **0.12812**

The historical 0.363 SD and 0.228685 MDE remain planning diagnostics only; they were not
inserted into the verdict. The run's own measured SD (0.203) is lower than the 0.363 planning
value.

## F. Discipline (research − base, tolerance 0.05)

| axis | base | research | delta | degraded |
|---|---|---|---|---|
| fabricated_evidence_rate | 0.000 | 0.000 | 0.000 | no |
| discipline_violation_rate | 0.7269 | 0.1806 | −0.546 | no (research better) |
| redundancy_rate | 0.00463 | 0.000 | −0.0046 | no |
| compiler_valid_rate (higher better) | 1.1530 | 1.0000 | base−research = **+0.153** | **YES** |

The discipline gate degradation is on `compiler_valid_rate`. See §I for the mechanism.

## G. Primary endpoint

- primary statistic: per-fixture paired Arm B − Arm A **qualified-rate** difference
- number of paired fixtures: 10
- per-fixture diffs: +0.450, −0.236, +0.321, +0.444, +0.167, 0.000, −0.222, +0.833, −0.023, −0.600
- **mean paired difference: +0.113384**
- frozen self-noise benchmark: **0.12812**
- comparison: mean diff (0.1134) does **not** exceed benchmark (0.1281) → `exceeds_self_noise = False`

On the primary alone this would be MIXED (positive but within self-noise). It was not reached
as the deciding gate: discipline is evaluated before the primary in the frozen gate order.

## H. Scientific evaluability

| prerequisite | required | observed | met |
|---|---|---|---|
| paired fixtures | ≥ 8 | 10 | yes |
| valid responses per arm | ≥ 8 | base 18, research 18 | yes |
| repeat groups per arm (≥2 reps) | ≥ 3 | base 4, research 4 | yes |
| qualified denominator | ≥ 20 | 399 | yes |

**EVALUABLE** — no unmet minimums.

## I. Scientific verdict

**FAIL**, exactly as produced by the frozen `v6_verdict.final_verdict`:

> FAIL: the research arm degraded discipline beyond tolerance 0.05 on
> `['compiler_valid_rate']`. §25 requires no material discipline degradation.

Frozen gate order: EVALUABILITY → **DISCIPLINE (fired here)** → PRIMARY.

**Honest characterization of the FAIL mechanism (recorded, not patched).** The
`compiler_valid_rate` in the frozen scorecard is `n_compiler_valid / n_nonabstaining`.
`n_compiler_valid` counts every hypothesis whose structure compiles — including abstaining
hypotheses, which compile — while the denominator excludes abstentions. The base arm abstains
far more (it lacks the richer evidence), so its numerator exceeds its denominator and the
pooled base rate is 1.153, above the research arm's 1.000; the base−research degradation delta
is 0.153 > 0.05, tripping the gate. This numerator/denominator asymmetry is a property of the
**frozen** evaluator that was validated and hashed before spend. Per the absolute scientific
rule and Phase 16, it is NOT corrected in this run: the verdict stands as FAIL. It is flagged
here as a candidate defect for a future, separately-authorized V6.1 — a repaired experiment
must be a new version, not a patch of this one.

Note also: this FAIL is a discipline-gate FAIL driven by an evaluator accounting asymmetry, not
evidence that richer context hurts the research layer. On the substantive primary endpoint the
research arm's qualified rate was higher on balance (mean paired diff +0.113), though within
self-noise. EXECUTION_STATUS, SCIENTIFIC_EVALUABILITY, and SCIENTIFIC_VERDICT are kept separate
(§14): the run executed cleanly, is evaluable, and the frozen evaluator returns FAIL.

## J. Cost reconciliation

| quantity | value |
|---|---|
| HARD_MAX_COST | $8.79 |
| actual spend | $7.226406 |
| ceiling breached | no (cumulative at final call $7.226406) |
| total exact frozen input tokens (bound) | 1,402,204 |
| total actual input tokens | 1,401,592 |
| per-request: observed input ≤ frozen exact | 36/36 (uniform −17 tokens/request) |
| total actual output tokens | 201,442 (of 294,912 max) |
| expected / p90 diagnostics (frozen) | $6.7355 / $7.1977 |

Phase 10 reconciliation: every observed `inputTokens` is at or below the pre-spend CountTokens
value; no `APPARATUS_TOKEN_ACCOUNTING_MISMATCH`. The hard-cost guarantee held.

## K. Raw evidence hashes

Immutable evidence chain: `research/hypothesis_oos/out/v6/execution/EVIDENCE_CHAIN_MANIFEST.json`
(SHA-256 `361ed76ee679e80b62627c3348c575e3cf3cd7388036a60b8453b03d869c2109`). It binds, for each
of the 36 calls: `request_sha256 → raw_response_sha256 → adjudicated_scorecard_sha256`. Raw
responses are preserved under `execution/raw/NNN.json`, written before adjudication and never
overwritten. Pre-call ledger: `execution/EXECUTION_LEDGER.json`
(`f01fc33b13d7116fee911c1426ac28b1ba648a095a271a7364d9a9ac47dd518b`).

## L. CHAMPION isolation

CHAMPION artifact `data/discovery/pilotC_stat_mixer.json` SHA-256
`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` — unchanged before and after
execution. No V6 module imports the production prediction path; production does not import V6.
No V6 hypothesis or feature entered `p_model`. Production was unaffected throughout.

---

## Machine states (what actually happened)

```
V6_EXECUTION_STARTED
V6_EXECUTION_COMPLETE            (36/36 calls, no stop rule fired)
V6_SCIENTIFIC_EVALUABILITY = EVALUABLE
V6_SCIENTIFIC_VERDICT      = FAIL   (frozen discipline gate §25, compiler_valid_rate)
```

Authorization expired on V6 termination. This report authorizes no rerun, repair, V6.1, V7,
alternate model, or supplementary sampling; any of those requires separate authorization.
