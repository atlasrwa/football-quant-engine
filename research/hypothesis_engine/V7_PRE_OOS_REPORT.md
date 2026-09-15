# V7_DETERMINISTIC_HYPOTHESIS_VALIDATION — Pre-OOS Report

**Executive verdict: `V7_PRE_OOS_READY`**
Confirmatory OOS **not computed**. `V7_OOS_EXECUTION_AUTHORIZATION_REQUIRED`. STOP.

Zero spend. No Bedrock call. No LLM effect estimation. CHAMPION unchanged
(`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9`, verified before and after).

---

## 0. Status of the prior V7 freeze

An earlier V7 apparatus existed (untracked, `V7_PRE_OOS_READY`, 29/132 measurable). It had
**not** computed any OOS result (`confirmatory_oos_computed: false`, no effects in any
artifact), so re-deriving the pre-OOS apparatus violated no freeze. Auditing it surfaced four
defects, three of them scientific. They are recorded here because the deltas are themselves
findings about the prior apparatus.

### D1 — Provider provenance was factually wrong (most serious)

v1 labelled `MatchRecord.base` as **FootyStats** and `MatchRecord.rich` as **TheStatsAPI**, and
refused to measure any hypothesis whose metrics spanned them.

Evidence that this is wrong:
- `multisrc_corpus._to_adapter_shape` — *"Map a **TheStatsAPI fixture** → the shape `adapt_match` wants"*
- `championship_adapter.adapt_match(fixture, stats_json)` reads **every** stat field
  (`yellow_cards`, `fouls`, `shots_on_target`, `expected_goals`, …) out of that one
  `stats_json`, and merely renders it in a FootyStats-*shaped* schema.

`base`, `rich` and `extra` are three **storage blocks of one provider**. No FootyStats value is
ever loaded. The phantom split rejected **33 canonical families** for "targets span multiple
providers" — a distinction that does not exist in this corpus. Because the two arms name
different metric mixes, that pruning was **arm-correlated**, biasing the Phase 20/21 control
comparison, which is V7's primary endpoint.

The no-pooling rule is **retained as a live invariant** (the real `DO_NOT_MERGE` hazards in
`hypothesis_engine.capability` — `xg@footystats~xg@thestatsapi` corr 0.55,
`total_shots@...` corr 0.80 — remain real for any future mixed corpus). It is now asserted with
evidence and proven not to fire here.

### D2 — Real corpus fields were declared non-existent

| metric | v1 verdict | measured coverage | corpus binding |
|---|---|---|---|
| `shots` (total) | "no single audited total-shots field" → 47 families excluded | **0.996** | `extra.total_shots` |
| `possession` | "no audited per-side possession field" → 9 excluded | **0.995** | `extra.possession` |
| `saves` | absent from contract → 4 excluded | **0.990** | `rich.saves` |

All three are loaded by `corpus.load_corpus()` and already mapped in
`hypothesis_engine.corpus_adapter._METRIC_SOURCE`.

Accounting for the whole correction: v1 declared 103 families non-measurable (89 provider +
10 compiler + 4 missing-field). D1+D2 recovered families blocked by the phantom provider split
and the three phantom-missing fields; the comparator fix (§5) recovered the 10 compiler rows.
Net, the measurable count moved **29 → 53 (+24)** and the non-measurable residual fell
**103 → 79**, now attributable entirely to two genuinely low-coverage metrics.

### D3 — A league-broken metric was marked measurable *and* used as a similarity dimension

`xg` was `audited: True` / MEASURABLE with **no competition restriction**, and was a frozen
similarity dimension (`xg_conceded_per_match`). Measured coverage:

| | champ | epl | laliga | laliga2 | ligue1 | ligue2 |
|---|---|---|---|---|---|---|
| `xg` | 0.995 | 1.000 | 1.000 | **0.452** | 0.998 | **0.000** |
| `touches_in_penalty_area` | **0.673** | 1.000 | 0.995 | 1.000 | 0.997 | 0.995 |

This is precisely the Phase 25 failure mode: every Ligue 2 team profile would have had that
dimension imputed to the cohort mean (z=0) while EPL profiles carried a real value — a silent,
**league-correlated** distortion of the distance metric that `MAX_MISSING_DIMS = 1` waved
through.

### D4 — Declared spec did not describe the code

`PROFILE_SHRINKAGE_K = 8.0` was published in the frozen similarity spec but `team_profile()`
never applied it. Now applied and unit-tested.

---

## 1. V6.1 hypothesis universe (immutable)

Phase 0 discharged: V6.1 execution is **genuine**, not a dry run — 36 raw responses carry real
AWS request IDs, HTTP 200s, real `usage` token counts and `latencyMs`, with a 36-entry billing
ledger totalling **$6.872679** confirmed spend against an $8.52 ceiling.
(`V6_1_STATES.json` reports 0 calls because it is the *pre-spend* states file, written before
authorization; `execution/execution_summary.json` records `V6_1_EXECUTION_COMPLETE`.)

| quantity | value |
|---|---|
| qualified hypotheses | **149** (base **51**, research **98**) |
| canonical families | **132** |
| duplicates collapsed | **30** (all `STRUCTURAL_DUPLICATE`) |
| families base-only | 44 |
| families research-only | 88 |
| **families in BOTH arms** | **0** |

Extraction is mechanical: included iff the frozen V6.1 scorecard row has `qualified is True`.
No selection by persuasiveness, no re-adjudication, no effect inspected.

### Measurability (corrected)

| class | v1 | **v2** |
|---|---|---|
| MEASURABLE | 29 (22.0%) | **53 (40.2%)** |
| UNMEASURABLE_COVERAGE | – | **79** |
| UNMEASURABLE_PROVIDER | 89 | 0 |
| UNMEASURABLE_COMPILER | 10 | 0 |
| UNMEASURABLE_MISSING_FIELD | 4 | 0 |

The entire residual is now attributable to **two coverage-failing metrics**, each reported with
the leagues that fail and why.

> **Finding.** 79/132 (59.8%) of V6.1 canonical families name at least one coverage-failing
> metric. The driver is exactly two: `xg` (58 families) and `touches_in_penalty_area` (44).
> The other two rejected metrics, `np_xg` and `offsides`, appear in **0** V6.1 families, so the
> figure is identical whether computed over the full rejected set or over those two alone.
> Against the same rejected set the deterministic null names one in 164/400 (41.0%) of its
> families. The LLM disproportionately asked about the two metrics this corpus covers worst.
> This is descriptive, effect-blind, and recorded before OOS.

---

## 2. Canonicalization & deduplication

`canonical_hypothesis_id = SHA256(canonical_spec)`, structural fields only — metrics normalized
through a frozen synonym map; subject/side/comparator/window/family/conditions/capabilities
order-normalized. No wording, no LLM, no outcome. Distinct canonical ids are **never merged**
(`NEAR_EQUIVALENT_NOT_MERGED` is never collapsed). One canonical question = one family identity;
origin multiplicity is metadata and adds no statistical weight (test 01).

Canonical slots: `TARGET, SUBJECT, SIDE, COMPARATOR, CONDITIONS, TIME_SCOPE,
SIMILARITY_DIMENSIONS, FAMILY, PROVIDER_REQUIREMENTS`.

---

## 3. Provider support & coverage (Phase 6 / 25)

Single provider **TheStatsAPI**; 5319 matches, 6 competitions, 13 season-instances,
2023-08-04 → 2026-05-31. Frozen gate: ≥0.95 overall **and** ≥0.95 in **every one of the 6**
competitions.

**Admitted (21):** goals, red_cards (1.000); shots, corner_kicks, possession, shots_on_target,
shots_inside_box, shots_outside_box, shots_off_target, blocked_shots, accurate_crosses,
tackles, interceptions, clearances, final_third_entries, ball_recoveries (≥0.987 min);
saves, fouls (0.984); big_chances (0.959); yellow_cards, cards_2h (0.952).

**Rejected (4), with the failing leagues named:** `xg` (ligue2 0.000, laliga2 0.452),
`np_xg` (laliga2 0.381 — *and* unaudited per-side split), `touches_in_penalty_area`
(champ 0.673), `offsides` (epl/ligue1 <0.95). Only the first and third are ever named by a V6.1
hypothesis; `np_xg` and `offsides` are rejected pre-emptively and cost the universe nothing.

No restricted universe is applied silently: every exclusion carries its competition list.

---

## 4. Similar-opponent engine (Phase 7)

Dimensions (all verified against the measured matrix, not asserted):
`goals_conceded`, `shots_on_target_conceded`, **`shots_inside_box_conceded`** (replaces the
removed `xg_conceded`), `fouls_committed`, `yellow_cards` — per match, PIT-safe.

Scaling `ZSCORE_PIT_TRAIN_ONLY` fitted on training past only; missing → cohort mean (z=0), max
1 missing dim; profile shrinkage k=8.0 toward the competition baseline **(applied)**; distance
family `{euclidean_z, manhattan_z}`, primary `euclidean_z`; K-nearest k=8; ≥6 prior matches;
tie-break `kickoff_unix_asc_then_fixture_id`; same-competition restriction. No per-hypothesis
threshold tuning. The LLM never produces a numeric similarity score.

---

## 5. Support, recency, confounders, multiplicity

**Support (frozen before effects):** raw N ≥20, unique fixtures ≥15, unique teams ≥6, Kish
effective N ≥10, max single-observation weight ≤0.25; classes `ADEQUATE / LOW / CONCENTRATED /
UNSTABLE / NOT_EVALUABLE`. Clustering + block bootstrap required for uncertainty (Phase 26).

**Recency:** preregistered decay family `{180d, 365d}` + shrinkage k=10 toward
`TEAM_COMPETITION_BASELINE`. `SUBJECT_RECENT_VS_LONG_BASELINE` is now compilable (it was 10
`UNMEASURABLE_COMPILER` rows) and flagged `requires_full_decay_family` — **both** half-lives are
reported; the better-looking one is never selected.

**Comparators:** 9 of 53 measurable families flagged `BASELINE_ABSORPTION` and rejected → 44
eligible candidates.

**Confounders:** by family, from a frozen allowed set (venue, competition, season_regime,
opponent_strength/profile, score_state, cards, formation, team_baseline_quality). The model's
own `candidate_confounders` are metadata only. No causal claim.

**Multiplicity:** BH-FDR per preregistered family at **q=0.10** + empirical-Bayes shrinkage
across 7 families. Promotion requires fold-direction-stable OOS survival **and** FDR
significance **and** a non-trivial shrunk effect. Nominal p<0.05 is never sufficient.

---

## 6. Walk-forward design (Phase 12/13)

Development 2023-08-04 → 2024-12-31 (apparatus validation only, never confirmatory).
Confirmatory 2025-01-01 → 2026-05-31, rolling-origin, 3-month blocks, retrain each fold from
past only, equal fold weighting. Random splitting is hard-disabled as primary evidence.

| fold | train end | validate end | train days |
|---|---|---|---|
| 0 | 2025-01-01 | 2025-04-01 | 515.2 |
| 1 | 2025-04-01 | 2025-06-30 | 605.2 |
| 2 | 2025-06-30 | 2025-09-28 | 695.2 |
| 3 | 2025-09-28 | 2025-12-27 | 785.2 |
| 4 | 2025-12-27 | 2026-03-27 | 875.2 |
| 5 | 2026-03-27 | 2026-05-31 | 965.2 |

All 6 satisfy the 365-day minimum history.

---

## 7. Control benchmark (Phase 20/21) — **the design change**

### Control A (arm-matched) is INFEASIBLE — determined before any OOS

Restricted to measurable families: **5 matched cells** across **3 fixtures**, 6 base / 7
research families — against frozen minima of 12 / 5 / 12. The direct cause is structural:

> **Not one canonical specification was generated by both arms** across all 10 fixtures
> (`n_families_both_arms = 0`). V6.1 was never constructed to yield matched pairs.

This is outcome-blind — cell membership is a pure function of the immutable V6.1 universe plus
the effect-blind measurability gate — so declaring it now is legitimate, and declaring it *after*
seeing folds would not have been. Per the fallback frozen in the same artifact, the arm contrast
is **demoted to descriptive** and may never be reported as a confirmatory arm effect.

### Control B (deterministic null) is the PRIMARY control

Phase 20 forbids testing V6.1 hypotheses in isolation, so with A infeasible V7 would have had
**no valid control at all** — a hard block. Control B, explicitly sanctioned by Phase 20, is
therefore built: 400 generic hypotheses enumerated deterministically over the same canonical
grammar via a SHA-256 counter stream (no LLM, no fixture-specific reasoning, PYTHONHASHSEED-
independent), pushed through the **identical** pipeline with no special-casing.

Fairness checks, frozen and outcome-blind:

| | V6.1 | null | gap | limit |
|---|---|---|---|---|
| measurability rate | 0.402 | 0.590 | 0.189 | ≤0.25 |
| comparator-reject rate | 0.170 | 0.123 | 0.047 | ≤0.25 |
| measurable families | 53 | 236 → **capped to 53** | — | balanced |

The null draws coverage-failing metrics too, so it faces the same hazards; slot vocabularies are
restricted to what V6.1 inhabits so it cannot lose on unused grammar; the balanced subset is
hash-ordered take-N at the V6.1 measurable count, so neither origin is rewarded for volume.

**Primary endpoint:** rate at which a canonical family reaches `OOS_SURVIVES`, V6.1-origin vs
`DETERMINISTIC_NULL`, on count-balanced measurable sets, with family/metric clustering.

---

## 8. Leakage audit (Phase 24)

11 mutation classes injected, **all rejected**; the legitimate PIT observation accepted:
`future_match_in_profile`, `post_cutoff_obs`, `at_cutoff_obs`, `target_in_baseline`,
`future_season_similarity`, `scaler_on_future_fold`, `forbidden_market_field`,
**`settlement_field`**, **`future_lineup_injury_field`**, **`shrinkage_hyperparam_on_future`**,
**`target_fixture_own_stat`** (last four added this pass).

---

## 9. Candidate lock & no-peeking (Phase 22/23)

`candidate_lock_sha256 = 75c7c3101dfe3a2f…` over the 44 ordered canonical eligible specs,
recomputable from the frozen artifact (test asserts the round-trip). Computed **before** any OOS;
`confirmatory_oos_computed: false` in the preregistration. Any post-OOS change to a candidate
invalidates its confirmatory status.

---

## 10. Reproducibility (Phase 31)

All **19** artifacts byte-identical under `PYTHONHASHSEED = 1, 2, 3, 12345`, and identical again
under a second interpreter (`.venv/bin/python`). No `random`, no Python `hash()`; the null
benchmark uses a SHA-256 counter stream with a frozen seed.

---

## 11. Tests

`tests/research/hypothesis_oos/test_v7_pre_oos.py` — **48 passed, 0 skipped, 0 xfail** (`-rs`).
Full `tests/research/hypothesis_oos/` — **403 passed, 0 skipped, 0 xfail**.

All 22 Phase 32 adversarial cases map to a named test. Four repairs were needed, and each was a
test that passed without testing anything:

- `test_03` / `test_20` asserted the **v1 mislabel**. Rewritten to pin the corrected invariants
  in both directions — single-provider evidence, cross-block pooling allowed, and the guard
  still firing when providers genuinely differ. `test_03d` added so the
  `UNMEASURABLE_PROVIDER` verdict is shown to be genuinely reachable (`cards`, `np_xg`) rather
  than vestigial after the correction.
- `test_04` (case 4, unsafe temporal resolution) passed a metric **absent from the contract**,
  so it returned `UNMEASURABLE_MISSING_FIELD` and never reached the half-resolution branch.
  Since `cards_2h` is the only half-resolution metric and it *is* supported, that guard was
  unreachable in tests. Now exercised by injecting an unsupported half metric and asserting
  `UNMEASURABLE_TEMPORAL_RESOLUTION` specifically.
- `test_22` (case 22, CHAMPION write attempt) checked the hash and import isolation but never a
  write attempt, and omitted two modules. Extended with `test_22b` (no V7 module opens any file
  for writing or names a production path — verified by AST over all 11 modules) and `test_22c`
  (the freeze driver's CHAMPION guard fails **closed**: a mismatch appends a blocking problem,
  which forces `V7_PRE_OOS_BLOCKED` with no states emitted).

The broader `tests/research/` suite was started but exceeded the wait window and was stopped;
it is outside V7's blast radius — `grep -rln "hypothesis_v7"` matches only `_freeze_v7.py` and
`test_v7_pre_oos.py`, and V7 only *reads* `corpus_adapter` / `matchup.corpus`. It is reported
here as not-run, not as passing.

---

## 12. CHAMPION isolation (Phase 29)

Hash unchanged before and after. AST-based executable-code check (docstrings stripped, so a
docstring saying "no p_model" is not itself a violation) across all 11 V7 modules: no reference
to `pilotC`, `stat_mixer` or `p_model`. `auto_promotion: false`; V7 writes no production feature
config and does not modify `p_model`. V7 writes only under `research/hypothesis_oos/out/v7/`.

---

## 13. Final states

```
V7_V6_1_HISTORY_FROZEN              V7_SUPPORT_RULES_FROZEN
V7_HYPOTHESIS_UNIVERSE_FROZEN       V7_CONFOUNDER_PLAN_FROZEN
V7_CANONICALIZATION_VALIDATED       V7_MULTIPLICITY_PLAN_FROZEN
V7_DEDUPLICATION_VALIDATED          V7_WALKFORWARD_DESIGN_FROZEN
V7_MEASURABILITY_RULES_FROZEN       V7_CONTROL_COMPARISON_FROZEN
V7_PROVIDER_SEMANTICS_VALIDATED     V7_EVALUATOR_FROZEN
V7_PIT_ENGINE_VALIDATED             V7_CHAMPION_ISOLATED
V7_SIMILARITY_ENGINE_VALIDATED      V7_FULLY_PREREGISTERED
                                    V7_OOS_EXECUTION_AUTHORIZATION_REQUIRED
```

**STOP.** Do not compute confirmatory OOS results until explicitly authorized.
