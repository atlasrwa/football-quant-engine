# V8B.1 — fixture-level scoring primitive (`v8b1_scorer_v1`)

**Status: frozen design, pending synthetic proof battery. Not yet used on any real target
outcome. No LLM numeric contribution enters this scorer anywhere.**

## 1. What this is for

V8B was aborted (`V8B_ABORT_REPORT.md`) because no existing V7/V7.1 primitive scores one
hypothesis at one target fixture — the smallest existing unit is a fold-cell (≥20 fixtures).
This document defines a new, minimal primitive, implemented at
`src/research/hypothesis_v8b1/scorer.py` — in its own package, deliberately kept OUT of
`src/research/hypothesis_v71/`, because that package is frozen scope belonging to V7.1's own
sealed confirmatory-run provenance chain (`V7_1_BLAST_RADIUS.json` and siblings); adding a
module there would either force an edit to a frozen post-hoc artifact or fail
`test_15_blast_radius_declares_every_v71_module_on_disk` by design (confirmed: it does, and
that failure is correct — it is the exact defect class, D14, that test exists to catch). The
new primitive calls into `hypothesis_v71`'s existing code but does not live inside it, so it:

- reuses the compiler's existing pre-T cohort/baseline estimates exactly as `engine.py`
  already computes them (same shrinkage, same PIT discipline, same recency family) — nothing
  about *how the estimate is built* is new;
- adds only what is genuinely missing: turning one fixture's `(cohort_estimate,
  baseline_estimate, observed)` triple into a standardized improvement number;
- is built and unit-tested entirely on synthetic/constructed data, never tuned against any
  real target outcome in this corpus, per instruction.

## 2. What already exists and is reused unchanged

From `src/research/hypothesis_v71/compiler.py::compile_query`:
- `cohort_values`, `cohort_weights`, `cohort_n`
- `baseline_values`, `baseline_weights`, `baseline_n`
- `environment_mean`
- `observed` — the target fixture's own value for the metric (only opened after selection
  freeze, per §7/§37/§41 of the V8B instructions, carried forward unchanged into V8B.1)
- Degeneracy detection (`CompiledQuery.is_degenerate()`), reused as-is.

From `src/research/hypothesis_v71/recency.py` / `src/research/hypothesis_v7/pit.py`:
- `Recency.shrink(mean, n, prior_mean)` → `shrink_estimate(mean, n, prior_mean, k=10.0)`,
  James-Stein-style partial pooling toward `environment_mean`. This is the SAME shrinkage
  `engine.py::_estimates` already applies to both the cohort and the baseline mean before
  computing `sig = cohort_estimate - baseline_estimate`. V8B.1 calls exactly this function,
  not a re-derivation of it.
- The frozen decay family (`HALFLIVES_DAYS = (180, 365)`) and `UniformRecency` — reused
  unchanged; a TIME_DECAY cohort is still averaged across both frozen half-lives, never one
  chosen.

From `src/research/hypothesis_v7/pit.py`:
- `classify_support(...)` and its frozen thresholds (`MIN_RAW_N=20`, `MIN_UNIQUE_FIXTURES=15`,
  `MIN_UNIQUE_TEAMS=6`, `MIN_EFFECTIVE_N=10.0`, `MAX_WEIGHT_CONCENTRATION=0.25`) — reused
  unchanged as the pre-score support gate. A cohort/baseline that would fail this gate at
  fold-level fails it identically here, at fixture-level, before a score is computed.

## 3. What is new: the fixture-level score

### 3.1 Point estimates (identical construction to `engine.py::_estimates`)

For a validated `IR` at target position `rec_i`, for each recency weighting `w` in the IR's
recency family (one member for `UNIFORM`, both frozen half-lives for `TIME_DECAY`, averaged —
unchanged from `engine.py::recency_family_for`):

```
c_mean = weighted_mean(cohort_values, cohort_weights)
b_mean = weighted_mean(baseline_values, baseline_weights)
c_hat  = w.shrink(c_mean, cohort_n, environment_mean)      # shrunk cohort estimate
b_hat  = w.shrink(b_mean, baseline_n, environment_mean)     # shrunk baseline estimate
```
averaged over the weighting family exactly as `_estimates` already does. `c_hat`/`b_hat` are
therefore byte-identical to what V7.1 would compute for the same `(ir, rec_i)` inside a fold —
no new estimation logic exists at this step.

### 3.2 The scale: pre-T cohort dispersion (genuinely new, but not tunable)

"Standardized" requires a scale. The scale must be constructed **only from information
strictly before T** — it may not use the target observation, and it may not be searched or
fit to make any hypothesis look better. The scale chosen is the cohort's own PIT-safe weighted
sample variance around its (unshrunk) mean:

```
scale_var = weighted_variance(cohort_values, cohort_weights)   # >= 0 by construction
scale = sqrt(scale_var)
```

This is the natural analogue of `evaluate_cell`'s `signal_variance` guard, computed from the
SAME `cohort_values`/`cohort_weights` `compile_query` already returns — no new data source, no
new hyperparameter, and it is exactly the quantity `evaluate_cell` already inspects
(`signal_variance <= 1e-18 -> contrastless`) to decide whether a fold-cell has any spread to
speak of. Reusing it here for degenerate-case detection keeps the two units reconcilable: a
family that would be `contrastless` at fold level is `SCORE_UNDEFINED` at fixture level for
the same underlying reason (near-zero cohort dispersion), not a different one.

**Why not the baseline's variance, or the pooled fold variance from `engine.py`:** the baseline
is by construction the less-restricted, larger-N selector (see `ontology.py`'s
`COMPARATOR_BINDINGS`), so its variance is a property of the whole population, not of what the
cohort claims to isolate. The fold-pooled `signal_variance` cannot be used because it requires
a fold's worth of fixtures — exactly the primitive this document exists to avoid depending on.
The cohort's own dispersion is available at single-fixture granularity because `compile_query`
already computes it for any one `rec_i`, without requiring any other fixture in a fold.

### 3.3 Standardized squared-error improvement

```
baseline_sq_error  = (observed - b_hat) ** 2
cohort_sq_error    = (observed - c_hat) ** 2
raw_improvement    = baseline_sq_error - cohort_sq_error     # positive = cohort estimate closer to T
score(T)           = raw_improvement / scale_var             # standardized by pre-T cohort variance
```

**Sign convention, stated explicitly (per instruction, since the direction must not be
assumed): higher `score(T)` is better**, consistent with `OOS_QUALITY_SCORE`'s existing
convention (`endpoints.py`: *"higher magnitude in the correct... direction"* framing; positive
`OOS_QUALITY_SCORE_DIFFERENCE` already means "LLM arm outperformed its control" in the V7.1
report). A positive `score(T)` means the hypothesis's conditional (cohort) estimate was closer
to the actual target observation than the unconditional baseline estimate was, in units of the
cohort's own pre-T variance. A score of exactly 0 means no improvement. A negative score means
the conditional estimate was *further* from the observation than the baseline — i.e. the
selected condition made the estimate worse, not better, at this fixture.

This is a direct, minimal generalization of `evaluate_cell`'s `sig`/`res` construction
(`sig = cohort - baseline`, `res = observed - baseline`) down to a single fixture: where
`evaluate_cell` correlates `sig` against `res` across many fixtures to see if the cohort's
deviation from baseline *tracks* the observation's deviation from baseline, this primitive
asks the fixture-local question that correlation cannot ask at n=1: *did substituting the
cohort estimate for the baseline estimate reduce squared error at this specific fixture,
relative to how much the cohort's own history varies?*

### 3.4 Degenerate cases — fail closed, never fabricate

| Condition | Result |
|---|---|
| `compile_query`'s own pre-fold-loop `assert_valid` raises `InvariantViolation` (e.g. `IDENTICAL_COHORT_BASELINE`/`SELF_COMPARISON` — this is how `SUBJECT_OVERALL_BASELINE` with zero conditions actually fails, confirmed against the real corpus in the proof battery, not merely assumed) | `SCORE_REFUSED` |
| `CompiledQuery.is_degenerate()` (cohort ≡ baseline, for a query that reaches construction) | `SCORE_REFUSED` — reused from the compiler's own check, unchanged |
| `compile_query` raises `CompileRefused` or `SimilarityRefused` | `SCORE_REFUSED` |
| `classify_support(...)` on the cohort is not `SUPPORT_ADEQUATE` | `SCORE_INSUFFICIENT_SUPPORT` — reused thresholds, unchanged |
| `scale_var <= 1e-18` (cohort has no dispersion — same floor `evaluate_cell` uses) | `SCORE_UNDEFINED` (analogous to `contrastless`) |
| `observed is None` or `environment_mean is None` | `SCORE_REFUSED` (same as `_estimates`'s existing raise) |

No degenerate case is silently coerced to `0.0`. `None`/a named refusal status is always
distinguishable from a genuine `score(T) = 0.0` (a real, computed zero improvement), mirroring
the NULL-is-not-ZERO discipline already enforced everywhere else in this codebase
(`confounders.py` D15, `corpus_index.py`'s `_read`).

### 3.5 What this scorer explicitly does NOT do

- It does not touch, read, or derive from any LLM numeric output. The LLM selects a
  **canonical hypothesis ID**; the scorer resolves that ID to an `IR` via the existing frozen
  `ir.build_ir`/lookup machinery and scores it exactly as it would score any other canonical
  ID, including one selected by the blind or heuristic control arms. The LLM's prose
  (`research_reason`, `mechanism_summary`, etc.) never enters this function.
- It does not re-fit, re-tune, or re-derive shrinkage strength, decay half-lives, or support
  thresholds. Every constant it uses (`k=10.0`, `HALFLIVES_DAYS`, `MIN_RAW_N`, etc.) is
  imported unchanged from `pit.py`/`recency.py`.
- It is not calibrated, adjusted, or selected against any real target fixture's outcome in
  this corpus. Section 4 (synthetic proof battery) is the only place real numbers are checked
  against expected behavior, and those numbers are constructed, not drawn from the corpus.
- It does not replace or modify `engine.py::evaluate_cell`/`score_family`/`OOS_QUALITY_SCORE`.
  Those remain exactly as frozen for any future family-level V7.1 work. This is an
  **additional, separate** primitive, versioned independently (`v8b1_scorer_v1`).

## 4. Synthetic proof battery (required before any real target outcome is scored)

Constructed cases, not real corpus fixtures, with known expected sign/magnitude:

1. **Perfect cohort, uninformative baseline**: construct a synthetic cohort/baseline/observed
   triple where `c_hat == observed` exactly and `b_hat` is far from `observed`. Expect
   `score(T) >> 0`.
2. **Cohort no better than baseline**: `c_hat == b_hat`. Expect `score(T) == 0` exactly
   (both squared errors identical, `raw_improvement == 0`).
3. **Cohort actively worse**: `|observed - c_hat| > |observed - b_hat|`. Expect `score(T) < 0`.
4. **Zero cohort dispersion** (all `cohort_values` identical): expect `SCORE_UNDEFINED`, never
   a division by zero exception and never a silent `0.0`.
5. **Degenerate cohort==baseline selector** (reuse an existing `IDENTICAL_COHORT_BASELINE`
   fixture from the compiler forensics already run in the prior audit): expect
   `SCORE_REFUSED`, matching the compiler's own `CompileRefused`.
6. **Scale invariance check**: multiply all synthetic values by a constant `> 0`; `score(T)`
   must be unchanged (this is what "standardized" is for — the primitive must not be sensitive
   to the metric's raw units, e.g. shots vs. possession percentage).
7. **Weighting-family averaging check**: a `TIME_DECAY` cohort must average its score
   construction across both frozen half-lives exactly as `_estimates` does for the point
   estimate — verified by comparing against a hand-computed two-halflife average on synthetic
   data.

All seven must pass before this scorer touches any cached corpus fixture's real observation.

## 5. Reconciliation statement (required by instruction)

This primitive is **not** a substitute for `OOS_QUALITY_SCORE`. It answers a different,
narrower question — "did this one conditional estimate beat its baseline at this one fixture,
in pre-T-standardized units" — that V7.1's family/fold-level score structurally cannot answer.
It shares every reusable building block with V7.1 (compiler, shrinkage, recency, support
thresholds) so that a reader can trace every number back to code that was already audited, and
it introduces exactly one new formula (§3.3), stated in full, with its sign convention named
explicitly rather than assumed.
