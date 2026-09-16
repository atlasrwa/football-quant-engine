# V8B — aborted pre-outcome. Missing evaluation primitive.

**Status: ABORTED. No target outcome was opened. No paid model call was made. No V8B artifact
beyond this report and the taint inventory below was created.**

## What was requested

V8B specified fixture-level paired scoring:

```
SONNET_SCORE(T) = aggregate quality of valid Sonnet selections at fixture T
BLIND_SCORE(T)  = aggregate quality of matched blind selections at fixture T
HEURISTIC_SCORE(T) = aggregate quality of heuristic selections at fixture T
D_BLIND(T) = SONNET_SCORE(T) - BLIND_SCORE(T)
D_HEUR(T)  = SONNET_SCORE(T) - HEURISTIC_SCORE(T)
```

with §42 requiring: *"Prefer an already-established OOS evaluation primitive if mathematically
appropriate. If existing V7/V7.1 quality machinery cannot validly score target-level selection:
STOP BEFORE OUTCOME EXPOSURE... Do not inspect outcomes and then invent one."*

## What was found

Read directly (not secondhand): `src/research/hypothesis_v71/estimator.py`, `engine.py`,
`execution.py`, `compiler.py`.

The existing scoring chain is:

1. `compiler.py::compile_query(ir, index, rec_i, ...)` — the only fixture-scoped primitive.
   Given one target position, returns raw `cohort_values`/`baseline_values`/weights for that
   fixture. **Data, not a score.**
2. `engine.py::evaluate_cell(ir, metric, index, positions, ...)` — takes a **list** of fixture
   positions (a whole fold), builds `sig[i] = cohort_i - baseline_i` and
   `res[i] = observed_i - baseline_i` across all of them, and computes
   `effect = pearson(sig, res)`. Hard floor: `MIN_CELL_OBSERVATIONS = 20`; below that,
   `effect: None` unconditionally. A single fixture gives one `(sig, res)` pair —
   `signal_variance` is exactly `0` by construction, and the function's own
   `if out["signal_variance"] <= 1e-18: out["contrastless"] = True; return out` guard would
   fire before any correlation was attempted even if the floor were bypassed. Pearson
   correlation over one point is mathematically undefined, not merely low-powered.
3. `engine.py::score_family(evidence)` — averages `mean_effect * direction_agreement` over
   folds and metrics into one `oos_quality_score` per canonical hypothesis **family**.
   `estimator.py`'s own docstring: *"One canonical family = one vote, whatever its origin
   multiplicity or how many fixtures it was evaluated over."*
4. `execution.py::aggregate_endpoints` — differences a treated family's score against a
   matched control's, per family pair, reduced further via
   `estimator.py::small_cluster_inference` over ~6-8 multiplicity-family clusters.

**No function anywhere in `estimator.py`, `engine.py`, `execution.py`, or `compiler.py` scores
one hypothesis at one target fixture.** The smallest scored unit is a fold-cell (≥20
fixtures); the smallest *reported* unit is a canonical hypothesis family (aggregated over all
folds). Building `score(hypothesis_ir, target_fixture) -> float` requires genuinely new
statistical design — which is what this document, and its successor `V8B1_SCORER_SPEC.md`,
exist to do openly, rather than inventing it silently after seeing outcomes.

## Decision

Per explicit instruction: **V8B as specified is aborted pre-outcome.** This state is preserved
as the scientific record of that attempt. **V8B.1** is created as the successor, with a new,
separately-designed and frozen fixture-level scoring primitive (`V8B1_SCORER_SPEC.md`)
completed and synthetically proven **before** any fixture manifest, search interface, evidence
packet, or control arm work resumes.

No code was changed. No CHAMPION file was touched. No model was called. This report and the
taint inventory it references are read-only forensic artifacts.
