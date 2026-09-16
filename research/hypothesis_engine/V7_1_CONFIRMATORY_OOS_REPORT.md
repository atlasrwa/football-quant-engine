# V7.1 — Confirmatory out-of-sample execution report

**Experiment** `V7_1_HARDENED_HYPOTHESIS_VALIDATION`
**Freeze** `v71_freeze_v3` · **Apparatus commit** `d983ce688e2855a374c20c9e218ee299fa70eba7`
**Executed** 2026-09-16, from a clean isolated checkout, pinned interpreter CPython 3.12.3.

The frozen sample was opened once. Nothing in the apparatus was changed before, during or
after the run. This report states what the measurement returned.

---

## 1. Executive verdict

The frozen evaluator does not emit a PASS/FAIL, so none is forced here. The six states it
does define are reported separately.

| | |
|---|---|
| **Execution status** | COMPLETE. Exit 0. All 2478 families evaluated and persisted. No partial exposure, no resume, no interruption. |
| **Apparatus status** | INTACT. Every preflight binding recomputed and matched. All 34 bound artifacts verified after the run. CHAMPION never opened for writing. |
| **Scientific evaluability** | `V7_1_EVALUABILITY_GATE_PASSED`. The apparatus was able to answer its own question at the frozen precision. |
| **Endpoint A** | **NEGATIVE.** LLM-derived families survive OOS at **16.7 %** (22/132) against the uniform null's **40.2 %** (803/2000). Difference **−23.5 points**, in favour of the null. |
| **Endpoint B** | **NULL.** 44 matched pairs over 6 clusters. Paired point estimate **−0.00555**. Exact enumerated cluster sign-flip **p = 0.53125**. |
| **Interpretation** | The confirmatory question — *do the frozen V6.1-derived hypotheses produce OOS-stable relationships at a better rate or quality than the frozen controls?* — is answered **no** on rate and **not distinguishable from zero** on quality. |

The headline gap is a **measurability** gap, not an effect-quality gap. Only 51 of 132 LLM
families (38.6 %) were measurable at all, against 1618 of 2000 (80.9 %) for the uniform null.
*Among measurable families* the survival rates are 43.1 % (LLM) and 49.6 % (null) — still
favouring the null, but by 6.5 points rather than 23.5. Endpoint A's denominator is
deliberately ALL canonical families, so the frozen endpoint charges unmeasurability to the
proposer. That is the preregistered choice and it is not revisited here; it is simply named,
because it is what drives the number.

---

## 2. Preflight integrity

Every value below was recomputed live in the clean checkout immediately before the run. None
was taken from the mission prompt or from a prior artifact.

| Commitment | Value | Status |
|---|---|---|
| Apparatus head | `d983ce688e2855a374c20c9e218ee299fa70eba7` | matches |
| Branch | `feat/v7-1-hardening` | matches |
| Freeze version | `v71_freeze_v3` | current |
| Freeze manifest | `22bbd20d1437b4446d320003620af550316f4ef68e88ac1a9c99bebeb210179c` | matches |
| Bound artifacts | 34 verified, 0 failing | matches |
| Source graph | `3df6cb03b1d07c66caa89ca5c92af46eb62b148bc0e7c93b7f67a094aa4fd063` | matches |
| Source-graph counts | static 35 · runtime 34 · union 35 · runtime-only 0 · untracked 0 · unresolved first-party 0 · ambiguous 0 | matches |
| Upstream V7 | `bf7806de3f3045f05e9bef6a76760ae760b90962c9e2c14c604a9a06b4cdac9d` | matches |
| Fresh content | `c0dcf99cb1e4c52b5bc3d785f163af28a0c118d43f0ec8ad277ba050631026cf` | matches |
| Historical PIT | `a6de3e6b1f3cc4b5065358d2e11a9f09fdfdc6b7d6dc37b2b2c362ae670ac1c7` | matches |
| Confirmatory fixtures | `6f20c484327e0df75eb0930ed270b9d5e35e748f8b3980c25ad2a9d225329032` | matches |
| Engine spec | `25527df61eb93e38d2d0fa7c568029d3a08276c78ed0a994c1ee3d2c22000be0` | matches |
| CHAMPION | `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` | unchanged |
| Interpreter | `/home/ubuntu/.venv/bin/python` · CPython 3.12.3 | pinned, matches |
| Cloud/Bedrock modules | none loaded | clean |
| Authorization token | `a218cdc0a012e2148aecb0d99eef832b3881f68d35228e1a4f66f11fa2a031a4` | valid |
| Corpus | 5636 records = 5319 development + 317 fresh | matches |
| Folds | `{0: 105, 1: 105, 2: 107}` | 3 chronological folds |

### 2.1 Clean isolated execution environment

The prior mission's isolation method was not recorded anywhere in the repository, so an
equivalent mechanism was built, as Section 3 of the authorization permits. It is stated here
in full because the integrity of the run depends on it.

- A detached `git clone --no-hardlinks` of the repository was checked out at
  `d983ce688`, and **bind-mounted over `/home/ubuntu`** inside a private mount namespace
  (`unshare -m --propagation private`). The apparatus hard-codes that absolute root, so it
  sees the frozen commit and nothing else. The developer working tree was masked for the whole
  run.
- Inside the namespace `src/research/matchup/` contains only `__init__.py` and `corpus.py`.
  The uncommitted V4/V5a modules **do not exist on disk at all**.
- `git status --porcelain` was **empty** at mint time and at run time.
- The commit does not contain the provider corpus, so **5655 non-code JSON files** were
  supplied from the working tree — determined empirically by auditing every `open()` the
  preflight performs under `data/`, not guessed. All 5655 live under
  `data/thestatsapi/championship`. **Zero are `.py`**; a recursive scan confirms no Python
  whatsoever under `data/`. None shadows a tracked path.
- Those exact paths — and only those — were written to `.git/info/exclude`, so porcelain is
  empty without masking anything else. This was **canary-tested**: a new untracked file
  created in the same directory still appears in `git status`. The exclusion is precise and
  falsifiable, and the supplied content is independently bound by the frozen fresh-content
  (`c0dcf99c…`) and historical-PIT (`a6de3e6b…`) commitments, both of which verified.
- The clean-checkout executability proof was **regenerated at `d983ce688`** with all 22 stages
  PASS, including `corpus_builds` (5636 records), `fresh_content_verifies`,
  `historical_pit_content_verifies`, `execution_plan_rebuilds`, the development execution
  path, and the full test suite.

### 2.2 Load-bearing test run

**167 passed, 0 skipped** — exactly the expected baseline.

The frozen proof artifact recorded `166 passed, 1 skipped`, and that discrepancy was
adjudicated *before* minting rather than absorbed afterward. The proof had been taken at the
parent commit `8af4426db`, where
`test_16_clean_checkout_proof_exists_and_binds_the_freeze_manifest` skips for want of the
proof artifact. `d983ce688` commits that artifact, so the test runs and passes. Exactly one
test moved from skipped to passed; the discrepancy is fully attributed.

### 2.3 Stale-artifact protection

`V7_1_DIAGNOSTIC_REPLAY.json` — the bound development diagnostic that feeds the evaluability
gate's precision input, and the artifact behind defect D16 — was **regenerated from the frozen
code and is byte-identical** to the bound version (`08443ddc…`). The live diagnostic is
`cluster_sigma = 0.03052062945008663`, the v3 value, **not** the stale v2 value
`0.029808027369281072`. The evaluability verdict is `V7_1_EVALUABILITY_GATE_PASSED`.

All 34 bound artifacts were re-verified after every regeneration step; none drifted.

### 2.4 Seal state at the moment of authorization

`CONFIRMATORY_OOS_COMPUTED=false` · `CONFIRMATORY_OOS_VIEWED=false` ·
`AUTHORIZATION_TOKEN_MINTED=false` · `POST_OOS_DESIGN_CHANGES=0` ·
`CANDIDATE_FEATURE_PROMOTION=false`. No confirmatory output artifact, no
`per_family_evidence/` directory and no cached effect existed anywhere in the repository or
the clean root. The development exercise writes to a separate `_dev_exercise/` namespace and
could not have seeded a resume.

The token was minted **only after** all of the above were green, by calling the executor's own
`AUTH.build_expected(...)` on values from a live in-process `preflight()` that reported
`problems: []`. No hash was typed by hand. The minting script was run from outside the
repository root so it could not enter the source graph — a precaution that proved necessary:
an earlier audit script placed at the repository root was **correctly refused** by the
source-graph guard as `UNTRACKED_EXECUTABLE_DEPENDENCY`.

---

## 3. Scope exceptions

Both exceptions were recorded durably and **committed at `6508086c2`, before the
authorization token existed**, so the ordering is checkable in git history rather than
asserted after the fact.

**V7 D14** — historical immutable blast-radius declaration defect, severity P3. Remains
unfixed inside frozen V7 by design. V7 was not patched. Non-blocking.

**V4/V5a historical executable-source defect** — tracked historical runner/test code
references `src/research/matchup/design.py`, `features.py` and `harness.py`, which were never
committed. The fail-closed condition was verified live and **holds**:

- `v71_static_reachable = false`, `v71_runtime_reachable = false`, `v71_union_reachable = false`
- the source graph's 35 files contain **none** of the three modules; the only `matchup` members
  are `__init__.py` and `corpus.py`
- all 35 bound files are git-tracked, present, and hash-match
- 0 untracked executable dependencies, 0 unresolved first-party imports
- **strongest form:** in the clean checkout the three modules are absent from disk entirely, so
  any path reaching them would raise `ImportError` rather than silently resolving against the
  developer tree — and the apparatus imports, builds the corpus, rebuilds the full plan and
  passes its whole suite in that environment

The modules were not harvested or committed. Historical V4 was not modified.

**Unrelated shadow/persisted-state failures** — outside the V7.1 execution path. No unrelated
working-tree changes were imported to make the global suite cosmetically green.

Recorded truthfully: `FULL_RESEARCH_SUITE_GREEN=false` ·
`V7_1_SCOPED_EXECUTABLE_CLOSURE_GREEN=true` · `V7_1_FREEZE_V3_READY_FOR_AUTHORIZATION=true`.

---

## 4. Endpoint A — end-to-end research yield

Denominator: **ALL** frozen canonical families, measurable and unmeasurable alike.
`matched = false` — this endpoint is an unmatched rate comparison by design.

| Funnel stage | LLM treated | rate of canonical | Uniform null | rate of canonical |
|---|---:|---:|---:|---:|
| Canonical | 132 | 100 % | 2000 | 100 % |
| Measurable | 51 | 38.6 % | 1618 | 80.9 % |
| Support-qualified | 49 | 37.1 % | 1508 | 75.4 % |
| Computable (OOS stage reached) | 51 | 38.6 % | 1618 | 80.9 % |
| **OOS-surviving** | **22** | **16.67 %** | **803** | **40.15 %** |

**Surviving-rate difference: −0.23483** (LLM minus uniform null).

Attrition reasons are preserved for every family in both arms
(`attrition_reasons_preserved: true`).

Two honest readings of the same funnel, both reported:

1. **As preregistered** (denominator = all canonical): the LLM arm loses by 23.5 points. Most
   of what the LLM proposed could not be measured by the deterministic engine at all.
2. **Conditional on measurability** (22/51 = 43.1 % vs 803/1618 = 49.6 %): the LLM arm still
   loses, by 6.5 points. Conditioning does not rescue the result — it only reattributes the
   bulk of the gap from "the surviving effects are worse" to "far fewer proposals were
   measurable".

Neither reading is favourable to the LLM arm.

---

## 5. Endpoint B — conditional signal quality

Primary statistic `OOS_QUALITY_SCORE_DIFFERENCE`, matched, cluster unit = multiplicity family.

| | |
|---|---|
| Scored treated families in the estimate | **44** of 51 |
| Unscored / unmatched | **7** (see 5.2) |
| Mean paired difference (over pairs) | **−0.010201** |
| **Paired point estimate** (unweighted mean of cluster means) | **−0.005551** |
| Cluster count **G** | **6** |
| Primary method | `EXACT_ENUMERATED_CLUSTER_SIGN_FLIP` |
| Enumeration | complete — all **64** = 2⁶ sign vectors |
| **Exact p-value** | **0.53125** |
| Inference status | `EXACT` |
| Clustered SE | 0.009562 — **descriptive only**, not used for inference |
| Normal-approximation p | **not used** (`normal_approx_p_is_not_used: true`) |

### 5.1 Cluster contributions

| Multiplicity family | pairs | cluster mean |
|---|---:|---:|
| attack_quality | 8 | −0.001261 |
| attacking_volume | 2 | −0.001895 |
| defensive | 5 | −0.047195 |
| discipline | 4 | **+0.047065** |
| form_baseline | 13 | −0.027040 |
| opponent_interaction | 12 | −0.002979 |
| **unweighted mean of 6 clusters** | 44 | **−0.005551** |

**1 of 6 clusters is positive.** 14 of 44 individual pairs are positive. Matched control
support per pair ranges 4–71 (median 20).

### 5.2 What is not in the estimate

Seven of the 51 evaluable treated families are absent from Endpoint B:

- **2 unscored** — `CONFOUNDED_UNRESOLVED`, no score produced (`3077e2b5…`, `af51a6de…`), both
  `form_baseline`.
- **5 scored but unmatched** — no matched control under exact stratification (`d922b8d6…`,
  `a5ee502d…`, `4c6804d9…`, `8696272d…`, `af8e5ae2…`). This is the known tail of exact
  stratification, at exactly the documented count of 5.

**This materially matters and is not smoothed over.** Three of the five unmatched families
(`d922b8d6…`, `4c6804d9…`, `8696272d…`) are OOS survivors, all in `attacking_volume`, and all
three are in the frozen candidate set. The `attacking_volume` cluster therefore contributes to
Endpoint B on only **2** pairs while its three strongest members are excluded for want of a
control. Endpoint B is silent about precisely the subset that looks best — not because anything
was hidden, but because exact stratification found no comparator.

### 5.3 The sign-symmetry assumption

As preregistered at `6508086c2`, before any fresh outcome was opened:

> The Endpoint-B enumerated cluster sign-flip p-value is exact conditional on the frozen
> assumption that cluster-level paired treated-minus-control contributions are
> sign-symmetric/exchangeable around zero under the null.

This is **not** a randomized-treatment randomization test. Treatment is "which hypotheses an
LLM proposed" and was never randomly assigned to clusters; the reference distribution is
imposed by assumption, not generated by design. The p-value is exact *with respect to the
enumeration*, and assumption-dependent *with respect to the null*.

With G = 6 the enumeration has only 64 points, so the smallest attainable two-sided p is
coarse. At p = 0.53125 the observed statistic sits near the middle of its own reference
distribution; no interpretation of the symmetry assumption would turn this into evidence of an
effect. The preregistered degradation rule — downgrade the p-value's interpretation, never
change the estimator — is therefore not triggered in a way that would alter the conclusion.

---

## 6. Fold stability

Three chronological folds over the five-week fresh window (105 / 105 / 107 fixtures).

| | n | mean | min |
|---|---:|---:|---:|
| Fold direction agreement | 49 | 0.8310 | **0.500** |

The minimum is 0.5 — coin-flip direction agreement — and it is reported rather than smoothed.
Per-family fold counts range from 1 to 12; three OOS survivors (`42570a2a…`, `fc67193b…`,
`22fa72db…`) rest on a **single fold**, so their p-value is `None` and their apparent stability
is not evidence of anything. Two-fold survivors include the two highest-scoring families
overall (`26f29a80…` q = +0.183, `2ca528d2…` q = +0.165). The strongest-looking results in the
treated arm are, in general, the thinnest.

## 7. Competition stability

| | n | mean | min |
|---|---:|---:|---:|
| Competition direction agreement | 49 | 0.7502 | **0.500** |

Six competitions (champ, epl, laliga, laliga2, ligue1, ligue2). Again a floor of 0.5. No
competition is excluded and no subset is selectively reported.

## 8. Family and multiplicity analysis

**By research family (treated arm, n = 51):**

| Research family | n | survives | rate |
|---|---:|---:|---:|
| ATTACK_VOLUME | 3 | 3 | 100 % |
| TEMPO_AND_TERRITORY | 2 | 2 | 100 % |
| DISCIPLINE | 4 | 3 | 75 % |
| DEFENSIVE_CONCESSION | 3 | 2 | 67 % |
| FORM_VS_BASELINE | 17 | 9 | 53 % |
| OPPONENT_PROFILE_INTERACTION | 12 | 3 | 25 % |
| DEFENSIVE_SUPPRESSION | 2 | 0 | 0 % |
| ATTACK_QUALITY | 8 | 0 | 0 % |

**By multiplicity family (the Endpoint-B cluster unit):**

| Multiplicity family | n | survives | rate |
|---|---:|---:|---:|
| attacking_volume | 5 | 5 | 100 % |
| discipline | 4 | 3 | 75 % |
| form_baseline | 17 | 9 | 53 % |
| defensive | 5 | 2 | 40 % |
| opponent_interaction | 12 | 3 | 25 % |
| attack_quality | 8 | 0 | 0 % |

The two families at 100 % have 3 and 5 members. `attack_quality` is the largest family with a
zero survival rate. With six clusters and these counts, per-family rates carry very little
information individually and are reported for completeness, not as findings.

## 9. Survivors

All 22 OOS survivors, not only the favourable ones. `q` = OOS quality score, `dir` = fold
direction agreement, `comp` = competition direction agreement, `CAND` = member of the frozen
candidate set.

| | id | q | dir | comp | folds | p | capability | family |
|---|---|---:|---:|---:|---:|---:|---|---|
| | `26f29a8043ab` | +0.18313 | 1.00 | 0.75 | 2 | 0.1648 | RESTRICTED | form_baseline |
| | `2ca528d265b3` | +0.16477 | 1.00 | 0.67 | 2 | 0.0663 | RESTRICTED | form_baseline |
| **CAND** | `8696272d40d6` | +0.15266 | 0.83 | 0.90 | 6 | 0.0149 | SUPPORTED | attacking_volume |
| | `42570a2abe5c` | +0.14755 | 1.00 | 0.67 | 1 | — | RESTRICTED | form_baseline |
| **CAND** | `d922b8d633fd` | +0.14588 | 0.83 | 0.80 | 6 | 0.0199 | SUPPORTED | attacking_volume |
| | `a5ee502d2f5a` | +0.12710 | 1.00 | 0.88 | 3 | 0.1042 | RESTRICTED | form_baseline |
| **CAND** | `2fd97e741773` | +0.11723 | 0.78 | 0.89 | 9 | 0.0061 | RESTRICTED | opponent_interaction |
| | `9d68a1245875` | +0.10490 | 0.83 | 0.70 | 6 | 0.0896 | SUPPORTED | discipline |
| | `3c85937dcde4` | +0.09461 | 1.00 | 0.85 | 4 | 0.0103 | SUPPORTED | form_baseline |
| **CAND** | `4c6804d93503` | +0.08945 | 1.00 | 0.75 | 9 | 0.0052 | SUPPORTED | attacking_volume |
| **CAND** | `dcdcca6685bb` | +0.08781 | 1.00 | 0.67 | 9 | 0.0021 | RESTRICTED | attacking_volume |
| **CAND** | `586957731381` | +0.08781 | 1.00 | 0.67 | 9 | 0.0021 | RESTRICTED | attacking_volume |
| | `09854416e590` | +0.08083 | 1.00 | 1.00 | 3 | 0.0774 | SUPPORTED | discipline |
| | `78ffe23416c0` | +0.08083 | 1.00 | 1.00 | 3 | 0.0774 | SUPPORTED | discipline |
| | `d3d94086b80f` | +0.05461 | 0.79 | 0.69 | 8 | 0.0646 | SUPPORTED | form_baseline |
| | `8ba53ae024fe` | +0.05217 | 0.75 | 1.00 | 12 | 0.1199 | RESTRICTED | opponent_interaction |
| | `ea1c21bf0e82` | −0.05157 | 0.78 | 0.67 | 9 | 0.2377 | SUPPORTED | defensive |
| **CAND** | `8c2f5ec3ed51` | −0.08375 | 0.83 | 0.75 | 12 | 0.0083 | RESTRICTED | defensive |
| | `fc67193beaa2` | −0.08635 | 1.00 | 0.89 | 1 | — | RESTRICTED | form_baseline |
| | `22fa72dbae32` | −0.08635 | 1.00 | 0.89 | 1 | — | RESTRICTED | form_baseline |
| | `4e1319900d9e` | −0.11017 | 0.83 | 0.83 | 12 | 0.0212 | RESTRICTED | opponent_interaction |
| | `bbde77c9328c` | −0.14839 | 1.00 | 0.78 | 2 | 0.2521 | RESTRICTED | form_baseline |

Note that "survives" is a **direction-stability** terminal state, not a sign condition: six
survivors carry a *negative* quality score. A family can be stably wrong-signed and still be
recorded as surviving. Three pairs of survivors are numerically identical
(`09854416`/`78ffe234`, `dcdcca66`/`58695773`, `fc67193b`/`22fa72db`) — distinct canonical ids
that measure the same thing, so the effective survivor count is 19, not 22.

**Frozen candidate set (7):** `2fd97e741773`, `4c6804d93503`, `586957731381`, `8696272d40d6`,
`8c2f5ec3ed51`, `d922b8d633fd`, `dcdcca6685bb`. Every candidate is an OOS survivor; the
candidate criterion is strictly stronger than survival. One candidate (`8c2f5ec3ed51`) has a
negative quality score.

## 10. Failure taxonomy

Full named terminal states, all arms, no attrition hidden.

| Terminal state | LLM treated | uniform null | matched control pool |
|---|---:|---:|---:|
| `OOS_SURVIVES` | 22 (43.14 %) | 803 (49.63 %) | 328 (40.54 %) |
| `OOS_NO_EFFECT` | 18 (35.29 %) | 285 (17.61 %) | 248 (30.66 %) |
| `OOS_DIRECTION_UNSTABLE` | 9 (17.65 %) | 420 (25.96 %) | 218 (26.95 %) |
| `CONFOUNDED_UNRESOLVED` | 2 (3.92 %) | 19 (1.17 %) | 15 (1.85 %) |
| `INSUFFICIENT_SUPPORT` | 0 | 91 (5.62 %) | 0 |
| **total evaluable** | **51** | **1618** | **809** |

Upstream of this table, 81 of 132 canonical LLM families (61.4 %) never reached evaluation at
all because they were not measurable by the deterministic engine. That is the single largest
attrition step in the experiment and it falls entirely on the treated arm.

**Confounder attrition (NULL ≠ ZERO, defect D15 repair, treated arm):** all 51 families had at
least one row dropped for a missing required confounder; 588 rows dropped in total; 39 cells
failed after confounder exclusion; 17 families had confounded cells; 0 families had
contrastless cells. No missing confounder was imputed to zero.

**Capability status (treated arm):** 16 `SUPPORTED`, 35 `RESTRICTED`.

## 11. Provider and corpus integrity

Corpus content commitments verified before and after: fresh `c0dcf99c…` (317 fixtures, every
consumable provider field with nulls preserved — same ids *and* same values), historical PIT
`a6de3e6b…` (5319 records). Confirmatory fixture set `6f20c484…`. Upstream V7 inputs
`bf7806de…`, re-hashed from the referenced files rather than trusted from the proof.

The 5655 supplied corpus files are non-code JSON, content-bound by the two commitments above.
Zero Python under any supplied data root. No network access; the corpus layer is cache-only.
No Bedrock, boto3, botocore or model-invocation module was loaded at any point — verified by
live `sys.modules` inspection inside the executor's own process. **Zero spend.**

## 12. PIT and leakage integrity

Zero-overlap re-verified live: the confirmatory fixture set is disjoint from the development
corpus **and** disjoint from V7's own confirmatory window. The PIT index is structurally
point-in-time — accessors take a reference position and can only see strictly-earlier
observations — so leakage is prevented by construction rather than by convention. The frozen
leakage/red-team suite is part of the 167 passing tests.

The fresh 2026/27 seasons reuse the same six competition labels as the historical corpus so a
team's history spans the season boundary; season id is what makes a fixture fresh. The
historical corpus identity is unchanged (`a6de3e6b…`).

## 13. Reproducibility

`V7_1_DETERMINISM_VERIFIED = true`, on a genuine recomputation.

**Why the obvious re-run would not have counted.** `execution.run_experiment` begins with
`resume = load_persisted(out_dir)`, and the driver always passes `persist=True`. A second
`_v71_execute.py --authorize` against the same output directory loads all 2478 per-family
records off disk, skips `evaluate_family_evidence` entirely, and only re-runs the aggregation.
It would return a byte-identical result and prove nothing about recomputation. Reporting
determinism on that basis would have been false.

**What was actually done.** The first run's `per_family_evidence/` and
`V7_1_CONFIRMATORY_RESULT.json` were moved aside before the re-run, so `load_persisted`
returned empty and the evidence directory was verifiably absent at start. Every family was
recomputed from the corpus. No code was changed between the runs and no frozen artifact was
altered — this moves data, not the apparatus.

| Compared quantity | Result |
|---|---|
| Per-family evidence files | 2478 vs 2478, **0 byte-differing**, none only-in-one |
| Per-family aggregate digest | `b020009884723aa9435f689dfc44725b5f8231f0aaa1e3c7c57ae3f3f3f549b2` — identical |
| Evidence bundle | `99d7819e4dda982242337e9fb1ddada2d03fa78b033f04c1e8235e8438316544` — identical |
| Endpoint A | identical |
| Endpoint B (incl. point estimate, cluster contributions, sign-flip p) | identical |
| Multiplicity, fold stability, competition stability | identical |
| Candidate feature set | identical |
| Per-family terminal states | identical |
| Endpoint counts | identical |
| CHAMPION before/after | identical |

**No differences of any kind.** Byte-identical output was expected here and was obtained.

The **first** execution remains the scientific record. The re-run is corroboration; it does
not replace the first result, and no nondeterminism was repaired after seeing outcomes.

## 14. CHAMPION

| | |
|---|---|
| Before | `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` |
| After | `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` |
| Unchanged | **true** |

Verified in the clean checkout at preflight, recorded in the result, and re-hashed in the real
working tree after the run. CHAMPION is never opened for writing on this path.

## 15. Scientific limitations

Stated plainly, including the ones that cut against reading anything positive into the tail.

1. **The fresh window is five weeks** and supports only three chronological folds. This is the
   binding constraint on the whole experiment.
2. **G = 6 clusters** for Endpoint B — fewer than the ~8 anticipated at freeze time. The exact
   enumeration has 64 points, so p-value resolution is coarse and power is very low. A null
   here is weak evidence of absence, not evidence of absence.
3. **The Endpoint-B p-value is assumption-dependent**, not design-based (§5.3).
4. **5 unmatched families**, three of them candidate-set survivors in `attacking_volume`, are
   absent from Endpoint B (§5.2). The best-looking subset is the least comparable.
5. **Low support throughout the treated arm**: fold counts as low as 1, matched control support
   as low as 4, three survivors with no computable p-value.
6. **Duplicate canonical ids**: 22 survivors reduce to 19 distinct measured relationships.
7. **Direction stability is not correctness**: six survivors have negative quality scores.
8. **Shared history**: V7's confirmatory window is part of V7.1's development data. Outcomes
   are not shared, but history is.
9. **Structural family counts** (16 / 51 / 132) were seen before the coverage threshold was
   fixed — a pre-OOS exposure that is recorded, not corrected.
10. **Endpoint A's denominator choice drives its headline.** Charging unmeasurability to the
    proposer is defensible and was preregistered, but the 23.5-point gap becomes 6.5 points
    conditional on measurability. Both are reported; neither favours the LLM arm.
11. **The authorization token is now committed and remains a valid key.** Any future
    `--authorize` in a tree where preflight passes would re-enter the authorized path — and,
    because `run_experiment` resumes from `per_family_evidence/`, would reuse the existing
    records rather than recompute them. That is the state this mission leaves behind.
12. **This experiment does not establish market edge, does not produce `p_model`, and does not
    modify CHAMPION.** It measures whether LLM-proposed research hypotheses generalize better
    than controls. The answer is no.

## 16. Final machine states

```
V7_1_CONFIRMATORY_OOS_EXECUTED        = true
V7_1_OOS_EVIDENCE_FROZEN              = true
V7_1_ENDPOINT_A_EVALUATED             = true
V7_1_ENDPOINT_B_EVALUATED             = true
V7_1_MULTIPLICITY_APPLIED             = true
V7_1_CANDIDATE_FEATURE_SET_FROZEN     = true
V7_1_CHAMPION_UNCHANGED               = true
V7_1_EXPERIMENT_COMPLETE              = true

CONFIRMATORY_OOS_COMPUTED             = true
CONFIRMATORY_OOS_VIEWED               = true
POST_OOS_DESIGN_CHANGES               = 0
CANDIDATE_FEATURE_PROMOTION           = false
CHAMPION_UNCHANGED                    = true

V7_1_DETERMINISM_VERIFIED             = true

FULL_RESEARCH_SUITE_GREEN             = false
V7_1_SCOPED_EXECUTABLE_CLOSURE_GREEN  = true
V7_1_AUTHORIZATION_SCOPE_EXCEPTION_V4 = true
```

Two states need a word so they do not read as contradictions.

**`CONFIRMATORY_OOS_VIEWED`.** `V7_1_CONFIRMATORY_RESULT.json` hard-codes
`confirmatory_oos_viewed: false`, because `finalize_result` stamps the state at *write* time,
before anything is read. The mission-level state is **true** — the results were read to write
this report. The artifact field is not wrong; it records a different moment.

**Candidate handling.** The 7 surviving candidates are marked only to the frozen V7.1 candidate
state, the equivalent of `CANDIDATE_FEATURE_ELIGIBLE`. Nothing was promoted into CHAMPION, the
production feature set, `p_model`, calibration, market comparison or betting logic. Whether to
run a model-level experiment on them is a separate decision, not taken here.
