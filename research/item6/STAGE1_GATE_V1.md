# STAGE1_GATE_V1 — frozen pass/fail gate + threshold design report

`item6_stage1_gate_v1` · code: `src/research/item6/stage1_gate.py`

The HARD, preregistered PASS/FAIL gate for Stage 1. Thresholds are frozen BEFORE any live
generation and BEFORE any output is seen. They use the prior-corpus audit as a **historical
reference**, not as an outcome to optimize against, and require **materially better** generation
than the prior corpus — not merely non-zero novelty.

## PRIOR_CORPUS_REFERENCE_METRICS (researcher knowledge)

| quantity | prior value |
|---|---|
| semantic duplicate rate | ~0.80 |
| baseline-equivalent / mirror-like rate | ~0.51 (77/150 mirror; 46/150 one repeated concept) |
| novel hypothesis families | 0 |
| meaningful two-condition rate (V3) | ~0.009 (1/112) |
| multivariable interaction rate | ~0.009 |
| nonlinearities / thresholds | 0 |
| half-state / game-state constructions | 0 |

## NEW_FROZEN_GATE_THRESHOLDS

### PRIMARY (all must pass; these DETERMINE pass/fail)

| endpoint | threshold | direction |
|---|---|---|
| `BASELINE_EQUIVALENT_RATE` | ≤ 0.60 | lower better |
| `SEMANTIC_DUPLICATE_RATE` (mean within-fixture) | ≤ 0.50 | lower better |
| `NOVEL_MEASURABLE_FAMILY_RATE` (fixture-level) | ≥ 0.30 | higher better |
| `NEW_FAMILY_COUNT` (distinct, corpus-wide) | ≥ 3 | higher better |
| `MULTIVARIABLE_INTERACTION_RATE` | ≥ 0.20 | higher better |
| `FORMALIZATION_SURVIVAL_RATE` | ≥ 0.50 | higher better |

### DIAGNOSTIC (reported, NON-gating)

| endpoint | threshold |
|---|---|
| `GROUNDING_PASS_RATE` | ≥ 0.90 |
| `FALSIFIABILITY_PASS_RATE` | ≥ 0.80 |
| `ABSTENTION_RATE` | reported (high abstention is itself informative) |

## WHY_EACH_THRESHOLD_WAS_CHOSEN

- **BASELINE_EQUIVALENT_RATE ≤ 0.60.** The prior regime was mirror/single-condition dominated
  (~0.51 by the mirror-like measure, higher once the full corpus is scored). A generator still
  emitting a majority of baseline-equivalent ideas has not changed kind. 0.60 sits below a
  "mostly baseline" majority while allowing that a genuinely expansive generator will still emit
  *some* baseline ideas (which is honest, not penalized to zero).
- **SEMANTIC_DUPLICATE_RATE ≤ 0.50.** Prior ~0.80. This is measured as the **mean within-fixture
  duplicate rate** (scale-stable; see below), and 0.50 demands the generator not repeat itself in
  more than half of a fixture's K draws — a material drop from 0.80.
- **NOVEL_MEASURABLE_FAMILY_RATE ≥ 0.30 (fixture-level).** Prior 0. Requires ≥30% of
  non-abstaining fixtures to yield ≥1 novel measurable family. Fixture-level (not mechanism-level)
  so K correlated mechanisms in one fixture are not K independent successes.
- **NEW_FAMILY_COUNT ≥ 3.** Prior 0. Repeatable expansion means several distinct families
  corpus-wide, not one anecdote.
- **MULTIVARIABLE_INTERACTION_RATE ≥ 0.20.** Prior ~0.009. A ~20× floor over the prior rate.
- **FORMALIZATION_SURVIVAL_RATE ≥ 0.50.** Guards against "novelty that evaporates at
  formalization": at least half of non-baseline-equivalent grounded ideas must keep their value
  through deterministic formalization (land in F3/F4).

## WHICH ARE PRIMARY vs DIAGNOSTIC

Primary = the six listed under PRIMARY; **all** must pass for `STAGE1_PASS`. Diagnostic =
grounding, falsifiability, abstention — reported for interpretation, never gating (so a single
grounding lapse cannot cascade the whole verdict, the V3 D10/D11 fail-closed-on-N pathology).

## Handling within-fixture dependence

Each fixture yields K=5 correlated mechanisms. The primary novel-family endpoint is aggregated at
the **fixture** level (fraction of non-abstaining fixtures with ≥1 novel family). The duplicate
rate is the **mean within-fixture** rate. Neither treats K×fixtures as independent observations.

## Degrees of freedom disclosure

Thresholds were derived from the historical reference and frozen in code before any output is
seen. They are NOT set to `prior_value + epsilon`; they demand a regime change. No threshold may
be edited after freeze; the freeze manifest pins the gate file hash.
