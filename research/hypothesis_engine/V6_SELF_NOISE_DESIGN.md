# V6 — Self-Noise Design (§9, §22)

**Zero spend.** `v6_selfnoise` + `v6_repeatability`. The FORMULA is frozen now; the VALUE is measured in the run.

## 1. Why this is a first-class measurement

V5A.2 issued four **byte-identical** requests at temperature 0.0 (same `serialized_request_sha256`). The primary metric came back `6, 0, 7, 0`; re-scored under the V6 adjudicator the base-arm `qualified_rate` was `0.75, 0.00, 0.70, 0.00`, pooled within-cell **SD 0.363**. That is not measurement jitter — it is a bimodal generator. Temperature 0 is not determinism.

A generator with that spread can produce an Arm B − Arm A difference of several hypotheses from nothing. So the claim V6 can make is not "B > A" but "**B − A exceeds what the generator does to itself on identical input**".

## 2. What is measured within a repeat group (§9)

Six deterministic functions of the response, none reading prose:
- accepted/qualified count (the numeric floor)
- normalized hypothesis intent → Jaccard
- evidence references → Jaccard
- dimensions used → Jaccard
- comparison types → Jaccard
- compiler plans → Jaccard

`priority` is excluded (§23). Every set is serialized sorted (§30).

## 3. Coverage (§9 requires MULTIPLE fixtures in BOTH arms)

V5A.2 had **one** group per arm and correctly refused to rely on it. V6 schedules **4 repeat fixtures × 3 calls each, in both arms** — exceeding the floor of 3 groups/arm, leaving one group of slack. `v6_schedule.freeze_assertions` refuses to freeze a sequence that does not reach this.

## 4. The benchmark (§22) — at the level the claim is made

V5A.2's gate compared a ten-fixture mean against a single call's spread — two different aggregation levels, conservative for no evidential reason (it would return MIXED whatever the model did — §37's "underpowered by construction"). V6 benchmarks the paired mean difference against its **standard error** under the null that the arms differ only by generator self-noise:

```
Var(d_f)    = sd² · (1/r_f_base + 1/r_f_research)      per fixture
Var(mean d) = Σ_f Var(d_f) / F²
benchmark   = Z · sqrt(Var(mean d)),  Z = 1.645 (one-sided 5%)
```

`sd` is the pooled within-(fixture, arm) SD measured from V6's own repeat groups. `MIN_SELF_NOISE_SD = 0.05` stops an accidentally-clean repeat group manufacturing a PASS.

**Honesty:** this is a noise-exceedance criterion, not a distribution-guaranteed hypothesis test. Ten fixtures, a bimodal generator and a bounded statistic do not satisfy normality; calling it a p-value would overclaim.

## 5. Power sketch (frozen before spend, §25)

`power_sketch` states the minimum detectable paired difference in advance:

| assumed within-cell SD | min detectable paired B−A diff |
|---|---|
| 0.363 (V5A.2 observed) | **0.229** |
| 0.20 | ~0.126 |

At SD 0.363 the design declares PASS only for a mean paired difference above ~0.23 (23 percentage points on the qualified rate). A smaller true difference returns MIXED — the honest answer for a difference this design cannot separate from generator self-noise. If the run's own measured SD is lower, the bar drops accordingly. This is stated before any data exists, so no threshold is chosen after observing results.
