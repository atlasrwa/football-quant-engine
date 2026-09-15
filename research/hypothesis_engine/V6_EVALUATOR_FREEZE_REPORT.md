# V6 — Evaluator Freeze Report (§24, §25, §26)

**Zero spend.** Every evaluator path is implemented and exercised on synthetic input BEFORE any paid call. Frozen artifact: `out/v6/EVALUATOR_FREEZE.json` (sha `91d63edf9b1275c2…`), `frozen_before_first_paid_call: true`, `spend_usd_at_freeze: 0.0`, `run_exactly_once: true`.

## 1. Frozen evaluator modules (hashed)

`validator_v5`, `firewall_v5`, `schema_v4`, and the ten `v6_*` scientific modules (`v6_classes`, `v6_numeric_contract`, `v6_baseline`, `v6_conditioning`, `v6_qualified`, `v6_scorecard`, `v6_repeatability`, `v6_selfnoise`, `v6_stop`, `v6_verdict`). Each hash is in `EVALUATOR_FREEZE.json` and `PREREGISTRATION.json`.

## 2. PASS / MIXED / FAIL (§25) — frozen gates, in order

`EVALUABILITY (§26) → DISCIPLINE (§25) → PRIMARY (§21,§22)`

- **NON_EVALUABLE** if coverage minimums are unmet — no PASS/MIXED/FAIL is issued, regardless of any partial mechanical score.
- **FAIL** if the research arm degrades any discipline axis (`fabricated_evidence_rate`, `discipline_violation_rate`, `redundancy_rate`, `compiler_valid_rate`) beyond `DISCIPLINE_TOLERANCE = 0.05`.
- **FAIL** if the mean paired B−A qualified-rate difference ≤ 0.
- **PASS** if that difference exceeds the self-noise benchmark and discipline held.
- **MIXED** if the difference is positive but within the benchmark.

## 3. Evaluability minimums (§26) — floors on coverage, not on result

| minimum | value | rationale |
|---|---|---|
| paired fixtures | 8 | 10 scheduled; slack for 2 lost |
| valid responses / arm | 8 | one per paired fixture per arm |
| repeat groups / arm | 3 | = `v6_selfnoise.MIN_REPEAT_GROUPS_PER_ARM`; 4 scheduled |
| qualified denominator | 20 | a rate on fewer non-abstaining hypotheses is noise |

None is reachable by tuning after the fact; a run that meets them can still FAIL.

## 4. Every evaluator path exercised before spend (§24)

`synthetic_mutation_battery.json` runs, through the production adjudicator:
`perfect`, `null_ab`, `noisy`, `high_firewall`, `grounding_failure`, `availability_failure_base_arm`, `response_fatal`. The whole-run verdict paths (PASS / MIXED / FAIL / NON_EVALUABLE) are exercised in `test_v6_prespend.py` — all five `v6_verdict` branches verified:

| synthetic battery | verdict |
|---|---|
| research 0.85 vs base 0.30, tight noise | PASS (diff 0.55 > bench 0.037) |
| 3 paired fixtures only | NON_EVALUABLE (no verdict) |
| research fabrication degraded | FAIL (discipline) |
| research ≤ base | FAIL (primary, diff −0.05) |
| small positive diff, wide noise | MIXED (0.03 within 0.21) |

## 5. Test coverage

`test_v6_prespend.py`: **40 tests pass.** Full suite (V6 + V5A.2 + V5A.1): **131 tests pass**, no regression. All 18 §34-named tests present. No analysis script may be created after the first paid call that affects scientific aggregation; this evaluator is frozen now.
