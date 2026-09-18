# V8C fresh-pilot population rule (`v8c_pilot_rule_v1`) — P1-J

**PREREGISTERED. Frozen BEFORE any sealed-947 structural scan has been run.**
**No sealed-947 coverage characteristic has been inspected. `SEALED_947_PREFLIGHT_RUN = false`.**

This document exists so the pilot population cannot be chosen after seeing what the reserve
looks like. Everything below is decided from information already available: the frozen manifest,
the frozen support contract, and the frozen inference rule.

---

## 1. Pilot size N

```
N = 60
```

**Derived, not chosen for convenience.** It is the smallest N that satisfies all three frozen
constraints simultaneously:

| constraint | source | requirement |
|---|---|---|
| exact sign-flip needs ≥ 3 qualifying blocks | `estimator.SIGN_FLIP_MIN_CLUSTERS` | G ≥ 3 |
| a block qualifies on ≥ 5 **actual paired** differences | `aggregate.MIN_PAIRED_PER_BLOCK` | ≥ 5 per block |
| ⇒ paired fixtures needed | product of the two | **≥ 15 paired** |

The binding question is therefore *not* "how many fixtures" but "how many fixtures **survive to
a paired difference**". A fixture contributes a paired S-v-R difference only when at least one
`(S_i, R_i)` pair has **both** sides reach `SCORE_OK`.

The V8B.2 exposed-50 diagnostic is the only real-corpus attrition evidence that exists, and it
is development data: 4 paired fixtures from 50 selections, under a **defective** apparatus
(R collapsed onto S, no measurability control). It cannot be used as a rate estimate, and it is
not used as one here. What it does establish is that **paired survival is the scarce quantity**,
so N must carry slack above the 15-paired floor rather than sit on it.

`N = 60` gives a 4× margin over the 15-paired minimum. If paired survival is better than 25%,
the pilot exceeds the floor and yields more than 3 blocks; if it is worse, the pilot returns
`INSUFFICIENT_CLUSTERS_FOR_INFERENCE` — which is a **predeclared, interpretable outcome**, not a
failure to be repaired after the fact.

> N is frozen here. It may not be revised after the sealed-947 scan reports coverage.

## 2. Eligible-fixture definition

A sealed fixture is `PILOT_ELIGIBLE` iff **all** hold, using **pre-T structural information
only**:

```
pre_t_evaluable_candidates >= K_MIN        (K_MIN = 4)
AND distinct_R_feasible
AND H_feasible
AND live_search_addressable                (every evaluable candidate reachable in one call)
AND fixture is in the frozen 947 reserve   (not exposed-50, not a T2 canary)
```

`K_MIN = 4` is operational, from what one fixture structurally needs: S must have a genuine
*choice* (≥ 2), R must find a control distinct from every S pick (+1), H must *rank* rather than
restate S's pick (+1).

**No criterion reads a target outcome, an effect, a score, a direction or a p-value.**

## 3. Deterministic ordering

The frozen manifest's own chronological order:

```
sort by (kickoff_unix, fixture_id)      # fixture_id breaks exact-time ties
```

This is the ordering `V8B1_FIXTURE_MANIFEST.json` already carries. It is not re-derived, and it
is independent of any structural property — so the order cannot be influenced by coverage.

## 4. Selection rule

```
take the FIRST N fixtures, in the order of §3, that satisfy §2
```

First-N-in-chronological-order. Not sampled, not stratified, not balanced across competitions —
any of those would let a coverage characteristic influence which fixtures are chosen.

## 5. If fewer than N qualify

Predeclared, so the response cannot be improvised:

| qualifying | action |
|---|---|
| ≥ 60 | run the pilot on the first 60 |
| 15 – 59 | **STOP and report.** Do not run a smaller pilot without re-authorisation. A pilot below N was not the preregistered design, and shrinking it after seeing the count is exactly the choice this document exists to prevent. |
| < 15 | **STOP.** Below the paired-inference floor even under perfect survival. Report the design conflict. |

In no case is `K_MIN`, `N`, or the eligibility definition relaxed to reach a count.

## 6. Reporting

The sealed-947 scan reports, by competition and by chronological block: eligible count,
evaluable-universe distribution (p10/p50/p90), distinct-R feasibility, H feasibility, live
addressability, and the eligible/ineligible reason breakdown.

That report is **descriptive**. It is produced *after* this rule is frozen and cannot amend it.

## 7. Minimum structurally usable coverage required before spend

```
eligible_fixtures >= 60
AND every eligible fixture has live_search_addressable == true
AND the first 60 span >= 3 frozen inference blocks
```

The last condition is structural, not outcome-dependent: it asks whether the *selected cohort*
could in principle populate three blocks, given the frozen blocking rule. It says nothing about
how many will survive to a paired difference — that is the experiment's job to discover.
