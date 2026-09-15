# V3 Hypothesis → Deterministic Historical Measurement

**Stage:** LLM hypothesis → **deterministic historical measurement** → sample/coverage →
confounder-aware analysis → walk-forward OOS → possible candidate feature.

**Spend:** $0.00. No Bedrock call, no LLM call, no network read. Every number below was
computed in Python from the immutable V3 outputs and the PIT-safe dual-provider corpus.

**Scientific question.** *Do the frozen hypotheses Sonnet 4.6 actually generated correspond
to measurable historical football relationships, and do they define useful, sufficiently
populated conditional cohorts?* Not whether Sonnet predicted any fixture correctly — that
question is not asked, and no artifact here could answer it.

`SONNET46_HYPOTHESIS_V3 = FAIL` is accepted permanently and is untouched. Nothing in this
task rescored V3, altered its firewall, gates, thresholds, responses, hypotheses or
verdict, or ran another LLM experiment.

---

## Eligibility criteria for the closing token — stated before the results

Deliverable 15 asks which families are *technically* eligible for a preregistered
confounder-aware / OOS stage. The gates are **structural only**. No criterion reads a
difference, a sign, a magnitude or any significance quantity:

| Criterion | Rule | Source |
|---|---|---|
| measurable query | family measurable rate ≥ 0.80 | conventional rate |
| sufficient coverage | mean conditional coverage ≥ 0.80 | conventional rate |
| reasonable sample N | median conditional usable N ≥ 8 | `context_packet.reliability_for` MEDIUM floor |
| distinct information | ≥ 10 distinct measured comparisons **and** corpus duplicate rate 0 | — |
| provider consistency | one pinned provider, zero unsupported plans | `PROVIDER_SEMANTICS` |
| PIT safety | zero leakage violations corpus-wide | mandate §3 |

**Disclosure on ordering.** These criteria were written *after* the measurement run, not
before it. What protects the conclusion is not the ordering but the construction: there is
no term in any criterion that could respond to an observed effect, and every threshold
except the two conventional rates is an existing canonical project value rather than a new
number chosen to fit this corpus. Stating this plainly is preferable to claiming a freeze
that did not happen.

---

## 1. Exact frozen hypothesis corpus used

Source: `out/hypothesis_v3_sonnet46/hypothesis_states.jsonl`, experiment
`SONNET46_HYPOTHESIS_V3`, manifest hash `cfd9244067c9dc0c…`.

| | |
|---|---|
| Reference-arm responses | 12 |
| Clean (no whole-response rejection) | 11 |
| **Eligible hypotheses** | **112** |
| Compiled query plans | 158 |

112 and 158 are exactly the frozen V3 denominators for P1 and P2. The corpus was derived by
re-running the **frozen analyzer's own** `score_all()` and reading
`validator_v2.accepted_hypotheses` — the acceptance decision is V3's, not re-implemented
here.

Artifact: `out/v3_hypothesis_measurement/frozen_hypothesis_corpus.json`

## 2. Inclusion / exclusion rules

**Included** — all three clauses, evaluated purely from frozen V3 artifacts before any
historical data was read:

```
control == "reference"                    # the unperturbed, factually-true packet arm
whole_response_failure is None            # survived the frozen V3 gates
hypothesis in validator_v2.accepted_hypotheses
```

**Excluded, with reasons preserved verbatim:**

| Reason | Records | Detail |
|---|---|---|
| `NON_REFERENCE_ARM` | 44 responses | every other arm sent a deliberately altered packet — perturbed shot surfaces, withheld dimensions, starved evidence, unsupported-data traps — so its hypotheses concern counterfactual football |
| `LATENT_GRADING_VIOLATION` | 1 response (seq 11) | whole-response rejection under frozen V3 gates; **no hypothesis salvaged** |
| `INFRASTRUCTURE_CENSORED` | 0 | none in the battery |

**The repeatability arm is deliberately not in the measurement corpus.** It re-sent 6 of
the same 12 frozen packets, so folding it in would double-count those fixtures in every
family denominator and every funnel count. Its 12 clean responses are retained for **one**
purpose: the same-input duplicate/equivalent-query analysis in §9, where plan agreement
across identical inputs is exactly the quantity of interest.

None of: match outcome, future fixture statistics, closing line, apparent plausibility,
effect direction, effect magnitude, or statistical significance is readable by the
selection code. A test asserts no outcome- or market-shaped field reaches any
specification.

## 3. Deterministic measurement specification per hypothesis

158 specifications, one per compiled query plan. Each is a pure projection of the **frozen**
`query_plan.QueryPlan` (that module is in the V3 frozen module-hash manifest and was not
touched) plus deterministic fixture resolution. No LLM-written SQL exists anywhere; no LLM
interpretation occurs during execution.

Fields carried: subject label + resolved club · target metric · side · venue · competition ·
own/opponent formation family · opponent-profile band + axis + band semantics · comparison
cohort · window · period · granularity · historical cutoff · provider · required corpus
fields · plan hash.

The executor is a **new** module, `cohort_measurement_v1`. It was added rather than editing
`measurement.py` because the V1-era executor **ignores `plan.comparison` entirely** — its
baseline is unconditionally the window slice, i.e. only `SUBJECT_OVERALL_BASELINE`. Four of
the five frozen comparisons had no implementation anywhere in the repository. A test asserts
that none of the five now falls through to `UNSUPPORTED_COMPARISON`.

Artifact: `out/v3_hypothesis_measurement/measurement_specs.json`

## 4. PIT / leakage audit

| | |
|---|---|
| Specifications checked | 158 |
| Observations at or after cutoff | **0** |
| Target fixture appearing in any cohort | **0** |
| Closest observed kickoff to cutoff | −343,800 s (≈ 3.98 days strictly before) |
| **Audit clean** | **yes** |

`historical_match_time < target_fixture_cutoff` is enforced in three independent places:
the corpus index (`HistoryIndex.prior`), an explicit target-fixture exclusion in the
observation builder, and a backstop inside `cohort_measurement.execute` that returns
`LEAKAGE_REJECTED` rather than measuring.

The leakage tests are **positive tests**, not assertions that clean input stayed clean:
they feed a deliberately leaked observation and assert refusal, including the boundary case
`kickoff == cutoff` (the rule is strict `<`). One test takes a history that measures
successfully, adds a single leaked row, and asserts the same input now refuses — proving
the check bites rather than passing vacuously.

No market information, closing line or settlement field is read by any module in this
stage; none is even importable from the measurement package.

Artifact: `out/v3_hypothesis_measurement/pit_audit.json`

## 5. Provider provenance

| | |
|---|---|
| Provider, all 158 plans | `thestatsapi` (single pinned provider) |
| Provider-semantics conflicts | 0 |
| Silent proxies substituted | **0** |
| Corpus field blocks | `rich` 121 · `extra` 19 · `base` 18 |
| Granularity / period | `FULL_MATCH` / `ALL` on all 158 |

Provider is pinned per metric by the frozen compiler's `_pin_provider`; no measurement mixes
a FootyStats stat with a TheStatsAPI stat of the same concept. Every measurement record
carries provider, the exact corpus field block and key, the corpus module, the similarity
version and the band semantics. A metric with no reader in the corpus adapter is typed
`UNSUPPORTED_METRIC` and no proxy is substituted — that path exists and is tested, and it
fired zero times here because all 15 metrics used are directly readable.

## 6. Conditional and comparison cohort measurements

All five frozen comparisons are implemented as the **exact** contrast the plan encodes:

| Comparison | Comparison cohort |
|---|---|
| `SUBJECT_OVERALL_BASELINE` | subject's window slice, unconditioned |
| `SUBJECT_VENUE_BASELINE` | subject's matches at the **upcoming fixture's** venue |
| `SUBJECT_COMPETITION_BASELINE` | subject's matches in the target competition |
| `LEAGUE_ENVIRONMENT_BASELINE` | competition-wide team-match population before cutoff |
| `SUBJECT_RECENT_VS_LONG_BASELINE` | same conditions on `ALL_PRIOR`; only the **window** differs |

Each measurement reports, for both cohorts: N, usable N, missing N, coverage rate,
missingness rate, reliability band, mean, median, SD, variance, p25/p75, min, max — plus
conditional-minus-comparison difference, shrunk difference (`n/(n+6)`), shrinkage weight,
SE, undetermined count, distinctness, overlap rate, per-dimension coverage and full
provenance.

**Three-valued condition logic is preserved.** A match with no recorded value for a
conditioned dimension is `None`, not `False`: it is excluded from the conditional cohort
**without** being counted as a non-member, because missing data is not evidence of
difference. The same applies to an opponent that could not be banded.

`SUBJECT_COMPETITION_BASELINE` is implemented and unit-tested but was **exercised zero
times against the corpus**: no eligible hypothesis requested it. The next stage should not
assume that path has been validated on real data.

Every record is labelled `association_type: DESCRIPTIVE_ASSOCIATION`.

Artifact: `out/v3_hypothesis_measurement/cohort_measurements.json`

## 7. N and coverage distributions

Canonical project conventions were found and are reused **verbatim** — no new threshold was
invented, so §7's fallback ("if no canonical rule exists, report raw distributions before
proposing thresholds") does not apply:

| Constant | Value | Source |
|---|---|---|
| `SHRINK_K` | 6.0 | `llm_matchup/cohorts.py:28` (= `measurement.py:38`) |
| `MIN_CONDITIONAL_N` | 4 | `hypothesis_engine/measurement.py:41` |
| `MIN_COMPARISON_N` | 8 | `hypothesis_engine/measurement.py:42` |
| `MIN_PRIOR_MATCHES` | 4 | `hypothesis_engine/similarity.py:122` |
| reliability bands | LOW <8, MEDIUM 8–19, HIGH ≥20 | `context_packet.py:70` |

Raw distributions are reported anyway, because the next stage needs them:

| | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| conditional usable N | 0 | 10 | **18** | 32 | 70 | 20.6 |
| comparison usable N | 4 | 37 | 56 | 69 | 1400 | 115.1 |
| conditional coverage | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.974 |

Conditional reliability bands: **HIGH 73 · MEDIUM 53 · LOW 32**.

Small-N hypotheses are reported, never discarded: `INSUFFICIENT_DATA` records carry the
full cohort statistics and simply decline to estimate a difference. Small N is recorded as
a scientific result, and it is concentrated exactly where the battery's stratification
predicted:

| Fixture | Stratum | prior N | formation cov. | Outcomes |
|---|---|---|---|---|
| mt_013233190 | `THIN_HISTORY` | 4 / 4 | 0.250 | **8 INSUFFICIENT_DATA, 0 measured** |
| mt_010441320 | `HIGH_CARD_PROFILE` | 64 / 64 | 0.188 | 12 measured, 4 insufficient (all formation) |
| mt_010243515 | `HIGH_CORNER_PROFILE` | 40 / 40 | 0.175 | 7 measured, 6 not-distinct |
| mt_010243537 | `HIGH_CORNER_PROFILE` | 104 / 50 | 0.123 | 14 measured, 4 not-distinct |
| mt_010243938 | `LOW_CORNER_PROFILE` | 69 / 70 | 0.151 | 23 measured |
| mt_010244159 | `HOME_AWAY_ASYMMETRIC` | 71 / 71 | 0.176 | 10 measured |
| mt_010244193 | `HIGH_SHOT_VOLUME` | 67 / 67 | 0.157 | 9 measured |
| mt_010441491 | `FORMATION_RICH` | 37 / 79 | 0.215 | 12 measured |
| mt_010444904 | `FORMATION_RICH` | 56 / 14 | 0.229 | 10 measured |
| mt_012232295 | `FORMATION_SPARSE` | 37 / 37 | 0.013 | 23 measured |
| mt_012232411 | `FORMATION_SPARSE` | 27 / 27 | 0.037 | 16 measured |

The `THIN_HISTORY` fixture is wholly unmeasurable at the canonical floors — 4 prior matches
per side. That is a property of the corpus, not of the hypotheses, and the hypotheses it
produced were structurally indistinguishable from those for rich fixtures.

Artifact: `out/v3_hypothesis_measurement/n_and_coverage_distributions.json`

## 8. Unsupported / unmeasurable hypotheses

| Outcome | Plans | Meaning |
|---|---|---|
| `MEASURED` | **136** | distinct cohort, both floors met |
| `INSUFFICIENT_DATA` | 12 | corpus **can** answer it; too few matches |
| `NOT_DISTINCT` | 10 | compiles and is measurable, but encodes **no contrast** |
| `UNSUPPORTED_*` | **0** | corpus **cannot** answer it |
| compile failure | **0** | all 158 plans compiled under the frozen compiler |

`UNSUPPORTED` and `INSUFFICIENT_DATA` are deliberately separate outcomes and separate
counts: "the corpus cannot answer this" is a capability fact, "the corpus has three matches"
is a sample fact, and collapsing them would make the funnel unreadable.

**The 10 `NOT_DISTINCT` plans are the most interesting negative result in this stage.** All
7 `SUBJECT_VENUE_BASELINE` plans are degenerate: a hypothesis that conditions on venue and
then compares against the same-venue baseline defines a conditional cohort that is the
*identical match set* as its comparison. The remaining 3 are unconditioned hypotheses
compared against `SUBJECT_OVERALL_BASELINE` — also identical by construction. These pass
schema, firewall, grounding and compilation; only execution reveals the tautology. The
frozen V3 multi-condition classifier independently detects this class
(`_BASELINE_ABSORBS_DIMENSION`), so the two instruments agree.

## 9. Duplicate / equivalent-query analysis

Equivalence key = fixture · subject · metric · side · window · period · all conditions ·
comparison.

| | |
|---|---|
| Plans | 158 |
| Distinct equivalence keys | **158** |
| **Within-corpus duplicate rate** | **0.0000** |

Within a response the model never proposes the same measurement twice — a genuinely clean
result and a prerequisite for treating each plan as independent research.

Same-input agreement, using the repeatability arm (identical frozen packet, re-sent):

| Fixture | ref keys | rep keys | shared | Jaccard |
|---|---|---|---|---|
| mt_010243515 | 13 | 35 | 1 | 0.021 |
| mt_010243938 | 23 | 21 | 8 | 0.222 |
| mt_010244193 | 9 | 17 | 6 | 0.300 |
| mt_010441320 | 16 | 22 | 4 | 0.118 |
| mt_010441491 | 12 | 24 | 10 | 0.385 |
| mt_012232295 | 23 | 30 | 11 | 0.262 |
| **mean** | | | | **0.218** |

Independent corroboration of V3's most important uncaught finding: the frozen battery
measured a same-input repeatability floor of **0.1894**, and the same-input *plan* overlap
measured here is **0.2179**. Two different instruments on two different objects agree that
identical inputs produce largely non-overlapping research proposals. Any future invariance
or stability claim built on this generator must account for that.

Artifact: `out/v3_hypothesis_measurement/duplicate_analysis.json`

## 10. Hypothesis-family diagnostics

By condition family:

| Family | generated | plans | measured | measurable rate | insuff. | not distinct | unsupported | median cond. N | mean coverage |
|---|---|---|---|---|---|---|---|---|---|
| `venue` | 57 | 80 | 66 | 0.825 | 7 | 7 | 0 | 28 | 0.997 |
| `opponent_profile` | 36 | 53 | 52 | **0.981** | 1 | 0 | 0 | 14 | 0.991 |
| `unconditional_behavioral_profile` | 14 | 19 | 16 | 0.842 | 0 | 3 | 0 | 14 | 0.985 |
| `formation` | 4 | 5 | 1 | **0.200** | 4 | 0 | 0 | 8 | 0.400 |
| `meaningful_multi_condition` | 1 | 1 | 1 | 1.000 | 0 | 0 | 0 | 11 | 1.000 |

By comparison type:

| Comparison | generated | plans | measured | rate | note |
|---|---|---|---|---|---|
| `SUBJECT_OVERALL_BASELINE` | 94 | 133 | 118 | 0.887 | |
| `LEAGUE_ENVIRONMENT_BASELINE` | 8 | 10 | 10 | 1.000 | |
| `SUBJECT_RECENT_VS_LONG_BASELINE` | 5 | 8 | 8 | 1.000 | conditional N capped at W5 = 5 |
| `SUBJECT_VENUE_BASELINE` | 5 | 7 | **0** | **0.000** | all 7 degenerate |

Research-family and metric-family breakdowns are in the artifact.

**The direct answer to §9's question — is Sonnet generating research our corpus can
support?** Overwhelmingly yes for behavioural and opponent-profile conditioning (0.84–0.98
measurable), and overwhelmingly no for formation conditioning (0.20). The formation failure
is a **corpus** limitation, not a hypothesis-quality one: recorded-formation coverage on
these fixtures runs 0.013–0.250, so a formation-conditioned cohort is dominated by
missingness. The model was not told formation data was thin; it proposed formation research
at a low rate (4 of 112) anyway.

Artifact: `out/v3_hypothesis_measurement/family_diagnostics.json`

## 11. Descriptive association results

**These are descriptive historical measurements. They are not predictive effects, not
evidence of OOS value, and no hypothesis was selected on them.**

Across the 136 measured comparisons:

| | value |
|---|---|
| conditional − comparison difference | min −2.95 · p25 −0.38 · **median +0.20** · p75 +1.07 · max +6.71 |
| sign | 79 positive · 57 negative · 0 zero |
| median \|difference\| / SE | 0.764 |
| fraction \|difference\| / SE > 1 | 0.382 |
| fraction \|difference\| / SE > 2 | 0.081 |

`|difference| / SE` is reported as a **scale-free descriptive dispersion summary only**. It
is not a significance test, no multiplicity correction is applied, and it is used in no
selection, ranking or eligibility decision anywhere in this stage.

By family (median |difference|/SE): `unconditional` 1.33 · `formation` 0.96 ·
`opponent_profile` 0.74 · `venue` 0.71 · `meaningful_multi_condition` 0.03.

The near-balanced sign split and the small typical standardized magnitude are what a corpus
of *descriptive* conditional contrasts should look like before any confounder adjustment.
Nothing here licenses a claim in either direction.

## 12. Confounder inventory

Current label: **`DESCRIPTIVE_ASSOCIATION`**. Later label, only after adjustment:
`CONFOUNDER_ADJUSTED_EFFECT`. **No causality is claimed at this stage.**

| Family | Confounders the next stage must adjust for |
|---|---|
| `venue` | opponent strength · team strength · competition · schedule congestion · score state |
| `opponent_profile` | opponent strength (the band axis is *behavioural*, not strength) · venue · team strength · competition · score state · **band drift** |
| `formation` | manager / tactical regime · opponent strength · venue · **formation selection is endogenous to the expected opponent** · lineup availability / injuries · score state |
| `meaningful_multi_condition` | every confounder of both constituent dimensions · **cohort thinning** (interaction cells are small) |
| `unconditional_behavioral_profile` | team strength · opponent strength · venue · competition · season / regime drift |

**Band drift is a known, recorded limitation of this stage.** Opponent-profile bands are
resolved **once, at the target fixture cutoff** (`PROFILE_BAND_SEMANTICS =
"AS_OF_TARGET_CUTOFF"`), using `similarity.resolve_band` exactly as designed — PIT-safe with
respect to the prediction, since every input match is strictly before the cutoff. The
alternative, re-banding at each cohort match's own kickoff, shifts the tercile reference
population per match, so two members of the same "HIGH" cohort would not be HIGH against the
same distribution; that is a different estimand and no module in this repository validates
it. The next stage must decide this explicitly rather than inherit it.

The model named its own candidate confounders on every hypothesis; the most frequent are
recorded in the artifact and broadly overlap this inventory. They are treated as *proposals
to check*, never as an adjustment set.

Artifact: `out/v3_hypothesis_measurement/confounder_inventory.json`

## 13. Hypothesis-to-measurement funnel

```
V3 valid hypotheses (reference arm, clean responses)      112
  -> compilable query plans                               158   (1.41 plans/hypothesis, 0 compile failures)
    -> historically measurable                            158   (100.0% - 0 unsupported by the corpus)
      -> sufficient data AND distinct                     136   ( 86.1% of plans)
        -> distinct research comparisons                  136   (100.0% - zero duplicate keys)
```

Information efficiency — the §10 question, *how often does a frozen LLM hypothesis lead to a
distinct, measurable historical cohort with adequate data?*

**The 136 measured comparisons descend from 94 distinct hypotheses: 94 of the 112
eligible hypotheses (83.9%) yield at least one distinct, adequately-populated historical
cohort.** Compilable syntax converted into usable research at a high rate. The losses are 12 sample-size failures
(11 of which come from the `THIN_HISTORY` fixture and the formation family) and 10
structural tautologies.

The final category is **not** called predictive. It is called *measurable*.

Artifact: `out/v3_hypothesis_measurement/funnel.json`

## 14. The single meaningful multi-condition hypothesis (seq 8)

Measured **exactly like every other eligible hypothesis** — same pipeline, same cohort
construction, same floors, same code path. Its cohort was not changed, it received no
favourable treatment, and its result modified no threshold. It is reported separately only
because it is scientifically informative about V3's depth question.

> *"Does the home team concede fewer big chances when playing at home against opponents with
> a high shots_on_target_for profile, compared to its overall baseline?"*
> — `mt_010444904` (Cádiz, laliga2), H6

| | |
|---|---|
| Conditions | `venue = HOME` **+** `opponent_profile = HIGH, axis = shots_on_target_for` |
| Metric / side | `big_chances` / `AGAINST` |
| Comparison | `SUBJECT_OVERALL_BASELINE` |
| Band resolution | 29 competition candidates, 29 bandable (coverage 1.000), 10 HIGH members, terciles lo ≤ 3.65 / hi ≥ 4.287 |
| Conditional cohort | **N = 11**, coverage 1.000, mean 2.364, median 2.0, SD 1.748, p25 1.5, p75 3.0 |
| Comparison cohort | N = 56, usable 55, mean 2.382, median 2.0, SD 1.758 |
| Difference | **−0.018 big chances/match** (shrunk −0.012, SE 0.578, weight 0.647) |
| Outcome | `MEASURED` |

**The interaction hypothesis measured cleanly and found essentially nothing** — a difference
two orders of magnitude smaller than its own standard error. That is a legitimate
descriptive result, not a failure of the hypothesis or of the measurement.

The scientifically important part is structural, not numerical: the one interaction the
model produced in 112 attempts **survived to a fully populated, PIT-safe, band-resolved
cohort of 11 matches with complete coverage**. Interaction hypotheses of this shape are
measurable in this corpus. V3's depth FAIL was about *generation rate* (1/112), and this
stage confirms the constraint is on the generator, not on the measurement apparatus.

Artifact: `out/v3_hypothesis_measurement/seq8_multicondition.json`

## 15. Recommendation for the next preregistered stage

Applying the structural gates stated at the top of this report:

| Family | plans | measured | rate | median N | Eligible | Blocking |
|---|---|---|---|---|---|---|
| `venue` | 80 | 66 | 0.825 | 28 | **YES** | — |
| `opponent_profile` | 53 | 52 | 0.981 | 14 | **YES** | — |
| `unconditional_behavioral_profile` | 19 | 16 | 0.842 | 14 | **YES** | — |
| `formation` | 5 | 1 | 0.200 | 8 | no | measurable query · coverage · distinct information |
| `meaningful_multi_condition` | 1 | 1 | 1.000 | 11 | no | distinct information (**n = 1**, corpus too small) |

**Recommended for a preregistered confounder-aware / OOS stage:** `opponent_profile` first
(highest measurable rate, zero degeneracy, clean band coverage, and the only family that
exercises the deterministic similarity machinery), then `venue` (largest N, but 7 of its
comparisons were structurally degenerate — the preregistration must exclude the
baseline-absorbing combination by construction), then
`unconditional_behavioral_profile` as a control family rather than a research target.

**Not recommended:** `formation`, blocked by corpus coverage rather than by hypothesis
quality — revisit only if lineup coverage improves. `meaningful_multi_condition` is blocked
**solely by n = 1**; it is not a quality judgement, and the right way to unblock it is a
generation-side change, which is a new experiment version, not a repair of V3.

**Screening warning.** If any later stage screens hypotheses on effect magnitude or sign,
that screening rule must itself be preregistered and validated on data disjoint from the
walk-forward evaluation window, or it contaminates the OOS test. No such screening is
applied here, and none of the five gates above contains an effect term.

Artifact: `out/v3_hypothesis_measurement/next_stage_recommendation.json`

---

## Test status

| Suite | Result |
|---|---|
| Full repository | **4529 passed, 0 failed** (21m49s, `.venv` interpreter) |
| `tests/research/hypothesis_engine` | **511 passed, 0 failed** (488 before this task + 23 new) |
| New: `test_v3_cohort_measurement.py` | **23 passed** |

No pre-existing failures and no new failures. The 23 new tests cover positive leakage
refusal (including the `kickoff == cutoff` boundary), three-valued condition logic,
all five frozen comparisons, typed-unsupported vs insufficient separation, unresolvable
profile axes, deterministic-similarity guards, canonical-threshold identity with the
existing project constants, corpus-eligibility denominators, absence of any outcome- or
market-shaped field in the specifications, and the import-graph firewall.

---

## Architecture confirmation

- No Bedrock call, no LLM call, no network read. **$0.00.**
- No V2 or V3 frozen artifact modified. `SONNET46_HYPOTHESIS_V3 = FAIL` stands untouched.
- `query_plan.py`, in the V3 frozen module-hash manifest, was **used, not edited**.
- `CHAMPION` untouched · `p_model` untouched · calibration untouched · production
  prediction untouched.
- No challenger trained, no LLM probability adjustment, no betting edge, no closing line
  read, no feature promoted, no alpha claimed.
- The measurement package imports no Bedrock client and no production-prediction path; an
  import-graph test enforces it.
