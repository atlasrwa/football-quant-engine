# SONNET46_HYPOTHESIS_V2 — Final Report

Experiment: `SONNET46_HYPOTHESIS_V2` · Model: `us.anthropic.claude-sonnet-4-6`
Manifest `59964d67…` · Battery `6e70d6e5…` · Run dir `research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/`

---

## 1. Zero-spend mechanical preflight — CLEAN

All frozen values verified **before** the first paid request. Nothing was repaired.

| Check | Result |
|---|---|
| `manifest_hash` == authorization, and self-consistent on recompute | PASS `59964d67…` |
| `battery_hash` == authorization, self-consistent | PASS `6e70d6e5…` |
| `controls.py` on-disk sha256 | PASS `52a76e3b…` |
| `normalize.py` on-disk sha256 | PASS `60a4dca0…` |
| `evaluation.py` on-disk sha256 | PASS `c07c21d3…` |
| `prompt_content_hash()` live recompute | PASS `9c9a0931…` |
| `schema_content_hash()` live recompute | PASS `acf90f95…` |
| Call plan per control == authorization | PASS (12/12/8/6/6/6/6/4/4 = 64) |
| Unique packets | PASS 52 |
| **Input tokens recomputed from the 64 serialized requests** | PASS **exactly 770,528** |
| All 52 `packet_hash` values self-consistent | PASS |
| `profile_perturbation` regenerates byte-identical from frozen references | PASS |
| `evaluation.THRESHOLDS` == manifest `pass_fail_thresholds` | PASS (identical) |
| V2 cache namespace empty before first call | PASS (did not exist) |

### 1a. The authorized profile-perturbation consistency assertion — CLEAN

> *Changing `corners_against` and `accurate_crosses_against` must not leave behind any stale
> derived summary, profile band, categorical label, quantile classification, natural-language
> evidence description, or other field whose semantics contradict the transformed raw values.*

**No inconsistency found. Verification only; zero repairs; zero paid calls made during the check.**

Full-tree diff of each perturbed packet against its reference shows **exactly three** differing
fields: the two AWAY values and the recomputed `packet_hash`. Structurally, no stale field can
exist because:

- evidence `id` hashes **`scope` only** (`subject/metric/side/venue/window`), never `value`;
- `reliability` derives from `sample_n` (40 → HIGH), not from `value`;
- `shrinkage_level` derives from cohort structure (`parent is not None`), not from `value`;
- evidence items carry **no** band / label / quantile / description field at all;
- `opponent_profile` bands are resolved at measurement time from history (`similarity.resolve_band`),
  never precomputed into the packet;
- no string anywhere in the packet echoes a pre-perturbation numeral.

| # | Fixture | Dir | `corners_against` | `accurate_crosses_against` | Verdict |
|---|---|---|---|---|---|
| 1 | mt_010441491 | RAISE ×1.60 | 5.2014 → 8.3222 | 5.1388 → 8.2221 | consistent |
| 2 | mt_012232295 | RAISE ×1.60 | 4.9015 → 7.8424 | 3.8584 → 6.1734 | consistent |
| 3 | mt_010243515 | RAISE ×1.60 | 3.4662 → 5.5459 | 3.8381 → 6.1410 | consistent |
| 4 | mt_010243938 | LOWER ×0.55 | 5.8320 → 3.2076 | 5.4789 → 3.0134 | consistent |
| 5 | mt_010441320 | LOWER ×0.55 | 4.9814 → 2.7398 | 4.1489 → 2.2819 | consistent |
| 6 | mt_010244193 | LOWER ×0.55 | 4.6327 → 2.5480 | 3.9627 → 2.1795 | consistent |

Both axes move together in every case; the frozen 3 RAISE / 3 LOWER split holds.

---

## 2. Execution

64/64 frozen calls executed in `seq` order. Frozen inference config used verbatim from
`FREEZE_LLM_MATCHUP_V3_SONNET46.json`: `temperature 0.0`, `maxTokens 8192`. (`topP: 1.0` is
omitted on the wire exactly as the frozen 4.6 adapter path does; under `temperature=0.0` it is
a no-op, so the sampling distribution is identical.)

**Retry semantics were not frozen in V2, so retries were set to zero.** No response — failed or
otherwise — was ever overwritten; the raw cache is write-once and states are fsync'd per call.

### Spend accounting

| Item | Value |
|---|---|
| Planned calls | 64 |
| Attempted | 64 |
| Completed | 64 |
| Cache hits | 0 |
| Retries | 0 |
| Infrastructure-censored | 0 |
| Model-rejected (no toolUse) | 0 |
| Input tokens | 1,228,036 |
| Output tokens | 165,127 |
| Total tokens | 1,393,163 |
| **Cost from actual tokens** | **$6.1610** |
| Ceiling | $9.15 |
| **Remaining under ceiling** | **$2.9890** |

`SONNET46_V2_SPEND_CEILING_REACHED` was **not** triggered. The battery was not reduced.

Note: the manifest's `chars/4` convention understated the real tokeniser by **1.594×**
(1,228,036 actual vs 770,528 estimated). The pre-call ceiling guard was therefore hardened to
scale by the measured ratio. This is spend-safety arithmetic only — no packet, prompt, schema,
threshold or score was touched.

---

## 3. Preregistered verdict (mechanical)

### Architecture / compliance

| Metric | Value |
|---|---|
| Schema-valid rate | **1.000** (64/64 responses schema-valid) |
| Numerical-authority violations (reference set, feeds gate E) | **6** |
| — of which `probability_claim` | **5** |
| — of which `percentage` | **1** |
| `probability_claim` hits across all 64 responses | **24** |
| `percentage` hits across all 64 responses | **6** |
| Odds / EV / edge / stake violations | **0** |
| Latent-advantage violations | **0** |
| Unsupported-capability violations | **0** (`unavailable_request_rate` 0.000) |
| Fabricated-evidence violations | **0** across all 64 responses |
| Leakage findings | **0** (52/52 packets + serialized requests audited CLEAN pre-spend) |

These are mechanical counts only. Their composition is analysed in §5a.

### Research quality

| Metric | Value | Threshold | Gate |
|---|---|---|---|
| Schema validity | 1.000 | ≥ 0.95 | **A PASS** |
| Query-compilability | 0.488 | ≥ 0.85 | **B FAIL** |
| Evidence grounding | 0.583 | ≥ 0.95 | **C FAIL** |
| Capability awareness (unavailable rate) | 0.000 | ≤ 0.05 | **D PASS** |
| Numerical authority | 6 / 0 | 0 | **E FAIL** |
| Football relevance | *not computed by the frozen scorer* | — | **F UNMEASURED** |
| Non-redundancy (median redundancy) | 0.000 | ≤ 0.35 | **G PASS** |
| Metric richness (median metrics / families) | 8.5 / 8.0 | ≥ 5 / ≥ 3 | **H PASS** |
| Identity robustness (median intent Jaccard) | 0.461 | ≥ 0.80 | **I FAIL** |
| Evidence sensitivity (trip rate) | 1.000 | ≥ 0.50 | **J PASS** |
| Irrelevant invariance | 0.000 | ≥ 0.90 | **K FAIL** |
| Abstention quality on starved packets | 0.000 | ≥ 0.70 | **L FAIL** |

**Gates passed: A, D, G, H, J. Gates failed: B, C, E, I, K, L. Gate F: unmeasured.**

`F_relevance` is named in the manifest's `scoring_rubric` but `evaluation.aggregate()` emits no
F gate at all — not even `None`. Under the manifest's own `gate_policy` ("Fail closed. An
unmeasured control gate is None and does NOT count as a pass") its absence cannot help the
verdict. It is recorded here rather than silently skipped.

**Comparison / cohort quality** (required metric, mechanical): across the 159 reference intents,
comparison baselines were `SUBJECT_OVERALL_BASELINE` 152, `SUBJECT_VENUE_BASELINE` 4,
`LEAGUE_ENVIRONMENT_BASELINE` 2, `SUBJECT_RECENT_VS_LONG_BASELINE` 1. Cohort condition dimensions
were venue 94, opponent_profile 7, own_formation_family 3, competition 1, half_score_state 0,
period 0. **Raw-metric utilization**: 16 of 19 available metrics used; median 8.5 distinct metrics
and 8.0 families per fixture.

### Provenance of the control predicates

The **thresholds** (0.80 / 0.50 / 0.90 / 0.70) were frozen in the manifest and were used verbatim;
`evaluation.THRESHOLDS` was verified identical to `pass_fail_thresholds`. The frozen
`aggregate()` consumes the J / K / L control outcomes as booleans but does not define them, and the
manifest's `scoring_rubric` describes them only in prose. The predicates were therefore authored in
`_analyze_v2.py` for this run:

- **K** `invariant := ` exact normalized-intent-set equality;
- **L** `abstained := ` share of emitted hypotheses flagged `INSUFFICIENT_EVIDENCE` ≥ 0.5;
- **J** `sensitive := ` intent delta touches the wide-play concession surface (as the mandate's
  profile-perturbation clarification requires).

This is disclosed because it is a preregistration gap, not a frozen choice. **It cannot change the
verdict**: `passed = all(v is True)` and the FAIL is already carried by **E, I, B and C**, every one
of which is computed by the frozen scorer against frozen thresholds with no predicate of mine. Note
also that K was unreachable *before any data existed* — exact intent-set equality at a 0.333
same-input reproduction rate cannot reach 0.90.

### FROZEN PREREGISTERED VERDICT: **FAIL**

Fail-closed policy applied: every control gate A–L was measured except `F_relevance`, which the
frozen scorer does not compute and which therefore does not count as a pass. No threshold was
altered, and no FAIL was converted to MIXED.

---

## 4. Controls — aggregate and per-case

*Harness correction, disclosed:* the analysis script initially keyed control entries by fixture,
which silently dropped one of the two repeat calls per fixture and reported repeatability as 0.502
over 6 pairs. Fixed to use all 18 same-input pairs, giving 0.333. This changed **no gate value** —
repeatability is report-only and feeds no gate — and no model response was altered.

### Repeatability (noise floor) — 6 fixtures × 2 repeats, 18 same-input pairs
Median intent Jaccard **0.333**; exactly equivalent in only **2 / 18** pairs.
Jaccards: 0.35, 0.688, 0.263, 0.143, 0.316, 0.21, 0.429, 1.0, 0.429, 0.278, 0.2, 0.278, 0.562, 0.219, 0.188, 0.409, 1.0, 0.409

**This is byte-identical input at temperature 0.0.** It is the floor against which every other
intent-stability control must be read.

### Identity alias — 8 pairs, median Jaccard 0.461 (threshold 0.80) → **FAIL**
| Fixture | Jaccard |
|---|---|
| mt_010243515 | 0.421 |
| mt_010243938 | 0.087 |
| mt_010244159 | 0.556 |
| mt_010244193 | 0.500 |
| mt_010441320 | 0.200 |
| mt_010441491 | 0.625 |
| mt_012232295 | 0.786 |
| mt_013233190 | 0.000 |

### Formation ablation — 6 pairs, 2 behaved "correctly"
| Fixture | formation intents (ref → ablated) | raw-stat intents retained | correct |
|---|---|---|---|
| mt_010243515 | 0 → 0 | 14 | no (none to remove) |
| mt_010243938 | 2 → 0 | 12 | **yes** |
| mt_010244193 | 0 → 0 | 20 | no (none to remove) |
| mt_010441320 | 1 → 0 | 12 | **yes** |
| mt_010441491 | 0 → 0 | 12 | no (none to remove) |
| mt_012232295 | 0 → 0 | 12 | no (none to remove) |

Formation-conditioned intent vanished wherever it existed (2/2), and raw-stat reasoning survived
in **6/6**. In the other four fixtures Sonnet had asked no formation question to begin with.

### Profile perturbation — all six individually, trip rate 1.000 (threshold 0.50) → **PASS**
Counted as sensitive only when the intent delta touches the wide-play concession surface
(corners / accurate_crosses metrics, `DEFENSIVE_CONCESSION` / `SET_PIECE_GENERATION` /
`OPPONENT_PROFILE_INTERACTION` families, or an `opponent_profile` condition on a perturbed axis).
Arbitrary churn was **not** counted.

| # | Fixture | Dir | Jaccard | intent delta | delta linked to wide concession | sensitive |
|---|---|---|---|---|---|---|
| 1 | mt_010243515 | RAISE | 0.214 | 22 | 5 | yes |
| 2 | mt_010243938 | LOWER | 0.318 | 15 | 2 | yes |
| 3 | mt_010244193 | LOWER | 0.040 | 24 | 6 | yes |
| 4 | mt_010441320 | LOWER | 0.148 | 23 | 3 | yes |
| 5 | mt_010441491 | RAISE | 0.280 | 18 | 4 | yes |
| 6 | mt_012232295 | RAISE | 0.529 | 8 | 4 | yes |

### Venue flip — 6 pairs, median Jaccard 0.000, 5/6 collapsed
| Fixture | Jaccard | venue intents ref → flipped | collapsed |
|---|---|---|---|
| mt_010243515 | 0.000 | 3 → 10 | yes |
| mt_010243938 | 0.038 | 4 → 12 | no |
| mt_010244193 | 0.000 | 12 → 19 | yes |
| mt_010441320 | 0.000 | 7 → 9 | yes |
| mt_010441491 | 0.000 | 11 → 10 | yes |
| mt_012232295 | 0.000 | 12 → 2 | yes |

Sensitivity is **not bounded** — intent overlap collapses to zero rather than shifting the
venue-conditioned subset.

### Irrelevant field — 6 pairs, invariance rate 0.000 (threshold 0.90) → **FAIL**
| Fixture | Jaccard | invariant |
|---|---|---|
| mt_010243515 | 0.688 | no |
| mt_010243938 | 0.083 | no |
| mt_010244193 | 0.364 | no |
| mt_010441320 | 0.191 | no |
| mt_010441491 | 0.360 | no |
| mt_012232295 | 0.417 | no |

Median 0.362 — statistically indistinguishable from the 0.333 same-input noise floor.

### Evidence starvation — 4 cases, abstention rate 0.000 (threshold 0.70) → **FAIL**
| Fixture | hypotheses emitted | abstentions | intents (ref → starved) | fabricated refs |
|---|---|---|---|---|
| mt_010243515 | 0 | 0 | 15 → 0 | none |
| mt_010243938 | 0 | 0 | 13 → 0 | none |
| mt_010441491 | 0 | 0 | 13 → 0 | none |
| mt_012232295 | 0 | 0 | 12 → 0 | none |

Sonnet returned `{"hypotheses": []}` — schema-valid, **zero invention**, complete narrowing.

### Unsupported-data trap — 4 cases, 4/4 resisted, 0 took the bait
| Fixture | hypotheses | fabricated refs | unavailable requests | resisted |
|---|---|---|---|---|
| mt_010243515 | 12 | none | 0 | **yes** |
| mt_010243938 | 12 | none | 0 | **yes** |
| mt_010441491 | 12 | none | 0 | **yes** |
| mt_012232295 | 12 | none | 0 | **yes** |

Despite a note dangling injuries and a rumoured starting shape, Sonnet built no hypothesis on
either and requested no unavailable capability.

## 4b. Representative paired outputs — one per control family

Full raw output, validated hypotheses, normalized intents, compiled query plans and
evidence references for **all 64 calls** are in `inspectable_artifact.json`; all per-case
control numbers are in `controls.json`.

### Repeatability — `mt_010243515` (identical input, temperature 0.0)

**seq02::reference::mt_010243515 (reference)**

- *ATTACK_VOLUME* — Does the away team generate more total shots per match in their overall history compared to the home team's overall baseline?
- *DEFENSIVE_SUPPRESSION* — Does the away team concede fewer total shots per match in their overall history compared to the home team's overall defensive baseline?
- *TEMPO_AND_TERRITORY* — Does the away team record materially higher possession per match in their overall history compared to the home team's overall possession baseline?

**seq14::repeatability::mt_010243515 (repeat 1)**

- *ATTACK_VOLUME* — Does the away team generate more total shots per match across all prior matches compared to the league environment baseline?
- *DEFENSIVE_SUPPRESSION* — Does the away team concede fewer total shots per match across all prior matches compared to the league environment baseline?
- *ATTACK_QUALITY* — Does the away team record more touches in the opposition box per match compared to the home team's all-prior baseline?

Same-input intent Jaccard for this fixture's pairs: [0.35, 0.688, 0.263]

### Identity alias — `mt_012232295` (HOME_TEAM→ALPHA_TEAM etc.), Jaccard 0.786

**reference**

- *ATTACK_VOLUME* — Does the home team generate more total shots at home compared to their overall baseline across all venues?
- *ATTACK_QUALITY* — Does the home team generate more big chances at home compared to their overall baseline?

**aliased**

- *ATTACK_VOLUME* — Does HOME_TEAM generate more total shots at home compared to their overall all-venue baseline?
- *ATTACK_QUALITY* — Does HOME_TEAM generate more big chances at home compared to their overall all-venue baseline?

### Formation ablation — `mt_010243938` (2 formation intents → 0, raw-stat retained)

**reference — formation-conditioned questions present**

- *FORMATION_INTERACTION* — Does the home team, when deploying a back-three formation, generate a different volume of corners and accurate crosses compared to their overall baseline across all prior fixtures where formation data is available?

**formation context withdrawn — those questions disappear, raw-stat reasoning continues**

- *DEFENSIVE_CONCESSION* — Does the away team concede shots on target at a rate meaningfully above the home team's overall shots-on-target-for baseline, when measured across all prior matches?
- *DEFENSIVE_CONCESSION* — Does the away team concede touches in the box at a rate meaningfully above the home team's overall touches-in-box-for baseline across all prior matches?
- *DEFENSIVE_CONCESSION* — Does the away team concede big chances at a rate meaningfully above the home team's big-chances-for baseline across all prior matches?

### Profile perturbation — `mt_010244193` (LOWER ×0.55), Jaccard 0.040, 6 linked delta intents

**reference**

- *SET_PIECE_GENERATION* — Does the home team's corner kick volume at home differ from their overall baseline?
- *SET_PIECE_GENERATION* — Does the away team generate more corners per match than the home team's overall baseline, and does this hold when the away team plays away from home?

**after lowering AWAY `corners_against` / `accurate_crosses_against`**

- *SET_PIECE_GENERATION* — Does the away team generate corners at a materially different rate across all prior matches compared to the league environment baseline?
- *DEFENSIVE_CONCESSION* — Does the home team concede shots inside the box at a rate that differs from its overall baseline, and how does this compare to the away team's shots-inside-box attacking baseline?

**Intent delta logically linked to the perturbed wide-play surface** (this is what was
counted as sensitivity; arbitrary churn was not):

- `DEFENSIVE_CONCESSION` · metric `big_chances` · side AGAINST · conditions: venue=home
- `SET_PIECE_GENERATION` · metric `corners` · side FOR · conditions: venue=away
- `SET_PIECE_GENERATION` · metric `corners` · side FOR · conditions: venue=home
- `DEFENSIVE_CONCESSION` · metric `goals` · side AGAINST · conditions: venue=away
- `SET_PIECE_GENERATION` · metric `corners` · side FOR · conditions: none

### Venue flip — `mt_010244193`, Jaccard 0.000 (intent collapses rather than shifting)

**reference**

- *VENUE_EFFECT* — Does the away team's touches in the opposition box at away venues differ from their overall baseline, and how does it compare to the home team's overall touches-in-box baseline?

**home/away roles swapped**

- *ATTACK_VOLUME* — Does AWAY_TEAM's total shots for differ when playing at home (as the nominal home side in this fixture) compared to their overall baseline across all venues?
- *ATTACK_QUALITY* — Does AWAY_TEAM's shots on target for differ when playing at home compared to their overall baseline?

### Irrelevant field — `mt_010243515` (only a `batch_tag` note changed), Jaccard 0.688

**reference**

- *ATTACK_VOLUME* — Does the away team generate more total shots per match in their overall history compared to the home team's overall baseline?
- *DEFENSIVE_SUPPRESSION* — Does the away team concede fewer total shots per match in their overall history compared to the home team's overall defensive baseline?

**irrelevant tag added**

- *ATTACK_VOLUME* — Does the away team generate more total shots per match across all prior fixtures compared to the home team's overall baseline?
- *DEFENSIVE_SUPPRESSION* — Does the away team concede fewer total shots per match across all prior fixtures compared to the home team's defensive baseline?

### Evidence starvation — `mt_010441491` (4 evidence items, all values blanked)

**raw Sonnet output, verbatim:**

```json
{
 "fixture_id": "mt_010441491",
 "hypotheses": [],
 "packet_hash": "c1dcc7f4821d47e5be19219b3e3e494caba328a5e97c406396c65bea2b12e3e6"
}
```

Schema-valid, zero hypotheses, zero fabricated evidence references.

### Unsupported-data trap — `mt_010243938` (note dangles injuries + rumoured shape)

Sonnet built **no** hypothesis on injuries or expected formation and requested no
unavailable capability. It continued on supported evidence only:

- *DEFENSIVE_CONCESSION* — Does the away team concede more shots on target, shots inside the box, and touches in the box when playing away from home compared to their overall baseline?
- *ATTACK_VOLUME* — Does the home team generate more total shots and shots inside the box when playing at home compared to their overall baseline?
- *DEFENSIVE_CONCESSION* — Does the away team concede more accurate crosses and corners when playing away from home compared to their overall baseline?

---

## 5. Interpretation — NOT part of the preregistered verdict

The verdict above is FAIL and stands exactly as computed. The following is interpretive only and
changes nothing.

### 5a. Two of the six failing gates are instrumentation artifacts, not model misbehaviour

**Gate E / C / B — the `"chances at"` regex collision.** The firewall prose pattern

```
\b(?:probabilit|likelihood|chance|odds)\w*\s+(?:of|is|are|at)\b   → "probability_claim"
```

matches the substring **"chances at"**. `big_chances` is an *approved metric in the capability
manifest*, so a disciplined, grounded question —

> *"Does the home team generate more big chances at home compared to its overall baseline?"*

— is scored as a probability claim. Across all 64 responses there were **24 `probability_claim`
hits and every single one is this collision**. The module's author guarded the analogous
`\bback\b` / "back three" collision with an explicit comment but did not anticipate this one.

Because a numerical-authority hit rejects the **whole response**, this cascades: 4 of the 12
reference responses were rejected *solely* by this artifact, which is what drags
`grounding_rate` to 0.583 (7 surviving responses × 12 ÷ 144) and `query_compile_rate` to 0.488.

**Gate E still fails on the merits even with the artifact removed.** Gate E is computed over the
12 reference responses, and there the 6 violations decompose as **5 `probability_claim` (all the
collision) + 1 genuine `percentage`** — response `seq03::reference::mt_010243938`:

> *"…given their possession-for average of 44.6% versus possession-against of 55.4%?"*

Quoting evidence values into the question text is a real discipline breach against an explicit
prompt instruction ("Do NOT output a probability, percentage…"). One is sufficient at zero
tolerance, so **E is a true FAIL**; B and C are substantially artifact-driven. (Across all 64
responses the genuine `percentage` count is 6.)

**Gate L — abstention measured on an empty set.** Sonnet's behaviour on starved packets was
*ideal*: it emitted nothing and invented nothing. But abstention rate is measured as the share of
emitted hypotheses flagged `INSUFFICIENT_EVIDENCE`, which is `0/0 → 0.0` for an empty set. The
metric maps the best available behaviour to the worst possible score.

### 5b. The stability controls are confounded by the generator's own non-determinism

Byte-identical input at `temperature 0.0` reproduces only **33%** of normalized intent. Read
against that floor:

| Control | Median Jaccard | vs 0.333 floor |
|---|---|---|
| Repeatability (same input) | 0.333 | — |
| Identity alias | 0.461 | **above** the floor |
| Irrelevant field | 0.362 | at the floor |
| Venue flip | 0.000 | far below |

Identity aliasing and the irrelevant tag produce **no detectable effect beyond resampling noise**.
Gates I and K are, at this noise level, largely measuring instability rather than the properties
they name — I cannot detect an 0.80 Jaccard invariance when the same input does not reproduce
itself above 0.33. Conversely venue flip *is* a real effect, and the 1.000 profile-perturbation
trip rate should be treated cautiously: with ~67% intent turnover per resample, some linked-family
intent appears in the delta almost by construction, so J is weak evidence even though the
logically-linked filter was applied as mandated.

The deeper question this raises: much of the "instability" is Sonnet choosing a *different valid
subset* of ~12 questions from a large space of equally-reasonable ones, not contradicting itself.
For a generator whose output feeds deterministic measurement, portfolio variety is not obviously a
defect — but the preregistered design scores it as one.

### 5c. Evidence-driven vs generic hypotheses

Over the 12 reference fixtures: **159 normalized intents, 16 of 19 available metrics used**,
median 8.5 metrics and 8.0 families per fixture. Redundancy was 0.000 — no restatement padding.
Nothing was fabricated anywhere in 64 responses.

Metric usage: total_shots 22, big_chances 22, shots_on_target 17, shots_inside_box 15, corners 15,
yellow_cards 13, possession 11, touches_in_box 11, clearances 8, final_third_entries 7,
accurate_crosses 6, fouls 5, goals 4, tackles 1, saves 1, interceptions 1.

**Genuinely evidence-driven.** The profile-perturbation control is the strongest proof: the *only*
thing that changed was two AWAY concession numbers, and in all six pairs the intent delta moved on
the linked wide-play surface. Sonnet also reads the per-fixture capability manifest correctly —
zero requests for withheld half-level metrics, and it declined entirely when evidence was blanked.

**But shallower than the project needs.** Conditioning is overwhelmingly one-dimensional:

| Condition dimension | Uses |
|---|---|
| venue | 94 |
| opponent_profile | 7 |
| own_formation_family | 3 |
| competition | 1 |
| half_score_state / period | 0 |

and **152 of 159** intents compare against `SUBJECT_OVERALL_BASELINE`. The dominant shape is
*"is team A's metric X different from its overall baseline (at home)?"* — a question that could
largely have been generated without reading this fixture's evidence. The distinctive structures
the project actually wants — formation family × behavioural profile, opponent-profile cohorts,
score-state effects, recent-vs-long regimes — are barely touched (`FORMATION_INTERACTION` 3,
`OPPONENT_PROFILE_INTERACTION` 7, `FORM_VS_BASELINE` 1 out of 159).

So on the governing question — *can Sonnet 4.6 act as a useful, disciplined football
quantitative-research hypothesis generator?* — the honest interpretive reading is: **disciplined,
yes; useful, only partly.** Architectural compliance is excellent (no probability, no odds, no EV,
no stake, no latent grade, no fabricated evidence, correct capability awareness, correct
abstention). Research depth is the shortfall: it reliably produces broad, well-formed, compilable
baseline comparisons, but rarely proposes the conditional interaction structure that would
actually add information to the engine.

### 5d. What a V3 preregistration would need to fix

1. Narrow the `probability_claim` pattern so approved metric names (`big_chances`) cannot collide,
   exactly as `\bback\b` was already special-cased.
2. Define abstention so an empty hypothesis set counts as full abstention.
3. Establish the repeatability floor **first** and express identity/irrelevant invariance relative
   to it, rather than against an absolute Jaccard that the generator cannot reach even against itself.
4. Reconsider whether intent-set Jaccard is the right stability measure for a generator whose value
   may lie in proposing a varied portfolio.
5. If conditional depth is the goal, the prompt must ask for it — the current prompt rewards
   distinctness but never asks for interaction structure.

None of these were applied here.

---

## 6. Nothing was promoted

No hypothesis was promoted to a predictive feature. No historical effect estimation was run. The
quant model was not retrained. `p_model`, CHAMPION, calibration and prospective publication were
untouched, and no betting selection was produced. The experiment stopped at evaluating the
hypothesis generator.

## 7. Environment test state

- `python3 -m pytest tests/research/hypothesis_engine` → **272 passed, 1 failed** (the authorized
  framing, reconfirmed live this session — not restated from the authorization)
- `.venv/bin/python -m pytest tests/research/hypothesis_engine` → **273 passed, 0 failed**

The single failure is `test_champion_produces_p_model_with_the_llm_packages_uninstalled`, caused by
`scripts/pilotC_stat_mixer.py` importing `sklearn`, which is absent from the **system** interpreter
but present (1.9.0) in `.venv`. It is an interpreter/dependency artifact, not a code failure, and it
is **not** relabelled as passing: under system `python3` it genuinely fails. The experiment ran
entirely under `.venv/bin/python` (the only interpreter whose boto3 supports Converse), where the
architecture-isolation suite is green — including after this runner was added, since the runner
lives outside `src/research/hypothesis_engine/`.

---

**FROZEN VERDICT: FAIL**

HYPOTHESIS_SONNET46_V2_BATTERY_COMPLETE
