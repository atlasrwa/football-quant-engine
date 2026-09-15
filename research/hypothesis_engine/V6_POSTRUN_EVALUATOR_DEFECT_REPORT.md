# V6 POST-RUN EVALUATOR DEFECT — FORENSIC REPORT

Experiment: `V6_GROUNDED_RESEARCH_GENERATOR` (executed, complete). This report documents a
scientifically material defect discovered **after** execution in the frozen evaluator's
`compiler_valid_rate`. It does not alter V6. It establishes why V6's FAIL is
non-confirmatory and why a new experiment (V6.1) is required.

## V6 remains immutable

| artifact | SHA-256 | status |
|---|---|---|
| frozen `v6_verdict.py` (evaluator) | `f195cf7f2db48d47d1bedc20cf6a364efc7b7efca46f5089045d3803b4d99854` | unchanged |
| frozen `v6_scorecard.py` | `0b89e96ec042a762bbaf78b4e3cdb9e65054b9514688d6d0c260663f86a13bcf` | unchanged |
| `EVALUATOR_FREEZE.json` | `d0c78442df6d63fba5a1fd83d0d5ad80d84691ae2da1c039e8b427032690d71c` | unchanged |
| `execution/V6_VERDICT.json` | `0225963d1ca6e0ca2accaf6f1e9c84ff1a9077816dd99d4675922782ceac86d6` | unchanged, not edited |
| `execution/scores.json` | `4ba5f37b98aec2ad2a04cf62f3b40587786a907dd6abe19c6939d2f26cf5ec3c` | unchanged |
| `execution/EVIDENCE_CHAIN_MANIFEST.json` | `361ed76ee679e80b62627c3348c575e3cf3cd7388036a60b8453b03d869c2109` | unchanged |
| `execution/V6_EXECUTION_STATES.json` | `0ad3f5871a0a0bcb192e9b3d0c773ac8e2b0b523cbc3a3a15047f950b389a6e3` | unchanged |

**V6_EXECUTION_STATUS = COMPLETE** and **V6_FROZEN_EVALUATOR_VERDICT = FAIL** are preserved
permanently. No raw response was modified. No corrected replay is treated as a V6 verdict.

## The original frozen FAIL

The frozen `v6_verdict.final_verdict` returned, on the immutable 36 scores:

- scientific_status = EVALUABLE
- scientific_verdict = **FAIL**
- decisive gate = DISCIPLINE (§25), axis `compiler_valid_rate`
- base ≈ 1.153, research = 1.000, degradation (base − research) ≈ 0.153, tolerance 0.05.

## The exact defect

`compiler_valid_rate` is computed by `v6_verdict._compile_rate(scorecards)`:

```python
# OLD (defective)
num = den = 0
for s in scorecards:
    nb = s.get("n_nonabstaining") or 0     # DENOMINATOR excludes abstentions
    cv = s.get("n_compiler_valid") or 0    # NUMERATOR includes abstentions
    num += cv
    den += nb
return (num / den) if den else None
```

The two populations are different:

- **Numerator** `n_compiler_valid` (from `v6_scorecard.score_response`) counts EVERY recovered
  hypothesis whose structure compiles — **including abstaining hypotheses**, which compile.
- **Denominator** `n_nonabstaining` counts only non-abstaining hypotheses.

So the numerator is drawn from a superset of the denominator's population. Whenever a response
contains a compilable abstention, `numerator > denominator` for that response, and the pooled
rate can exceed 1.0. A rate above 1.0 is mathematically invalid: a proportion of a population
cannot exceed the whole population.

### Counterexample from the actual run

Across the 36 responses:

- 33 abstaining hypotheses, **28 of them compiler-valid** (an abstention with well-formed
  structure compiles).
- 399 non-abstaining hypotheses, all compiler-valid.

Pooled per arm:

| arm | OLD numerator (all compilable) | denominator (non-abstaining) | OLD rate | corrected numerator (non-abstaining ∩ compilable) | corrected rate |
|---|---|---|---|---|---|
| base | 211 | 183 | **1.1530** | 183 | 1.0000 |
| research | 216 | 216 | 1.0000 | 216 | 1.0000 |

The base arm abstained far more (it lacks the richer evidence and correctly declines
unsupported questions), so its 28 compilable abstentions inflated only the base numerator.

## Why the defect was decisive

The spurious base rate of 1.153 vs research 1.000 produced a degradation delta of ≈0.153,
which exceeds the 0.05 discipline tolerance and, because DISCIPLINE is evaluated before the
PRIMARY in the frozen gate order, forced the verdict to **FAIL** before the primary endpoint
was ever consulted. With the corrected metric, both arms compile at 1.000, the delta is 0.000,
and this gate does not fire.

## Materiality and timing

- The defect **directly caused** the decisive FAIL gate. It is scientifically material.
- It was discovered **only after** execution completed (during the execution report's
  forensic inspection of the `compiler_valid_rate > 1` anomaly). No pre-spend test asserted a
  generic `0 ≤ rate ≤ 1` metric contract, so the impossible value passed silently into the
  verdict.
- V6 is preserved untouched. The corrected replay (see V6.1 work) is **diagnostic only** and
  is never treated as a V6 verdict or as confirmatory evidence.

## Scientific consequence

- Mechanical frozen verdict: **FAIL** (immutable).
- Scientific conclusion from V6: **NONE / NON-CONFIRMATORY**, because the decisive evaluator
  path was defective.
- The unaffected primary diagnostic (mean paired qualified-rate diff ≈ +0.1134 vs benchmark
  0.1281 — positive but within self-noise) is **not** a PASS and must **not** be used to tune
  V6.1 thresholds, fixtures, model, or scoring.

Durable states recorded separately (see `V6_POSTRUN_AUDIT.json`):

```
V6_POSTRUN_AUDIT             = DECISIVE_EVALUATOR_DEFECT_DISCOVERED
V6_SCIENTIFIC_INTERPRETABILITY = COMPROMISED
V6_SCIENTIFIC_VERDICT        = None   (superseding interpretation; the frozen mechanical
                                       verdict remains FAIL and is not overwritten)
```
