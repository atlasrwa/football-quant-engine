# V7.1 — executive summary and continuation state

**Date:** 2026-09-15 · **Branch:** `feat/v7-1-hardening` (pushed to origin) · **Head:** `e109616e5`

## Terminal state

```
V7_1_READY_FOR_CONFIRMATORY_OOS
CONFIRMATORY_OOS_COMPUTED = false
CONFIRMATORY_OOS_VIEWED   = false
BEDROCK_CHANGE_REQUIRED   = false     KIRO_HANDOFF_REQUIRED = false
CHAMPION 0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9 — unchanged
```

The full report is `research/hypothesis_engine/V7_1_PRE_OOS_HARDENING_REPORT.md` (sections A–V).
This file is the short version plus what a fresh session needs to resume.

## What was built

**A semantic layer between the LLM and measurement** — `src/research/hypothesis_v71/`, 20 modules.
V7's defect class was that a comparator was a *label* the executor branched on; V7.1 makes it an
explicit `(cohort, baseline)` **Selector pair** in a frozen `COMPARATOR_BINDINGS` table, compiles
the pair, and fails closed on anything unbound. Nothing is ever recovered from prose.

| module | role |
|---|---|
| `ontology.py` | frozen vocabulary; 10 comparators, each binding a selector pair |
| `ir.py` | `Filter`/`Selector`/`IR`; `Selector.key()` is the degeneracy test; SHA-256 `ir_id()` |
| `invariants.py` | 9 structural refusals before any measurement |
| `capability.py` | one provider contract; UNKNOWN ≠ UNSUPPORTED; NULL ≠ zero; ≥4-of-6 coverage policy |
| `compiler.py` | executes selector pairs; O(1) prefix fast path; refuses per-fixture collapse |
| `corpus_index.py` | point-in-time index; safety is structural (chronological position + prefix caches) |
| `similarity` `recency` `confounders` `estimator` `matching` `controls` | statistical contracts |
| `evaluability.py` | the pre-OOS gate |
| `freshsample` `leakage` `engine` `golden` `bugledger` | sample, red team, scoring, corpus, defects |

**Results of the repair (diagnostic replay of V7, `DIAGNOSTIC_ONLY` / `NON_CONFIRMATORY`):**
132 canonical V6.1 families → 61 `STRUCTURALLY_INVALID` (named and refused *before* measurement),
20 `UNMEASURABLE`, **51 evaluable** where V7 could compute 16. Contrastless cells after repair: **0**.

**14 defects** (2×P0, 6×P1, 3×P2, 2×P3, 1×P4), zero P0–P3 unresolved. Each fix guards the *class*.
Headline ones: D1 the response schema had no cross-entity comparator token (fixed forward, never
retro-assigned); D7 per-fixture comparator collapse; D11 `RECENT_VS_LONG` whose baseline was not
long-run; D13 the W5/W10 truncation was skipped on the recency branch; D14 hand-maintained
blast-radius declarations drift from disk.

**Control B:** exact single-tier stratification on the whole covariate vector against a 200k
marginal pool. 46/51 matched, 9.8% unmatched, Kish ESS 428.1, worst |SMD| **0.000**,
`control_b_comparable = true`. Coarsening was measured and rejected (0.874 / 0.496 / 0.361 / 0.283).

**Fresh confirmatory sample:** 317 fixtures, 6 competitions, 122 teams, 3 chronological folds,
2026-08-08 → 2026-09-14, from TheStatsAPI 2026/27. **Zero overlap proved at fixture-identifier
level** against 5,319 development and 3,606 V7-confirmatory fixtures.

**Gate:** `V7_1_EVALUABILITY_GATE_PASSED`, all 7 checks; 8 clusters vs 4 required; smallest
detectable difference 0.032 against the frozen MDE of 0.05.

**Reproducibility:** 19 quantities × 4 seeds × 2 interpreters = 8 environments, 0 unstable.
**Leakage red team:** 18/18 mutation classes rejected, live negative control.
**Freeze:** 27 SHA-256 artifacts, `problems: []`, interpreter pinned to `/home/ubuntu/.venv/bin/python` 3.12.3.

**Tests:** `tests/research/` → 3260 passed, 1 failed; `tests/research/hypothesis_v71/` → 97 passed.
The single failure is **pre-existing**, reproduced on the unchanged baseline `4c663a737`, and is
V7's own blast-radius artifact (D14). V7 is immutable, so it is not repaired; the claim it failed
to cover is re-verified read-only and holds. Nothing was skipped or xfailed.

## Honest limitations

1. The fresh window is five weeks and supports only three folds (§L).
2. V7's own confirmatory window is unavoidably part of V7.1's development data — **history is
   shared; outcomes are not** (§N).
3. Structural family counts (16 / 51 / 71) were seen before the ≥4-of-6 coverage threshold was
   fixed; disclosed in `capability.COVERAGE_POLICY` (§J).
4. The 5 unmatched families are the tail of exact stratification, not a systematic hole (§K).

## To resume

```bash
cd /home/ubuntu && git checkout feat/v7-1-hardening
/home/ubuntu/.venv/bin/python -m pytest tests/research/hypothesis_v71/ -q      # 97 passed
/home/ubuntu/.venv/bin/python research/hypothesis_engine/_v71_execute.py       # dry run, computes nothing
```

Artifacts: `research/hypothesis_oos/out/v7_1/` (27 frozen files; `V7_1_FREEZE_MANIFEST.json` is
the index). Drivers: `research/hypothesis_engine/_v71_*.py` — `trace`, `diagnostic_replay`,
`fetch_fresh_oos`, `freeze`, `blast_radius`, `reproducibility`, `execute`.

**The one thing not to do casually.** `_v71_execute.py --authorize` is the confirmatory run.
It currently refuses by design: computing a confirmatory outcome was outside this mission's
authorization and requires a separate explicit one. Once it runs, V7.1 becomes live and immutable
and no further tuning is legitimate. Everything else in this repository can be re-run freely
because none of it touches the fresh outcomes.
