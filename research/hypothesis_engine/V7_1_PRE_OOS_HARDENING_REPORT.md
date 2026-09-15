# V7.1 — Pre-OOS Hardening Report

## A. Executive state

# `V7_1_READY_FOR_CONFIRMATORY_OOS`

| | |
|---|---|
| defects found | **14** — 2×P0, 6×P1, 3×P2, 2×P3, 1×P4. **Zero P0–P3 unresolved.** |
| treated universe | 132 canonical V6.1 families → 61 `STRUCTURALLY_INVALID` (named, refused *before* measurement), 20 `UNMEASURABLE`, **51 evaluable** |
| Endpoint B | 46/51 matched, 9.8% unmatched, ESS **428.1**, worst \|SMD\| **0.000**, `control_b_comparable = true` |
| fresh confirmatory sample | **317 fixtures**, 6 competitions, 122 teams, 3 chronological folds, 2026-08-08 → 2026-09-14 |
| zero overlap | proved at **fixture-identifier** level against 5,319 development and 3,606 V7-confirmatory fixtures — both empty intersections |
| evaluability gate | **PASSED**, all 7 checks; 8 clusters against 4 required; smallest detectable difference **0.032** at the frozen MDE of 0.05 |
| reproducibility | 19 quantities × 4 seeds × 2 interpreters = 8 environments, **0 unstable** |
| leakage red team | 18/18 mutation classes rejected, legitimate observation accepted, three-way empirical probe with a live negative control |
| frozen artifacts | **27**, SHA-256, `problems: []` |
| CHAMPION | `0b8f5ff3dc4ddf15…` unchanged |
| authorization | `CONFIRMATORY_OOS_COMPUTED = false`, `CONFIRMATORY_OOS_VIEWED = false` |

The standard of completion, stated as a claim I am willing to defend: *we have traced the
LLM-to-measurement semantics, eliminated the known structural failure modes, created generic
invariants against their recurrence, hardened the provider, PIT, similarity and statistical
contracts, built fair controls, proven sufficient pre-OOS evaluability, frozen a genuinely
untouched confirmatory sample, demonstrated reproducibility, preserved CHAMPION, committed the
complete apparatus, and can now run V7.1 without knowing its result.*

Two honest limitations sit against that, both stated in full below: the fresh window is five
weeks and supports three folds (§L), and V7's own confirmatory window is unavoidably part of
V7.1's development data (§N).

---

## B. V7 preservation

V7 is finished and immutable. Its apparatus, evidence and report existed only as untracked
files in the working tree at the start of this mission; they are now committed.

| | |
|---|---|
| lineage preservation commit | `f4817fff3` — V3–V6.1 source, tests and immutable execution evidence (533 files) |
| V7 freeze commit | `4c663a737` — V7 apparatus, 45 evidence artifacts, 3 reports (63 files) |
| successor branch | `feat/v7-1-hardening`, branched from the V7 freeze commit |

Preserved verbatim, and re-verified on every freeze:

```
EXECUTION_STATUS        = COMPLETE
APPARATUS_STATUS        = INTACT
SCIENTIFIC_EVALUABILITY = SEVERELY_LIMITED
Endpoint A              = LLM 5.3% vs uniform null 19.4%
Endpoint B              = -0.007536052743368488, clustered p = 0.3910801834229277
CHAMPION                = 0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9
DETERMINISM             = 10/10 evidence artifacts byte-identical
```

`V7_1_V7_IMMUTABILITY_PROOF.json` recomputes all 26 declared V7 artifact hashes and the
CHAMPION digest at freeze time. Nothing in `src/research/hypothesis_v7/`,
`research/hypothesis_oos/out/v7/` or `V7_CONFIRMATORY_OOS_REPORT.md` was modified. The V7
comparator defect remains a **historical apparatus finding**, deliberately unpatched there.

Every V7.1 diagnostic output is stamped `DIAGNOSTIC_ONLY` / `NON_CONFIRMATORY` /
`OUTCOME_ALREADY_VIEWED`.

---

## C. Defects discovered

Fourteen defects, classified per section 24. Full detail in `V7_1_BUG_LEDGER.json`; every fix
guards the **class**, not the instance.

| id | sev | defect | changes V7's interpretation? | generic fix |
|---|---|---|---|---|
| D1 | **P0** | The response schema had no token for a cross-entity comparison. "Does AWAY_TEAM concede more than HOME_TEAM concedes" is subject-vs-opponent; the enum offered only subject-relative comparators, so the model chose the nearest token and left the question in prose. 103/432 raw, 44/132 canonical. | No. The number stands; it reframes *why* — a schema-expressiveness limit, not a football judgement. | `SUBJECT_VS_FIXTURE_OPPONENT` added to the ontology for future generation. **Not** retro-assigned: the affected families fail closed. |
| D2 | P1 | The compiler implemented two of nine declared comparator semantics; the other seven fell through to one generic subject-vs-subject contrast. **Latent** in V7 — V6.1's own qualification filter removed all 93 `LEAGUE_ENVIRONMENT_BASELINE` hypotheses, so the path was never taken. | No. | A comparator is no longer a label: each binds an explicit `(cohort, baseline)` selector pair the compiler executes. An unbound comparator fails closed. |
| D3 | P1 | `value: ANY` and unsupported dimensions counted toward `len(conditions)`, so a degenerate hypothesis carrying one bypassed the degeneracy fast path. 25 raw hypotheses. | Marginally — V7's `TAUTOLOGICAL` count understated degeneracy and `UNMEASURABLE` overstated the data problem. | `NON_RESTRICTIVE_VALUES` frozen; degeneracy is judged on **restrictions**, never on list length. |
| D4 | P1 | An unimplemented condition dimension compiled to an **empty cohort**, indistinguishable downstream from genuine no-support. A capability gap was recorded as a data problem. 84 raw hypotheses. | Re-labels part of the attrition. | `UNSUPPORTED_FILTER_DIMENSION` names the dimension and fails closed; a filter that reaches the compiler is guaranteed executable. |
| D5 | P2 | The coverage gate demanded all six competitions while declaring `restricted_universes_reported: true` and never honouring it. xG is ≥0.99 in four of six and was discarded outright. | No — V7's gate was frozen and applied as frozen. It explains much of V7's low evaluability. | Restricted universes admitted at ≥4 of 6, the admissible set frozen and reported, and `n_admissible_competitions` added as a matching covariate so the control arm inherits the same opportunity. |
| D6 | P1 | A venue column constant by construction made the adjustment singular; V7 patched it mid-flight. | No — fixed on the development window before any confirmatory effect. | `screen_design` drops constant and collinear columns under **named reasons** carried into the evidence; unavailable and mediator variables are stripped from the plan with their own reasons. |
| D7 | **P0** | A structurally invalid query produced a zero-valued feature and ran a full walk-forward before being classified `TAUTOLOGICAL`. | No — the terminal state was right, reached far too late. | `assert_valid` **raises** before the fold loop; and a comparator that collapses at one fixture (`cohort_fixtures == baseline_fixtures`) triggers `CompileRefused` there, so no structural zero enters a distribution. |
| D8 | P2 | A similarity profile missing more than the frozen allowance was imputed to the cohort mean rather than excluded, making data-poor teams look artificially average. Latent in V7. | No. | `MAX_MISSING_DIMS` enforced on target and candidates; the engine **refuses** rather than returning a cohort built from imputations. |
| D9 | P3 | The whole V7 apparatus and 32 MB of immutable evidence were never committed. | No. | Two preservation commits before successor work; the immutability proof re-runs on every freeze. |
| D10 | P4 | V7's first similarity spec published a shrinkage constant the code never applied. V7 fixed the instance; the class had no guard. | No. | Specs are generated **from** the modules that implement them and hashed into the freeze manifest, so a published constant no code reads cannot drift undetected. |
| D11 | P1 | **Introduced and fixed inside this mission.** V7.1's first ontology bound *both* selectors of `SUBJECT_RECENT_VS_LONG_BASELINE` to the hypothesis' own window, so a W5 hypothesis compared a decayed five-match cohort against an **un-decayed five-match baseline** — where the two weightings barely differ, so the contrast collapses toward zero by construction. | No — V7 never had this binding. | The baseline is pinned to `ALL_PRIOR`, as the comparator's name and V7's frozen definition ("subject long-run un-decayed PIT baseline") both say. A golden round-trip case asserts the reconstruction contrasts a windowed cohort against the whole prior history. |
| D12 | P1 | **Introduced and fixed inside this mission.** `BASELINE_ABSORPTION` fired on reweighting comparators, whose selectors legitimately share their filters because the contrast is carried by the weighting. Every venue-conditioned recency hypothesis was rejected. | No. | Absorption is only considered when both selectors share a weighting; a reweighting pair is judged on its weighting difference alone. The real-absorption negative control still fires. |
| D13 | P2 | V7's executor applied the W5/W10 truncation only on its non-recency branch, so **every** recency hypothesis decayed over the team's whole prior history regardless of the window it declared. W5 and W10 recency families were the same query. | Mildly — V7's recency survivors are all-prior decay contrasts, not the W5/W10 contrasts their specs declared. The measured effect is real; the label is wrong. | The window is part of the `Selector`, so it applies wherever the binding says. W5, W10 and ALL_PRIOR recency now compile to three different queries and three different IR identities. |
| D14 | P3 | Blast-radius declarations were hand-maintained and drifted from disk. V7's artifact omitted `hypothesis_v7/measurement.py`, so its "no pre-existing test reaches changed code" claim was never checked for that module; V7.1's own first driver had already drifted by two modules. | No. V7 is not patched; the uncovered claim is re-verified read-only and holds. | The changed set is **derived from the package directory**, never declared, and two tests fail if the published artifact ever disagrees with disk. |

No P0–P3 defect is carried into V7.1.

D11–D13 were found by the diagnostic replay in the way section 17 intends: by comparing the
**compiled semantics** against the frozen comparator definition, not by chasing an effect. The
tell was structural — a comparator named RECENT_VS_LONG whose baseline was not long-run. Each
fix is justified by that comparison alone and would stand if the effect had moved the other
way.

### The defect, shown end to end

The trace of V6.1 hypothesis `H002`:

```
stated question   Does AWAY_TEAM concede a substantially higher volume of shots, shots on
                  target, and touches in the box per match than HOME_TEAM concedes ...?
structured fields subject=AWAY_TEAM  side=AGAINST  comparison=SUBJECT_OVERALL_BASELINE
                  conditions=[]      window=ALL_PRIOR
reconstructed     For shots, shots_on_target, touches_in_penalty_area: does the subject's
                  concession, over all prior matches differ from the subject's concession,
                  over all prior matches?
invariants        IDENTICAL_COHORT_BASELINE, SELF_COMPARISON
verdict           deterministic_query_tests_the_stated_question = FALSE
```

The question is cross-entity; every structural field that could have carried that is absent.
V7 measured it as subject-vs-itself and got exactly zero. V7.1 refuses it by name.

---

## D. Semantic intermediate representation

`src/research/hypothesis_v71/ir.py`, built from structural fields plus the frozen ontology —
never prose, never an LLM, never an outcome.

An IR is a target metric set, a subject role, a perspective, and **two fully specified
selectors**. A `Selector` is `(entity_role, perspective, filters, window, weighting,
complement, similar_to_opponent)`. Structural equality of the two selectors *is* the
degeneracy test.

Represented: subject; opponent role; target metric; FOR/AGAINST perspective; cohort selector;
baseline selector; conditions; venue; competition; temporal horizon; recent-vs-long context;
half/match-state requirement; similarity dimensions, target and source; provider requirements;
required temporal resolution; aggregation; interaction through conditioning; confounder family;
and an explicit abstention reason.

Fail-closed statuses: `SEMANTICALLY_AMBIGUOUS`, `UNSUPPORTED_FILTER_DIMENSION`,
`UNKNOWN_COMPARATOR`, `INVALID_ROLE_BINDING`, `MISSING_REQUIRED_CONDITION`,
`MISSING_REQUIRED_SIMILARITY`, `UNSUPPORTED_TEMPORAL_RESOLUTION`.

Round trip, on the question V6.1 could not express:

```python
{"subject": "HOME_TEAM", "side": "AGAINST", "comparison": "SUBJECT_VS_FIXTURE_OPPONENT",
 "target_metrics": ["total_shots"], "conditions": [], "window": "ALL_PRIOR"}
→ "For shots: does the subject's concession, over all prior matches differ from
   the fixture opponent's concession, over all prior matches?"
```

and on a genuine conditional:

```python
conditions=[{"dimension": "opponent_profile", "axis": "possession_for", "value": "HIGH"}]
→ "... does the subject's concession, over all prior matches, restricted to matches where
   the opponent was in the HIGH tercile of possession_for differ from the subject's
   concession, over all prior matches?"
```

---

## E. Comparator and compiler integrity

Ten comparators, each bound to an explicit selector pair and each **executed**:
`SUBJECT_OVERALL_BASELINE`, `SUBJECT_VENUE_BASELINE`, `SUBJECT_COMPETITION_BASELINE`,
`SUBJECT_RECENT_VS_LONG_BASELINE`, `OPPONENT_OVERALL_BASELINE`, `OPPONENT_VENUE_BASELINE`,
`LEAGUE_ENVIRONMENT_BASELINE`, `SIMILAR_OPPONENT_COHORT`, `SUBJECT_CONDITIONAL_VS_BASELINE`,
`SUBJECT_VS_FIXTURE_OPPONENT`.

Invariants rejected before any measurement: `IDENTICAL_COHORT_BASELINE`, `SELF_COMPARISON`,
`EMPTY_COMPARATOR`, `BASELINE_ABSORPTION`, `TAUTOLOGICAL_CONDITION`, `DUPLICATED_CONDITION`,
`NO_EFFECTIVE_RESTRICTION`, `INVALID_ROLE_BINDING`, `UNSUPPORTED_METRIC`,
`INSUFFICIENT_PROVIDER_COVERAGE`, `TEMPORAL_RESOLUTION_UNSUPPORTED`,
`UNKNOWN_PROVIDER_SEMANTICS`, `SIMILARITY_WITHOUT_DIMENSIONS`, plus the IR statuses above.

**V6.1's 132 canonical families under the hardened semantics:**

| terminal structural state | n |
|---|---|
| `STRUCTURALLY_INVALID` | 63 |
| — of which `IDENTICAL_COHORT_BASELINE` / `SELF_COMPARISON` | 44 |
| — of which `BASELINE_ABSORPTION` | 19 |
| `UNMEASURABLE` (capability) | 20 |
| structurally valid **and** measurable | **49** |

Against V7's own accounting: V7 reached 53 measurable and 16 with a computable estimate. V7.1
names 63 families as structurally invalid *before measuring them*, and lifts 56 families from
`UNMEASURABLE` to a reported restricted universe. The net evaluable set is **49** — roughly
three times V7's 16, and every one of them has a contrast that exists.

---

## F. Provider capability matrix

One provider, `thestatsapi`. `base` / `rich` / `extra` are **storage blocks of that one
provider**, never provenance; `assert_block_is_not_provider` and a permanent regression test
hold the line. The `DO_NOT_MERGE` registry (xg corr 0.55, total_shots corr 0.80 across
providers) stays armed and does not fire on a single-provider corpus.

Statuses are four, not two: `SUPPORTED` (all six competitions), `RESTRICTED` (≥4 of 6, the
admissible set frozen and reported), `INSUFFICIENT_COVERAGE`, `UNSUPPORTED` (contract), and
`UNKNOWN` — **unknown is not unsupported**, and NULL is not zero.

| metric | status | admissible competitions |
|---|---|---|
| `shots`, `goals`, `corner_kicks`, `shots_on_target`, … | `SUPPORTED` | all six |
| `xg` | `RESTRICTED` | champ, epl, laliga, ligue1 (ligue2 0.000, laliga2 0.452) |
| `touches_in_penalty_area` | `RESTRICTED` | epl, laliga, laliga2, ligue1, ligue2 (champ 0.673) |
| `offsides` | `RESTRICTED` | champ, laliga, laliga2, ligue2 |
| `np_xg` | `UNSUPPORTED` | per-side semantics unaudited |
| `cards` | `UNSUPPORTED` | ambiguous (yellow vs total) |
| anything uncontracted | `UNKNOWN` | — a named gap |

### The restricted-universe threshold, and a disclosure

`MIN_ADMISSIBLE_COMPETITIONS = 4` is justified structurally, not numerically: a restricted
universe must remain a **strict majority** of the corpus's six competitions; four of six
necessarily spans ≥2 countries and ≥2 division tiers, which three of six does not guarantee;
and retaining ≥⅔ of competitions keeps per-fold support in the same order of magnitude as a
full-coverage family.

**Disclosure.** The structural consequence of the threshold — how many canonical families it
admits — was computed on the already-viewed V7 universe *before* the threshold was fixed
(16 at six competitions, 51 at ≥4, 71 at ≥3). That quantity contains no effect, direction or
p-value, but the ordering is recorded here rather than hidden, because a reader is entitled to
weigh it. The rationale above stands without it.

### Capability envelope (section 10)

`V7_1_CAPABILITY_MATRIX.json` is the machine-readable envelope a **future** generator may be
shown: semantics, units, perspectives, temporal resolution and per-competition admissibility.
It contains no OOS outcome and no effect estimate, so exposing it cannot leak results into
generation. V7.1 does **not** regenerate V6.1's hypotheses with it — that would change the
treatment universe to improve measurability. The frozen V6.1 set remains the treatment arm and
is classified honestly under the hardened contract.

---

## G. Similarity integrity

The frozen V7 spec is reused verbatim — dimensions, z-scaling, profile shrinkage `k = 8.0`,
euclidean-z distance, `k = 8` neighbours, `MIN_PROFILE_HISTORY_MATCHES = 6`, frozen tie-break,
same-competition restriction. xG is absent from the dimension set by measured coverage.

What V7.1 adds is the operational half V7 never had: `SimilarityEngine.similar_opponent_ids`
rebuilds every profile, the competition baseline and the z-scale fit **from the prior frontier
of each target fixture**, caches them by `(competition, reference position)` so a cache hit
cannot serve a later-built profile, and asserts PIT on every observation. `MAX_MISSING_DIMS`
is now enforced: a target profile or candidate exceeding it causes a **refusal**, not an
imputation (D8). The LLM never produces a similarity score.

---

## H. Recency and shrinkage

```
half-lives              180 d, 365 d   — a preregistered FAMILY, never a searched grid
aggregation             equal-weight mean over half-lives; neither is ever selected
shrinkage prior         TEAM_COMPETITION_BASELINE, k = 10.0
windows                 W5/W10 are shrunk like any other cohort — never treated as truth
cross-season            prior seasons contribute through decay ALONE; none excluded
regime variables        manager, formation, lineup: UNAVAILABLE, declared not approximated
hyperparameters         constants, so nothing is fitted; `assert_not_fitted` is checkable
```

A PIT guard on `weight()` raises for any observation not strictly prior. The engine evaluates
a reweighting cohort at **every** frozen half-life and averages — a regression test asserts
that averaging the family differs from picking one member, so the contract cannot silently
degrade into a chosen window.

---

## I. Confounders

The frozen per-family plan is reused from V7. Variables the corpus cannot supply
(`score_state`, `formation`) are **declared unavailable**, not approximated. `score_state` is
additionally on the `NEVER_ADJUST` list: running score is a consequence of the process under
test, so conditioning on it would absorb the effect.

Before every solve, `screen_design` drops `DROPPED_CONSTANT_COLUMN` and
`DROPPED_COLLINEAR_COLUMN` under named reasons that are carried into the evidence. The V7
constant-venue surprise is a regression test.

---

## J. Controls

**Endpoint A — end-to-end research yield.** A uniform pool over the whole structural grammar.
It deliberately does **not** copy the LLM's metric preferences: the endpoint asks whether
choosing what to ask about beats blind enumeration, and a control inheriting those choices
cannot answer it.

**Endpoint B — conditional signal quality.** A marginal pool drawn from the treated arm's own
structural marginals, then matched and weighted. Conditioning is on genuine measurability and
support, never on an outcome. Controls buy matching flexibility; the inferential unit stays the
canonical family and the clustered SE stays on the multiplicity family, so controls never
become thousands of independent votes.

Both pools are enumerated from a SHA-256 counter stream — never `hash()`, never `random` — so
they are byte-identical under every `PYTHONHASHSEED`.

**Slot inhabitation** (`V7_1_SLOT_INHABITATION.json`) proves, before any outcome exists, that
the generator can occupy every structural slot the treated arm occupies: comparator, subject,
side, window, condition kind, condition count, metric group, target-set size, similarity usage,
capability class, admissible-universe size, temporal resolution and confounder family. A
crippled-generator negative control proves the check can fail.

---

## K. Balance

Endpoint-B matching is **exact on every frozen structural covariate**. Coarsening was tried
and measured, outcome-blind, on the V7.1 pools:

| key that was coarsened | worst \|SMD\| it left |
|---|---|
| `metric_group` dropped at the coarse tier | **0.874** (treated arm is ~80% `SCORING`; a metric-blind stratum draws controls from the whole vocabulary) |
| `time_scope` and `target_band` dropped (V7's hierarchy) | 0.496 / 0.361 |
| `subject` dropped | 0.283 |

So V7.1 has **one tier**: an exact stratum on the whole covariate vector. Matching flexibility
comes from pool size — a 200,000-family marginal pool, 110,951 of them structurally valid and
measurable — rather than from relaxing the key. A treated family with fewer than
`MIN_NULL_PER_STRATUM = 3` exact controls is reported `NO_COMPARABLE_CONTROL`, never matched
against something structurally different.

```
treated offered to matching        51
matched (TIER_1_EXACT)             46
no comparable control               5      unmatched fraction 0.098  (limit 0.25)
distinct controls carrying weight 809
total control weight             46.0      == n_matched, exactly, by construction
Kish effective sample size      428.1      (minimum 20.0)
max single control weight share   0.007    (limit 0.25)
covariate levels checked            35
levels out of balance                0
worst |SMD| (weighted)            0.000
control_b_comparable              true
```

Balance is computed on the **matched** treated sample, and the estimand is recorded in the
artifact as `MATCHED_TREATED_SAMPLE`. An unmatched treated family has no comparator to be
balanced against; it is accounted for by the unmatched-fraction limit, not by dragging a
zero-weight level into the standardized differences. Thresholds were frozen before the
cross-tabulation and none depends on an effect.

**What the 5 unmatched families are.** All five carry the comparator
`SUBJECT_RECENT_VS_LONG_BASELINE`, but that is not a hole in that comparator: 24 of its 29
treated families matched. Beyond the comparator they share nothing — they span three metric
groups (`SHOT_VOLUME` x2, `TERRITORY` x2, `SCORING` x1), both subjects, both sides, three target
bands and two admissible-universe sizes. The attrition is therefore the expected tail of exact
stratification on a 6-key vector: rare covariate combinations that the 200k marginal pool did
not inhabit at least `MIN_NULL_PER_STRATUM` times. It is not a systematic exclusion of a metric
group, a universe size, or a comparator, so the matched Control-B arm is not structurally
narrower than the treated arm along any single frozen covariate. The unmatched families remain
counted in the treated denominator and in the unmatched-fraction limit.

`worst |SMD| = 0.000` is not a tuning achievement — it is what exact stratification means. The
work was in deciding that exactness was required, and in paying for it with pool size.

---

## L. Evaluability

V7 reached a computable estimate for 16 of 132 families and a 16-pair, 9-cluster comparison,
and nobody knew that apparatus could not answer its own question until the window was spent.
V7.1 therefore decides before opening the fresh sample.

**Frozen precision requirement.** `MDE = 0.05`, `alpha = 0.05` two-sided, `power = 0.80`, with
a 1.15 inflation for the clustered-t reference distribution. 0.05 is half the per-family OOS
quality score a structurally comparable control arm produced in V7 (0.0609).

**Simulated dispersion.** From the development-window diagnostic replay: the standard deviation
across multiplicity-family clusters of the cluster-mean score, `cluster_sigma = 0.02981`.
Dispersion is not an effect — it carries no direction and no significance — and §16 explicitly
permits development-window simulation for sizing.

| check | have | need | |
|---|---|---|---|
| competitions | 6 | 4 | ✓ |
| folds | 3 | 3 | ✓ |
| fixtures per fold (minimum) | 105 | 50 | ✓ |
| evaluable families | 51 | 12 | ✓ |
| distinct teams | 122 | 40 | ✓ |
| effective sample size | 428.1 | 20.0 | ✓ |
| clusters for power | 8 | 4 | ✓ |

**Verdict: `V7_1_EVALUABILITY_GATE_PASSED`.** Smallest detectable difference at 8 clusters:
**0.032**, comfortably inside the 0.05 the requirement asks for.

**Is the MDE commensurate with the scale?** It has to be checked, not assumed — an MDE larger
than the entire range a metric can take is vacuous. On the development window the repaired
engine produces family scores with median \|score\| 0.015, p90 0.106, max 0.129, and **13 of 51
families exceed 0.05**. The V7 anchor (0.0609) sits inside that range. The requirement is
commensurate.

*(This check was the reason D11 was caught: the first V7.1 binding produced a maximum family
score of 0.044, below the MDE, which is what prompted comparing the compiled recency semantics
against V7's frozen definition. The mis-scaling was a symptom of the defect, not a reason to
re-anchor the threshold — and the threshold was not re-anchored.)*

**Stability criterion — unchanged from V7.** Direction agreement over **folds**, threshold
0.75, with competition stability reported separately. A finer (fold × competition) **cell**
unit was built and trialled and is **rejected** on an a-priori power argument: a cell holds
tens of observations, so for a true effect of \|r\| ≈ 0.1 the probability that a cell's
correlation even has the right sign is about Φ(0.1·√50) ≈ 0.76 — a 0.75 threshold at cell level
measures sampling noise, not stability. *Disclosure: the cell unit was trialled before it was
rejected, and on the development window it left zero survivors. That observation preceded the
decision; the power argument stands on its own, and the reverted unit and threshold are V7's,
so nothing is loosened.*

**Limitation, stated plainly.** Three folds spanning five weeks, roughly a fortnight apart, is
a thin walk-forward. It clears `MIN_FOLDS` and every support minimum, and the fixture counts
per fold (105/105/107) are healthy. But direction stability across three blocks that close
together is weak evidence of *temporal* stability in the sense six quarterly folds would give.
A null result on this sample should be read as "no signal detectable in five weeks of the
2026/27 season", not as "no signal across seasons". The gate passes; the limitation is real and
is not dissolved by passing it.

---

## M. Diagnostic V7 replay — `DIAGNOSTIC_ONLY` / `NON_CONFIRMATORY` / `OUTCOME_ALREADY_VIEWED`

The already-viewed V7 sample replayed through the repaired code. **Structural findings only
drive readiness.** Nothing here changed a threshold or a semantic in response to an effect.

| | V7 as executed | V7.1 replay |
|---|---|---|
| canonical families | 132 | 132 |
| refused for a **named structural reason** before measurement | 0 | **61** |
| — `IDENTICAL_COHORT_BASELINE` / `SELF_COMPARISON` | — | 44 |
| — `BASELINE_ABSORPTION` | — | 17 |
| `UNMEASURABLE` (capability) | 79 | 20 |
| measurable **and** structurally valid | 53 | **51** |
| with a computable estimate | 16 | **51** |
| **contrastless cells after repair** | 37 families reached `TAUTOLOGICAL` *after* a full walk-forward | **0** |
| confounder-unresolved cells | required a mid-flight patch | 10 (in the secondary per-competition view only; named and reported) |

**Semantic recovery.** 61 families are now refused by name instead of silently measured as
zero; 56 families move from `UNMEASURABLE` to a reported restricted universe. The count of
families that reach a real estimate goes from 16 to 51 — and the 51 have a contrast that
exists, which the 16 could not all be said to have.

**Zero contrastless cells** is the load-bearing number in this section: the degeneracy that
consumed most of V7's evaluable sample is gone, and it is gone because queries are refused
upstream, not because they were re-labelled.

Diagnostic outcome, reported and then left alone: 13 of 51 families would have reached
`OOS_SURVIVES` on the development window (29 direction-unstable, 9 no-effect). They are
dominated by `FORM_VS_BASELINE`, which is what V7 found too. This is a property of
already-viewed data and is **not evidence for V7.1**; it appears here only because §17 asks
whether the repaired apparatus produces non-degenerate features where a contrast genuinely
exists. It does.

---

## N. Fresh confirmatory OOS manifest

V7's confirmatory window consumed 2025-01-01 → 2026-05-31, which is the entire tail of the
cached corpus. No untouched chronological sample remained in it, so V7.1 **acquired the 2026/27
season** for the same six competitions from the same provider, through the repository's
existing cache-first, quota-capped client, under dedicated `f27_*` cache tags so neither the
frozen `multisrc_corpus.LEAGUES` registry nor V7's corpus identity could change.

| competition | finished fixtures |
|---|---|
| Championship 26/27 | 81 |
| LaLiga 2 26/27 | 55 |
| Ligue 2 26/27 | 54 |
| LaLiga 26/27 | 51 |
| Premier League 26/27 | 40 |
| Ligue 1 26/27 | 36 |
| **total** | **317** |

514 live API requests; 59,914 of the monthly quota remaining afterwards.

### Zero-overlap proof

Membership is by **season id**, not by date, so a rescheduled fixture cannot drift across the
boundary; disjointness is then proved on **fixture identifier sets**, not date ranges.

```
confirmatory fixtures                        317
development fixtures                       5,319
V7 confirmatory fixtures (a subset)        3,606
confirmatory ∩ development                     ∅
confirmatory ∩ V7 confirmatory                 ∅
proof level                    FIXTURE_IDENTIFIER_SET
confirmatory fixture set sha256   6f20c484327e0df7…
```

The 3,606 count matters: a zero-overlap proof against an empty V7 window would be vacuous.

### Partition and folds

Development is **everything outside the fresh season ids** — the whole historical corpus,
including everything V7 viewed and everything V7.1's repair work touched. Confirmatory is the
fresh season alone. Folds are equal-count chronological blocks in kickoff order; each fold
trains on everything strictly before its own start.

| fold | validate window | fixtures | competitions |
|---|---|---|---|
| 0 | 2026-08-08 → 2026-08-24 | 105 | all 6 |
| 1 | 2026-08-24 → 2026-09-05 | 105 | all 6 |
| 2 | 2026-09-05 → 2026-09-14 | 107 | all 6 |

No fixture is excluded; no fold shares a fixture with another.

### What is shared, said out loud

**History is shared; outcomes are not.** A 2026/27 fixture draws its point-in-time history from
2023–2026 — the same corpus the development window used — because that is what a PIT feature
*is*. What must be disjoint is the set of fixtures whose **outcomes** are read, and that is
what the proof above establishes. A reader should not mistake shared history for a leak, and
should not be left to work out that it is shared.

The unavoidable consequence: V7's confirmatory window is part of V7.1's development data.
Nothing can undo that without discarding two and a half seasons of history. It is recorded as a
limitation rather than argued away.

No effect was computed on any fresh fixture to produce this section. Only structure was read:
fixture, team, competition and fold counts.

---

## O. Leakage tests

**Layer 1 — guard mutations.** Eighteen classes injected, every one rejected, and a legitimate
point-in-time observation **accepted** (a guard that rejects everything would pass trivially).

| # | mutation | result |
|---|---|---|
| 01 | target fixture's own outcome in its baseline | rejected |
| 02 | target fixture's post-match statistic as input | rejected |
| 03 | observation after the reference time | rejected |
| 04 | future fixture of the same team in a profile | rejected |
| 05 | future fixture of the opponent in a profile | rejected |
| 06 | future season aggregate | rejected |
| 07 | settlement field | rejected |
| 08 | closing line | rejected |
| 09 | future market price | rejected |
| 10 | future lineup | rejected |
| 11 | future injury | rejected |
| 12 | future formation | rejected |
| 13 | target-own-stat field | rejected |
| 14 | timestamp exactly at the cutoff | rejected |
| 15 | provider retrieval after kickoff | rejected |
| 16 | similarity profile built from the future | rejected |
| 17 | scaler fitted on a future fold | rejected |
| 18 | shrinkage hyperparameter fitted on the future | rejected |
| 00 | **legitimate prior observation** | **accepted** |

**Layer 2 — empirical probes against the live compiler.** A guard can be correct while the
engine never calls it, so the red team also corrupts the corpus and re-compiles:

| probe | expected | observed |
|---|---|---|
| corrupt the **target** fixture's own statistic | feature unchanged | unchanged |
| corrupt a **future** fixture | feature unchanged | unchanged |
| corrupt a valid **prior** fixture of the subject | feature **moves** | **moves** |

The third is the negative control. Without it the first two prove nothing — a feature that is
simply constant would pass them both.

**Layer 3 — structural.** Every fixture identifier a compiled query reads is asserted to have a
kickoff strictly before the target's, and the target's own identifier is asserted absent. The
point-in-time guarantee is a property of the index's construction (accessors are keyed by
chronological record position and cumulative prefixes cannot reach forward), not a convention
the engine is trusted to honour.

---

## P. Reproducibility

Every deterministic specification and control universe is re-derived in a **fresh interpreter**
under `PYTHONHASHSEED` ∈ {0, 1, 42, random} **and** under both compatible interpreter
environments on this machine, then compared by SHA-256.

```
interpreters                /home/ubuntu/.venv/bin/python  3.12.3   (project venv)
                            /usr/bin/python3               3.12.3   (system, separate site-packages)
seeds                       0, 1, 42, random
environments                8   (2 interpreters x 4 seeds)
quantities re-derived       19
unstable across seeds       0
unstable across interpreters 0
byte_stable                 true
```

Anything built from Python's salted `hash()` or the `random` module would differ between seeds;
everything here is built from sorted canonical JSON and a SHA-256 counter stream.

The two interpreters share a minor version but have independent site-packages trees; the
project venv is the environment the test suite and the confirmatory driver run under, and is
the one that produced the frozen manifest.

---

## Q. Test results

```
tests/research/            (full research suite, venv 3.12.3)   3260 passed, 1 failed, 21m34s
tests/research/hypothesis_v71/  (V7.1 only, final code)            97 passed, 9.6s
```

**The one failure is pre-existing and is not repaired, deliberately.**

```
FAILED tests/research/hypothesis_oos/test_v7_control_b.py::
       test_blast_radius_proof_is_current_and_complete
AssertionError: V7 modules missing from the blast-radius declaration:
                ['src/research/hypothesis_v7/measurement.py']
```

It was reproduced on the **unchanged pre-V7.1 baseline** by checking out commit `4c663a737`
into a detached worktree and running the same test there: it fails identically. This branch did
not introduce it. It is recorded as defect **D14** (P3, evidence integrity).

Repairing it would mean regenerating `V7_BLAST_RADIUS.json`, a frozen V7 artifact, after V7's
confirmatory outcomes have been viewed. Section 1 forbids that, so V7 is left exactly as
frozen. What the failure means — that V7's "no pre-existing test module reaches changed code"
claim was never checked for one module — is instead **re-verified read-only** in
`V7_1_BLAST_RADIUS.json`:

```
V7 modules undeclared in V7's own artifact : ['src/research/hypothesis_v7/measurement.py']
    test modules reaching them             : ['tests/research/hypothesis_v71/test_v71_engine.py']
```

The only test module that reaches it is one of V7.1's own new tests. No pre-existing test
module reaches it, so V7's published conclusion was correct although under-verified.

**The class, not the instance.** The same hand-maintained-declaration pattern had already
drifted inside V7.1: the first blast-radius driver named 18 modules while 20 were on disk
(`matching.py` and `bugledger.py` were missing, so no importer analysis ever covered them).
V7.1's driver now derives the changed set from the package directory, and two new tests fail if
the published artifact ever again disagrees with disk.

No test was skipped, xfailed, deleted or weakened to obtain these numbers. No new `skip` or
`xfail` marker was introduced anywhere on this branch.

**Scope of the delta since the full run.** The full suite above was executed before the D14
repair. The repair touched `src/research/hypothesis_v71/bugledger.py`, the two V7.1 driver
scripts and the V7.1 test module. `V7_1_BLAST_RADIUS.json` (regenerated, 221 test modules
scanned) shows exactly two test modules can transitively reach any V7.1 module —
`test_v71_engine.py` and `test_v71_semantics.py` — and both were re-run to completion (97
passed). No other test module in the repository can import the changed code.

---

## R. Blast radius

Machine-generated by AST transitive-import closure over the first-party tree
(`V7_1_BLAST_RADIUS.json`):

```
test modules scanned                 221
reach changed/added V7.1 code          2   (the two new V7.1 test modules)
cannot reach it                      219
```

V7.1 is **purely additive**: it adds `src/research/hypothesis_v71/` and imports from V7 without
modifying any existing module. No pre-existing test can be affected by a V7.1 change, which is
why the full-suite result below is a check on the environment rather than on the new code.

---

## S. Git state

```
branch      feat/v7-1-hardening   (from feat/model-oos-benchmark at the V7 freeze commit)
remote      origin  git@github.com:atlasrwa/football-quant-engine.git
```

| commit | contents |
|---|---|
| `f4817fff3` | preserve the V3–V6.1 hypothesis research lineage (533 files) |
| `4c663a737` | freeze the immutable V7 apparatus, evidence and report (63 files) |
| `04f2bbf54` | V7.1 semantic IR, compiler invariants, capability contract, golden suite |
| `68f17df65` | V7.1 engine, controls, evaluability gate, fresh sample, red team, drivers |
| `73ee8b771` | exact Endpoint-B matching, corrected recency binding, frozen apparatus |
| *(final)* | this report and the frozen artifacts it describes |

No `.env`, credential, API secret, transient runtime log or unrelated data is committed. Every
commit stages **explicit paths** — never `git add -A` over the repository root, which is the
user's home directory and contains `.ssh`, `.aws`, `.git-credentials` and shell history among
8,000+ untracked files.

### The working tree is not empty, and the claim is not that it is

Twenty tracked files remain modified. **None was touched by this mission**; all predate it and
belong to unrelated work:

| files | what they are |
|---|---|
| `src/research/llm_matchup/**` (4), `tests/research/test_golden_v3_resume.py`, `research/llm_matchup/out/hardening_v3/**` (3) | an in-progress LLM-matchup V3 hardening effort from a previous session |
| `tests/conftest.py` | a `hypothesis` profile registration (`derandomize=True`) added by earlier V6.1 work; test infrastructure only |
| `data/discovery/**`, `data/forward/**`, `data/creator/**`, `data/forecast_broadcast/**` (11) | append-only runtime ledgers written by scheduled jobs |

Also untracked and left alone: `research/champion_audit/`, `research/contextual_matchup/`,
`research/evaluation/` — prior research from other sessions, out of scope for this branch.
Section 2 forbids mixing unrelated production changes into this branch, so they were not
swept in. `git status` will show them; this table is here so a reader is not left to wonder
whether they are mine.

Everything V7.1 produced — every source module, test, driver, specification and frozen
artifact — is committed.

---

## T. CHAMPION

```
before  0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9
after   0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9
```

**Unchanged.** No production feature, coefficient, calibration, publication path, signal logic
or `p_model` was touched. The freeze driver re-verifies the digest against V7's preregistered
value on every run, and the execution driver refuses to proceed if it differs. CHAMPION is
never opened for writing anywhere on the V7.1 path.

---

## U. Bedrock

```
BEDROCK_CHANGE_REQUIRED = false
KIRO_HANDOFF_REQUIRED   = false
```

No AWS, IAM, inference-profile, SDK-runtime, model-access, `CountTokens` or Converse change
was needed or made. The execution driver refuses to proceed if any `boto3`, `botocore`,
`bedrock`, `converse` or `counttokens` module is on the import path.

The one external call made in this mission was **data acquisition**: finished 2026/27 fixtures
and their per-match `/stats` from TheStatsAPI, through the repository's existing cache-first,
quota-capped client, under dedicated `f27_*` cache tags so neither the frozen
`multisrc_corpus.LEAGUES` registry nor V7's corpus identity could change. It was explicitly
authorized before any request was sent.

---

## V. Final authorization state

```
CONFIRMATORY_OOS_COMPUTED   = false
CONFIRMATORY_OOS_VIEWED     = false
CANDIDATE_FEATURE_PROMOTION = false
BEDROCK_CHANGE_REQUIRED     = false
KIRO_HANDOFF_REQUIRED       = false
```

No effect, correlation, p-value or terminal state has been computed, printed, cached, logged or
inspected for any of the 317 fresh confirmatory fixtures. The execution driver's dry run
constructs every object a real run constructs — index, capability contract, similarity engine,
fold positions — verifies all 27 frozen hashes, and then stops before the first effect:

```
=== V7.1 EXECUTION DRIVER ===
  mode                  : DRY RUN
  experiment            : V7_1_HARDENED_HYPOTHESIS_VALIDATION
  artifacts verified    : 27 (failing: 0)
  zero overlap          : True
  evaluability          : V7_1_EVALUABILITY_GATE_PASSED
  engine spec           : 4138f90bbf73c959
  CHAMPION              : 0b8f5ff3dc4ddf15
  interpreter pinned    : True (/home/ubuntu/.venv/bin/python 3.12.3)
  cloud modules loaded  : none
  index                 : 5636 records
  folds                 : {'0': 105, '1': 105, '2': 107}

DRY RUN COMPLETE. No confirmatory outcome was computed, read or written.
```

The freeze manifest records the interpreter the apparatus was frozen under
(`/home/ubuntu/.venv/bin/python` 3.12.3, CPython) and the preflight refuses if the live
interpreter differs. Section P proves the apparatus is byte-identical across both interpreters
on this machine, so this is a pin rather than a correctness dependency: running the
confirmatory experiment under a different interpreter is possible, but only by re-freezing
deliberately, which is visible in the manifest.

Under `--authorize` the driver re-runs the same preflight and then refuses, because computing a
confirmatory outcome is outside this mission's authorization. A separate, explicit
authorization is required.

---

## Final machine states

```
V7_FROZEN_IMMUTABLE                        V7_1_STATISTICAL_CONTRACTS_GREEN
V7_1_SEMANTIC_IR_LOCKED                    V7_1_CONTROL_UNIVERSES_FROZEN
V7_1_PROVIDER_CAPABILITY_CONTRACT_LOCKED   V7_1_MATCHING_WEIGHTS_FROZEN
V7_1_COMPILER_INVARIANTS_GREEN             V7_1_EVALUABILITY_GATE_PASSED
V7_1_SIMILARITY_ENGINE_GREEN               V7_1_FRESH_OOS_MANIFEST_FROZEN
V7_1_PIT_RED_TEAM_GREEN                    V7_1_REPRODUCIBILITY_GREEN
V7_1_EXECUTION_DRIVER_DRY_RUN_GREEN        V7_1_CHAMPION_UNCHANGED
V7_1_CONFIRMATORY_OOS_NOT_OPENED           V7_1_READY_FOR_CONFIRMATORY_OOS
```

**STOP.** Do not execute the confirmatory V7.1 run until a separate explicit authorization is
issued.
