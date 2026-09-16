# V8B.1 — fixture aggregation and inference spec (`v8b1_aggregation_v1`)

**Status: frozen design. Reuses `estimator.small_cluster_inference` unchanged. No real target
outcome has been opened while writing this spec.**

## 1. What this answers

Given per-fixture, per-hypothesis scores from `scorer_v8b1.score_fixture` (§ see
`V8B1_SCORER_SPEC.md`), how do ~1,000 fixtures' worth of Sonnet/blind/heuristic selections
become the three primary endpoints (§44-§47 of the V8B instructions, carried into V8B.1):
research yield, Sonnet vs matched blind, Sonnet vs heuristic — with fixture-level pairing and
robust, dependence-aware inference, reusing the strongest existing primitive rather than
inventing a new one.

## 2. Fixture-level score aggregation (within one fixture, across its selections)

For target fixture T, each arm (`SONNET`, `BLIND`, `HEURISTIC`) has a set of selected
canonical hypothesis IDs, each resolved to an `IR` and scored via `score_fixture(ir, T)`.

```
ARM_SCORE(T) = mean(score for score in {score_fixture(ir, T) for ir in arm's valid selections at T}
                    if status == SCORE_OK)
```

- Only `SCORE_OK` results enter the mean. `SCORE_REFUSED`/`SCORE_INSUFFICIENT_SUPPORT`/
  `SCORE_UNDEFINED` selections are excluded from `ARM_SCORE(T)` and recorded separately in the
  attrition ledger (§44's research-yield endpoint), never coerced to 0 (NULL-is-not-ZERO,
  unchanged from every other layer of this codebase).
- If an arm has **zero** `SCORE_OK` selections at T, `ARM_SCORE(T)` is `None` (not `0.0`), and
  fixture T contributes no paired difference for that arm at that fixture (§3).
- Equal-weight mean across an arm's own valid selections — the same
  `EQUAL_WEIGHT_MEAN_OVER_METRICS`/`EQUAL_WEIGHT_MEAN_OVER_HALFLIVES` convention `engine.py`
  already uses elsewhere in this codebase, not a new weighting scheme.

## 3. Fixture-level paired differences

Per instruction (§40, carried into V8B.1), the blind and heuristic control selections at T are
each built to size `K_valid(T)` = Sonnet's own valid-selection count at T (§8/§9 below), so
`ARM_SCORE` is never inflated or deflated purely by selecting more or fewer hypotheses.

```
D_BLIND(T) = SONNET_SCORE(T) - BLIND_SCORE(T)        # only where BOTH are not None
D_HEUR(T)  = SONNET_SCORE(T) - HEURISTIC_SCORE(T)    # only where BOTH are not None
```

A fixture where either side is `None` contributes to neither `D_BLIND` nor `D_HEUR` (it may
still contribute to the separate, unpaired research-yield endpoint). This is a listwise, not
pairwise, exclusion rule, stated once here rather than left implicit.

## 4. Clustering for robust inference

Reuses `src/research/hypothesis_v71/estimator.py::small_cluster_inference(values, clusters)`
**unchanged** — no new statistical machinery. What is new is only the choice of what plays the
role of "value" and "cluster":

- **`values`** = the list of fixture-level paired differences (`D_BLIND(T)` or `D_HEUR(T)`,
  computed separately — two independent calls to `small_cluster_inference`, one per endpoint).
- **`clusters`** = **chronological block**, not `MULTIPLICITY_FAMILY` (V7.1's own choice for
  its family-level endpoint). This is a deliberate, stated departure, not an oversight:
  - V8B.1's inferential unit is the FIXTURE, not the canonical hypothesis family — there is no
    "multiplicity family" a fixture belongs to; each fixture may contribute selections from
    several different mechanism families simultaneously.
  - §48 of the instructions explicitly names "chronological dependence" and "repeated teams"
    as the discipline to account for. Chronological blocking (e.g. calendar-month or
    fixed-count contiguous blocks in kickoff order) is the most direct way to make the cluster
    unit absorb both: fixtures close in time share season-state and, incidentally, are more
    likely to share teams than fixtures far apart.
  - The block size is fixed BEFORE selection freeze (§6 below) at a size chosen to produce at
    least `SIGN_FLIP_MIN_CLUSTERS = 3` blocks (the frozen minimum `estimator.py` itself already
    enforces) and, for a genuinely exact enumeration rather than the coarse few-cluster regime
    V7.1's Endpoint B was limited to, comfortably more — the block count is reported explicitly
    (§7) rather than tuned post-hoc to produce a particular p-value.
- **Secondary, descriptive-only clustering by competition** is also computed and reported
  (mirroring V7.1's own fold-vs-competition dual reporting, `_competition_agreement` in
  `engine.py`), never used to select a "better" clustering after seeing the result.

`small_cluster_inference` returns, unchanged: `primary_p_value` (exact enumerated sign-flip
when `n_clusters` is within `MAX_ENUMERATED_G=20`, else the same deterministic SHA-256-stream
fallback V7.1 already defines for larger G), `point_estimate`, `n_clusters`,
`clustered_se_descriptive_only` (reported, never the primary inferential quantity — unchanged
from V7.1's own explicit `normal_approx_p_is_not_used: true` policy).

## 5. Primary endpoints, restated precisely

**Endpoint 1 — research yield** (§44): for the Sonnet arm, the attrition funnel
`selected -> canonical -> compiler-valid -> measurable (score_fixture reaches SCORE_OK or a
named non-OK status, never an exception) -> support-qualified (SCORE_OK specifically)`,
reported exactly like V7.1's own Endpoint A funnel (`_yield_ladder` in `execution.py`), reused
in shape though computed over this experiment's own selections, not V7.1's frozen ones.

**Endpoint 2 — Sonnet vs matched blind** (§45): `small_cluster_inference(D_BLIND values,
chronological_block_clusters)`. Primary statistic is the returned `point_estimate` (mean
cluster-mean of `D_BLIND(T)`) and `primary_p_value`. Positive point estimate ⇒ Sonnet's
selections had, on average, more standardized squared-error improvement over baseline than
their structurally matched blind counterparts at the same fixtures.

**Endpoint 3 — Sonnet vs heuristic** (§46): identical construction, substituting `D_HEUR`.

Both endpoints 2 and 3 are fixture-level paired (§47), never per-hypothesis-independent — this
is enforced structurally by the fact that `D_BLIND(T)`/`D_HEUR(T)` are single numbers per
fixture, already aggregated across that fixture's own selections before any clustering or
inference step sees them. A fixture can never contribute more than one value to either
endpoint's `values` list, regardless of how many hypotheses any arm selected there.

## 6. What must be frozen before any fixture-level score touches a real outcome

- The chronological block size/boundaries (fixed function of fixture count and kickoff
  ordering, computed from the frozen fixture manifest alone — never from any score).
- The listwise-exclusion rule (§3) and the `SCORE_OK`-only aggregation rule (§2).
- The competition-block secondary clustering definition.

None of these can be adjusted after target outcomes are opened, per the no-mid-run-tuning
rule (§53 of the V8B instructions, carried into V8B.1).

### 6.1 Frozen values (actual, not illustrative)

Computed by `research/hypothesis_engine/_build_v8b1_chronological_blocks.py` over
`V8B1_FIXTURE_MANIFEST.json` (hash `932a72ca9c520f74...`), written to
`V8B1_CHRONOLOGICAL_BLOCKS.json` (hash `cef333918cfacd3a...`):

```
n_fixtures        = 1000
target_n_blocks   = 20     (chosen before any score existed, per the module's own docstring)
block_size        = 50     (contiguous, chronological-order, ceiling-divided)
n_blocks_actual   = 20
within_estimator_small_cluster_bounds = true   (3 <= 20 <= MAX_ENUMERATED_G=20)
```

20 clusters of 50 fixtures each gives `2^20` (≈1.05 million) sign vectors for the exact
enumerated sign-flip test — a materially finer reference distribution than V7.1's own
Endpoint B (6-8 clusters, 64-256 sign vectors), because the fixture-level design has far more
independent units available than V7.1's family-level design did.

## 7. Stability and diagnostics reporting (§49-§52), restated for this unit

Reported descriptively, never used to select a favorable reading of a null/negative overall
result (§49's own explicit rule, restated here so it is not lost in translation from the
family-level V7.1 language to the fixture-level V8B.1 language):

- overall (§5's two endpoints);
- by chronological block (the same blocks used for inference, so this is not a new cut);
- by competition (secondary, descriptive);
- by data-richness (e.g. cohort `cohort_n` quartile, available directly from `FixtureScore`);
- by home/away subject role;
- by mechanism family (the hypothesis's own `research_family`, carried from its IR);
- by similar-opponent usage vs not (`ir.cohort.similar_to_opponent is not None`);
- by attack×defense usage vs not (a structural property of which comparator/condition
  combination was selected, not an LLM self-report).

Research-quality diagnostics (§50-§52: simple-average-equivalence rate, model-use diagnostic,
etc.) are computed from the **research trace** and **selected IR shapes**, not from this
scoring/aggregation layer, and are specified separately alongside the research protocol.
