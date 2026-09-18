# V8C distinct blind control spec (`v8c_controls_v2`) — P1 R CONTROL / R PAIRING / H

## 1. Two defects, not one

**V8B.1** seeded the exclusion set only with controls already used at that fixture. Sonnet's
own id was never excluded, so `R_ID == S_ID` was permitted. Measured on the exposed 50 under
identical inputs: **5/5 identity collapse** — every paired fixture had R equal to S, so the
S-v-R difference was identically zero by construction.

**V8C v1** excluded only the *paired* Sonnet id. R could therefore return a **different**
hypothesis that Sonnet had also selected at the same fixture — still treatment, wearing a
control label.

## 2. The rule

R's exclusion set is seeded with **every Sonnet-selected id at that fixture**, plus every
control already used there. Both consequences are **asserted**, not reported:

```python
assert identity == 0                 # R is never its own pair's S
assert cross_treatment_overlap == 0  # R is never ANY S at this fixture
```

If the ordered relaxation is exhausted without a distinct candidate, the arm returns
`UNMATCHED_DISTINCT_CONTROL`. It never fabricates and never duplicates.

## 3. Nuisance dimensions

An unmatched nuisance dimension is a confound in the paired difference. V8B.1 matched six;
V8C matches nine, because the V8C grammar now varies `window` and condition shape:

| dimension | V8B.1 | V8C | relaxable? |
|---|:-:|:-:|---|
| `target_metric` | ✓ | ✓ | **never** |
| `subject` | ✓ | ✓ | **never** |
| `comparator` | ✓ | ✓ | **never** |
| `uses_similarity` | — | ✓ | **never** |
| `perspective` (FOR/AGAINST) | — | ✓ | last tier |
| `window` (ALL_PRIOR/W5/W10) | — | ✓ | tier 4 |
| `condition_family` | — | ✓ | tier 2 |
| `n_conditions` | ✓ | ✓ | tier 3 (±1) |
| `capability_status` | ✓ | ✓ | tier 5 |

`condition_family` is the order-independent set of condition **dimensions**
(`venue+opponent_profile`), not their values. Matching on the value would leave R almost no
candidates; matching on the shape controls the structural nuisance that matters.

The four never-relaxed dimensions define *what question is being asked*. Relaxing them would
make R a different question rather than a different answer.

## 4. Relaxation tiers

Each tier drops exactly **one** further constraint, cumulatively, so what was traded away to
obtain a match is always legible in the frozen record:

```
EXACT → CONDITION_FAMILY_ANY → CONDITIONS_PM1 → WINDOW_ANY
      → CAPABILITY_EITHER → PERSPECTIVE_EITHER → UNMATCHED
```

Within a tier, candidates are sorted by `hypothesis_id` and the first is taken — deterministic,
and independent of any support quantity, so the choice cannot encode measurability.

The tier is carried in the `(S_ID, R_ID, tier)` triple through freeze → scoring →
aggregation, because a reviewer will ask whether pairs matched at `PERSPECTIVE_EITHER` behave
like `EXACT` ones.

## 5. R is blind

R reads the structural shape and the exclusion set. It does **not** read Sonnet prose, the
mechanism summary, the research reason, any outcome, any observed effect, or any scorer
output. `SonnetShape` has no prose field at all — there is nothing to accidentally read.

## 6. Pairing survives to the estimand

```
d_i(T) = score(S_i, T) − score(R_i, T)      per surviving pair
D_R(T) = mean over surviving pairs at T
```

A pair drops when **either** side is non-OK — the **pair**, not the fixture. The previous rule
(`mean(all S SCORE_OK) − mean(all R SCORE_OK)`) could compare the mean of three surviving S
hypotheses against one surviving R hypothesis, which throws the matching away at the last step.

## 7. H is deliberately not pair-matched

H ranks the **frozen, unmodified** `heuristic_score` (imported byte-identically from
`hypothesis_v8b1.controls`, all five coefficients untouched) over the **entire**
`PRE_T_EVALUABLE` universe. V8B.1 ranked it over `search(max_results=50)` — the 50
structurally-lowest `ir_id`s — so "H's top pick" answered a different question from S's.

H is a **policy baseline** ("what would a fixed deterministic ranker pick?"), so S-v-H keeps
arm-mean semantics. **S-v-R and S-v-H are different estimands** and are labelled differently
everywhere (`S_vs_R (MATCHED-PAIR)`, `S_vs_H (ARM-MEAN)`) so they are never read as comparable.
