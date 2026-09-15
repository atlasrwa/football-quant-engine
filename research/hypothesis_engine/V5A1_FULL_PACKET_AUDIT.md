# V5A.1 Full Packet Audit

**Experiment:** `V5A.1_FULL_FIDELITY_EVIDENCE_INTERFACE`
**Date:** 2026-09-14 · **Spend:** $0 · **Bedrock/LLM/network calls:** 0
**Predecessor:** V5A — `ABORTED_PRE_SPEND`, artifacts preserved unchanged

Companion documents: `V5A1_EVIDENCE_INTERFACE_DESIGN.md`, `V5A1_PROVIDER_SEMANTICS_AUDIT.md`.

---

## 1. Artifacts

| path | role |
|---|---|
| `research/hypothesis_oos/out/v5a1/packets_base.json` | base-arm packets, 10 fixtures |
| `research/hypothesis_oos/out/v5a1/packets_research.json` | research-arm packets, 10 fixtures |
| `research/hypothesis_oos/out/v5a1/PREREGISTRATION.json` | machine-readable preregistration + frozen request manifest + cost model |
| `research/hypothesis_oos/out/v5a1/exposure_audit.json` | history exposure, cell fidelity |
| `research/hypothesis_oos/out/v5a1/evidence_id_audit.json` | valid ids, duplicates, alias collisions |
| `research/hypothesis_oos/out/v5a1/ab_isolation_audit.json` | superset proof, admissible surfaces |
| `research/hypothesis_oos/out/v5a1/section_position_audit.json` | measured byte offsets of every section |
| `tests/research/hypothesis_oos/test_v5a1_prespend.py` | 45-test pre-spend battery |

---

## 2. Fixture set (§26)

The V5A eligible set, unchanged. `mt_013233190` remains excluded for the same deterministic
pre-spend reason — too little prior history — now measured against the **full PIT-safe
universe** (4 prior matches per team, against a floor of 6) rather than against the raw-row
cap. No fixture was removed for anything to do with hypothesis quality, V4 results, outcomes
or model behaviour. The exclusion is symmetric across arms and recorded in the exposure audit.

**10 paired fixtures.**

---

## 3. Per-fixture packet inventory

| fixture | base bytes | base tok | research bytes | research tok | base ids | research ids | rows | metric cells | PIT prior H/A | raw % | summary % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| mt_010243515 | 35,237 | 19,239 | 130,873 | 71,456 | 109 | 3,361 | 60 | 2,760 | 40/40 | 30.0 | 51.9 |
| mt_010243537 | 35,341 | 19,296 | 131,102 | 71,581 | 109 | 3,361 | 60 | 2,760 | 104/50 | 29.9 | 52.0 |
| mt_010243938 | 35,369 | 19,311 | 131,443 | 71,767 | 109 | 3,361 | 60 | 2,760 | 69/70 | 29.9 | 52.1 |
| mt_010244159 | 35,385 | 19,320 | 131,456 | 71,774 | 109 | 3,361 | 60 | 2,760 | 71/71 | 29.9 | 52.1 |
| mt_010244193 | 35,394 | 19,325 | 131,385 | 71,736 | 109 | 3,361 | 60 | 2,760 | 67/67 | 29.9 | 52.1 |
| mt_010441320 | 35,382 | 19,318 | 131,422 | 71,756 | 109 | 3,361 | 60 | 2,760 | 64/64 | 30.0 | 52.1 |
| mt_010441491 | 35,384 | 19,319 | 131,706 | 71,911 | 109 | 3,361 | 60 | 2,760 | 37/79 | 29.9 | 52.1 |
| mt_010444904 | 35,494 | 19,379 | 119,746 | 65,381 | 109 | 2,601 | 44 | 2,024 | 56/14 | 24.7 | 55.5 |
| mt_012232295 | 35,337 | 19,294 | 129,364 | 70,632 | 109 | 3,343 | 60 | 2,760 | 37/37 | 30.3 | 51.5 |
| mt_012232411 | 35,092 | 19,160 | 124,509 | 67,981 | 107 | 3,054 | 54 | 2,484 | 27/27 | 28.6 | 52.5 |

`VALID_EVIDENCE_IDS > 0` on every packet in both arms — the V5A HS-1 gate, cleared.

---

## 4. Evidence-reference integrity (§3, §13, §20)

| check | result |
|---|---|
| `duplicate_evidence_ids_zero` | **0**, both arms, 10/10 |
| `duplicate_match_aliases_zero` | **0**, 10/10 (V5A had 9 cross-team collisions over 7 fixtures) |
| duplicate ids fail construction | `DuplicateEvidenceId` raised, not warned |
| ids resolvable by the shared resolver | 107–109 base, 2,601–3,361 research |
| arm-specific reference mechanism | **none** — `packet.get("evidence")` appears nowhere in `validator_v3.py`; the same function serves both arms |
| ids human-readable | `MATCH:HOME:M01:corners_for`, `SUMMARY:AWAY:W5:ANY:shots_on_target_against` |

The id grammar, with examples and the rule that an id absent from the packet is not evidence,
is serialized as the final section of every packet.

### End-to-end grounding (§19), run before freezing

schema → `validator_v3` → `firewall_v3` → `query_plan.compile_hypothesis`, on real frozen
packets, in **both** arms. Positive cases: one match observation · several match observations
· one summary · a venue summary · a recent summary · opponent-profile evidence · formation
evidence. All accepted where the arm exposes them, and all compile. Negative cases: invalid
reference · cross-fixture payload · empty refs with `SUFFICIENT` · duplicate ids · excluded
metric · unsupported comparison · venue or W5 question against a base packet. All refused,
each with the specific reason. An honest `INSUFFICIENT_EVIDENCE` abstention with no refs is
accepted in both arms.

---

## 5. A/B isolation (§4, §5, §6)

| check | result |
|---|---|
| `RESEARCH_SUPERSET_OF_BASE` | **true, 10/10** |
| `BASE_IDS_NOT_IN_RESEARCH` | **empty, 10/10** — nothing the base arm receives is omitted |
| `N_UNEXPECTED_SHARED_VALUE_MISMATCHES` | **0** across all fixtures |
| `EXPECTED_AVAILABILITY_DIFFERENCES` | 40 (4 per fixture) — the exposure declarations §7 requires to differ |
| research-only ids | 2,492–3,252 per fixture |
| `same_base_history_universe` | ALL_PRIOR `sample_n` identical across arms, per evidence_id, 10/10 |
| `packet_schema_version` identical | `research_evidence_packet_v1` in both arms |
| system prompt identical | SHA-256 equal, asserted against the manifest |
| `no_visible_treatment_label` | no key or non-disclaimer value names a condition; no `arm` field |

Shared and asserted across arms: target fixtures · cutoff · provider corpus · canonical
metrics · **ALL_PRIOR historical universe (uncapped, both arms)** · team/opponent/competition
aliases · system prompt · user instruction · schema · validator · firewall · compiler · model
· temperature · max hypotheses · evidence-id format · evaluation.

**Treatment = exposed evidence only.**

---

## 6. History policy (§10)

`ALL_PRIOR` summaries use the entire PIT-safe history in **both** arms. Raw rows are a
separate, separately-declared visibility bound. The packet states both counts per team and
says explicitly that the rows are not the whole record.

| fixture | PIT prior H/A | rows serialized H/A | rows omitted by row policy H/A | ALL_PRIOR summary N range H/A |
|---|---|---|---|---|
| mt_010243515 | 40/40 | 30/30 | 10/10 | 36–40 / 36–40 |
| mt_010243537 | 104/50 | 30/30 | 74/20 | 97–104 / 47–50 |
| mt_010243938 | 69/70 | 30/30 | 39/40 | 65–69 / 66–70 |
| mt_010244159 | 71/71 | 30/30 | 41/41 | 66–71 / 65–71 |
| mt_010244193 | 67/67 | 30/30 | 37/37 | 64–67 / 63–67 |
| mt_010441320 | 64/64 | 30/30 | 34/34 | 63–64 / 62–64 |
| mt_010441491 | 37/79 | 30/30 | 7/49 | 36–37 / 74–79 |
| mt_010444904 | 56/14 | 30/14 | 26/0 | 53–56 / 13–14 |
| mt_012232295 | 37/37 | 30/30 | 7/7 | 34–37 / 34–37 |
| mt_012232411 | 27/27 | 27/27 | 0/0 | 25–27 / 24–27 |

(ALL_PRIOR `sample_n` falls below the universe only where a provider cell is null for that
metric — e.g. xG's 78.9% coverage. The gap is visible in `sample_n` on each summary row.)

---

## 7. Raw cell fidelity (§18)

Every model-visible `MATCH_OBSERVATION` cell was recomputed from the canonical record and
compared.

| measure | value |
|---|---|
| cells checked | **26,588** |
| mismatches | **0** |
| `UNEXPLAINED_OMISSION` | **0**, all fixtures |
| available vs visible | every admitted row is serialized in full; `admitted → serialized` rate 1.0 |
| omitted rows | only by the declared raw-row policy, counted per fixture in §6 |
| truncation markers (`"..."`, `…`, /truncat|elided|clipped/i) | **none** in any payload |
| row/column integrity | `n_rows == len(rows)` and `len(cells) == 46` for all 1,076 rows |

No shrinkage, no band substitution, no imputation, no HIGH/LOW transformation, no
LLM-generated normalization anywhere in the row path.

---

## 8. Section positions (§11) — measured, not estimated

Byte offsets located by finding each section's exact serialized substring in the payload.

**Research arm, `mt_010244159`:**

| § | section | bytes | start–end | % of packet |
|---|---|---:|---|---:|
| 1 | TARGET_FIXTURE_CONTEXT | 1,250 | 0.1%–1.1% | 0.9 |
| 2 | AVAILABILITY_MAP | 6,979 | 1.1%–6.4% | 5.3 |
| 3 | METRIC_SEMANTICS | 11,558 | 6.4%–15.2% | 8.8 |
| 4 | **MATCH_LEVEL_OBSERVATIONS** | **39,328** | **15.2%–45.1%** | **29.9** |
| 5 | DERIVED_SUMMARIES | 52,239 | 45.1%–84.8% | 39.7 |
| 6 | OPPONENT_PROFILE_SUMMARIES | 16,267 | 84.8%–97.2% | 12.4 |
| 7 | FORMATION_CONTEXT | 1,368 | 97.2%–98.3% | 1.0 |
| 8 | EVIDENCE_CITATION_INSTRUCTIONS | 2,192 | 98.3%–99.9% | 1.7 |

**Base arm, same fixture:**

| § | section | bytes | start–end |
|---|---|---:|---|
| 1 | TARGET_FIXTURE_CONTEXT | 1,151 | 0.5%–3.8% |
| 2 | AVAILABILITY_MAP | 7,474 | 3.8%–24.9% |
| 3 | METRIC_SEMANTICS | 11,558 | 24.9%–57.6% |
| 4 | DERIVED_SUMMARIES | 11,369 | 57.6%–89.7% |
| 5 | FORMATION_CONTEXT | 1,368 | 89.7%–93.6% |
| 6 | EVIDENCE_CITATION_INSTRUCTIONS | 2,192 | 93.6%–99.8% |

**Pre-spend gate: both teams' raw-history blocks end at 41.5–45.2%, before the first byte of
any derived summary. PASS, 10/10.** (V5A: rows at 81.5–95.9%, behind ~80% of summary bytes.)

### Byte distribution (§12)

| fixture | raw rows | summaries (derived + profile) | instructions | metadata (context + availability + semantics) | raw : summary |
|---|---:|---:|---:|---:|---|
| mt_010444904 (smallest) | 29,629 (24.7%) | 66,473 (55.5%) | 2,192 (1.8%) | 19,732 (16.5%) | **1 : 2.24** |
| mt_010243537 (median) | 39,265 (29.9%) | 68,216 (52.0%) | 2,192 (1.7%) | 19,747 (15.1%) | **1 : 1.74** |
| mt_010441491 (largest) | 39,440 (29.9%) | 68,644 (52.1%) | 2,192 (1.7%) | 19,760 (15.0%) | **1 : 1.74** |

V5A was **1 : 5.54 – 1 : 7.18** with rows at 11.5–14.4% of bytes. The improvement came from
structural deduplication — shared row and summary metadata declared once, metric semantics
defined once, `units` removed as a per-row column — not from removing football content. No
metric was dropped to improve the ratio; `npxg` was dropped for the semantic reason in the
provider audit.

**Reported, not optimised:** summaries still occupy about twice the bytes of the raw rows.
That is a design fact, not a target that was tuned.

---

## 9. Deep inspection — smallest / median / largest (§31)

Deterministic selection, rule fixed before content: sort by research-arm payload bytes
ascending, take index 0, index `floor((n−1)/2) = 4`, index 9. No ties.

| rank | fixture | bytes | selected |
|---:|---|---:|---|
| 0 | mt_010444904 | 119,746 | **SMALLEST** |
| 4 | mt_010243537 | 131,102 | **MEDIAN** |
| 9 | mt_010441491 | 131,706 | **LARGEST** |

| property | mt_010444904 | mt_010243537 | mt_010441491 |
|---|---|---|---|
| research bytes / tokens | 119,746 / 65,381 | 131,102 / 71,581 | 131,706 / 71,911 |
| match rows (H/A) | 30 / 14 | 30 / 30 | 30 / 30 |
| metric cells | 2,024 | 2,760 | 2,760 |
| null cells | 44 (2.2%) | 14 (0.5%) | 20 (0.7%) |
| PIT prior H/A | 56 / 14 | 104 / 50 | 37 / 79 |
| valid evidence ids | 2,601 | 3,361 | 3,361 |
| raw-row span | 16.7%–41.5% | 15.2%–45.2% | 15.2%–45.1% |
| first summary byte | 41.5% | 45.2% | 45.1% |
| raw : summary | 1 : 2.24 | 1 : 1.74 | 1 : 1.74 |
| profile cohorts / rows | 7 / 56 | 8 / 64 | 8 / 64 |
| formation coverage H/A | 0.214 / 0.286 | 0.106 / 0.160 | 0.324 / 0.165 |

### Readability checklist (§31)

| requirement | verdict |
|---|---|
| both teams clearly separated | **CLEAR** — `match_level_history` blocks keyed `HOME` then `AWAY`, each with `n_rows`; summary and profile rows carry `subject` |
| rows chronological | **CLEAR** — ascending `kickoff_unix`, plus `kickoff_date` (ISO), `chronological_rank` and `matches_before_target` on every row, and a `row_order` string saying M01 is the oldest |
| FOR/AGAINST orientation clear | **CLEAR** — `orientation_rule` states `_for`/`_against` is the subject's perspective and is **independent of** the `venue` field, naming the exact confusion V5A left open |
| raw rows occur early | **CLEAR** — 15.2%–45.2%, ahead of every summary |
| summaries visually distinct | **CLEAR** — their own numbered sections, `evidence_type: DERIVED_SUMMARY`, `derivation_type: UNWEIGHTED_MEAN`, distinct id prefix |
| opponent-profile direction clear | **CLEAR** — full-sentence `semantic_label` (`HOME_TEAM_ATTACK_VS_OPPONENTS_DEFENSIVELY_SIMILAR_TO_AWAY_TEAM`), cohort definition, cohort N, baseline and baseline N |
| no treatment label visible | **CLEAR** — structural scan of every key and value |
| availability truthful | **CLEAR** — asserted against actual section and row presence |
| no unsupported prompt invitations | **CLEAR** — the prompt promises no section; the admissibility gate enforces the packet's surface |
| ids resolvable | **CLEAR** — 2,601–3,361 research, 107–109 base |
| no truncation | **CLEAR** — no markers; row/column counts exact |

Two residual readability notes, reported rather than fixed:

- **Summaries remain about twice the raw rows by volume.** Structurally distinct and
  positioned after the record, but still the larger block.
- **`possession_for` and `possession_against` are complementary** (they sum to 100), so one
  of the two columns is redundant. The metric semantics say so explicitly rather than leaving
  a reader to infer it.

---

## 10. Full 10-fixture structural table

| fixture | packet hash A/B | rows H/A | metric cols | cells | cell fidelity | truncation | chronology | both teams | availability map | valid ids A/B | dup ids | dup aliases | superset | unexpected value diffs |
|---|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|
| mt_010243515 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,361 | 0 | 0 | ✅ | 0 |
| mt_010243537 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,361 | 0 | 0 | ✅ | 0 |
| mt_010243938 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,361 | 0 | 0 | ✅ | 0 |
| mt_010244159 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,361 | 0 | 0 | ✅ | 0 |
| mt_010244193 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,361 | 0 | 0 | ✅ | 0 |
| mt_010441320 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,361 | 0 | 0 | ✅ | 0 |
| mt_010441491 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,361 | 0 | 0 | ✅ | 0 |
| mt_010444904 | ✅/✅ | 30/**14** | 46 | 2,024 | 0 mismatch | none | ascending | ✅ | ✅ | 109/2,601 | 0 | 0 | ✅ | 0 |
| mt_012232295 | ✅/✅ | 30/30 | 46 | 2,760 | 0 mismatch | none | ascending | ✅ | ✅ | 109/3,343 | 0 | 0 | ✅ | 0 |
| mt_012232411 | ✅/✅ | **27/27** | 46 | 2,484 | 0 mismatch | none | ascending | ✅ | ✅ | 107/3,054 | 0 | 0 | ✅ | 0 |

---

## 11. PIT and leakage

| check | result |
|---|---|
| every row `kickoff_unix < information_cutoff_unix` | ✅ 10/10 |
| target fixture never present as a row | ✅ 10/10 |
| cutoff equals the target's kickoff | ✅ 10/10 |
| identity leak (real club / competition tokens, both arms) | **0 hits** |
| target outcome fields (`score_home`, `fulltime`, `fixture_result`) | absent from every key and value |
| market fields (`odds`, `price`, `market`, `probability`, `implied`) | absent; `market_prices` appears only as the availability dimension that **declares** them absent, asserted `NOT_PROVIDED_BY_SOURCE` |
| import-graph isolation | no V5A.1 module imports `boto3`, `botocore`, `requests`, `httpx`, `urllib`, `socket`, `http`, nor references `p_model`, Bedrock, the champion artifact, or the prediction/prospective/broadcast/forward layers |
| firewall numeric provenance | restricted to the MEASURED quantities (`value`, `cohort_value`, `baseline_value`) and the raw match cells. Sample sizes and coverage rates are excluded: they are metadata about an estimate and are small integers that collide with plausible metric values, so including them would let a copied predictive number be labelled "reproduces a packet value" (class B) rather than class A. **Both classes block**, so this affects classification accuracy, not enforcement, and it is symmetric across arms either way. |

---

## 12. Prompt-to-data compatibility (§7, §17, §22)

The prompt promises no section and names no dimension as a quota. The admissible surface is
narrowed per packet, and the packet declares that surface itself.

| | base arm | research arm |
|---|---|---|
| metrics | 23 canonical | 23 canonical (identical) |
| windows | `ALL_PRIOR` | `ALL_PRIOR`, `W5`, `W10` |
| dimensions | `competition` | `competition`, `venue`, `opponent_profile`, `own_formation_family`, `opponent_formation_family` |
| comparisons | `SUBJECT_OVERALL_BASELINE` | + `SUBJECT_VENUE_BASELINE`, `SUBJECT_RECENT_VS_LONG_BASELINE` |
| excluded metrics (declared in-packet) | `npxg`, `dangerous_attacks`, `attacks`, `total_bookings` | same |
| unsupported comparisons | `LEAGUE_ENVIRONMENT_BASELINE`, `SUBJECT_COMPETITION_BASELINE` | same |
| unsupported dimensions | `half_score_state`, `period`, `referee` | same |

`schema_v2` and `vocabulary` remain frozen and byte-identical; the narrowing happens in
`v5a1_admissibility`, per packet, at validation time. Every surface claim above is enforced
by a test that asserts the corresponding hypothesis is refused.

Priming: **0 hits** across all 20 payloads. The four prohibition-only terms in the prompt are
asserted to occur only inside the HARD RULES list.

---

## 13. Cost model (§34) — recomputed from the actual frozen requests

| item | value |
|---|---|
| calls | **38** (20 base + 18 repeatability) |
| repeatability | 3 fixtures × 2 arms × 3 extra calls |
| total input bytes | 3,272,310 |
| calibration | 0.546 tokens/byte — V3 **observed** 21,457 input tokens / 39,297 payload bytes |
| total input tokens (est.) | 1,786,660 |
| output tokens, mean / p90 / max | 97,888 / 121,410 / 155,648 |
| price | $0.003 / 1K in, $0.015 / 1K out |
| **expected cost** | **$6.8283** |
| **p90 cost** | **$7.1811** |
| **hard ceiling** | **$7.6947** |

Computed from the actual serialized requests in this freeze. The aborted V5A's $7.18 estimate
was **not** reused.

---

## 14. Pre-spend regression battery (§32)

`tests/research/hypothesis_oos/test_v5a1_prespend.py` — **47 tests, all passing.**

| mandated test | covered by |
|---|---|
| `arm_b_valid_evidence_ids_nonzero` | `test_arm_b_valid_evidence_ids_nonzero` |
| `arm_b_grounded_reference_acceptance` | `test_arm_b_grounded_reference_acceptance` |
| `arm_a_grounded_reference_acceptance` | `test_arm_a_grounded_reference_acceptance` |
| `same_base_history_universe` | `test_same_base_history_universe` |
| `arm_b_superset_of_arm_a_base_evidence` | `test_arm_b_superset_of_arm_a_base_evidence`, `test_arm_b_does_not_omit_anything_arm_a_receives` |
| `no_visible_treatment_label` | `test_no_visible_treatment_label`, `test_packet_schema_version_identical_across_arms` |
| `truthful_availability_map` | `test_truthful_availability_map`, `test_availability_matches_what_the_packet_actually_contains` |
| `no_prompt_invited_unsupported_dimension` | `test_no_prompt_invited_unsupported_dimension`, `test_excluded_metrics_are_declared_in_the_packet` |
| `duplicate_match_aliases_zero` | `test_duplicate_match_aliases_zero` |
| `duplicate_evidence_ids_zero` | `test_duplicate_evidence_ids_zero`, `test_duplicate_ids_fail_construction` |
| `opponent_profile_direction_unambiguous` | `test_opponent_profile_direction_unambiguous`, `test_opponent_profile_is_descriptive_not_predictive` |
| `raw_rows_before_summary_majority` | `test_raw_rows_before_summary_majority`, `test_both_teams_rows_present_and_before_summaries` |
| `no_hidden_truncation` | `test_no_hidden_truncation` |
| `serialized_cells_equal_canonical` | `test_serialized_cells_equal_canonical` |
| `xg_npxg_semantics_resolved_or_npxg_excluded` | `test_xg_npxg_semantics_resolved_or_npxg_excluded` |
| `target_fixture_excluded` | `test_target_fixture_excluded_and_future_observations_excluded` |
| `future_observations_excluded` | same |
| `no_future_market` / `no_target_outcome` | `test_no_target_outcome_and_no_future_market` |
| `no_llm_to_p_model_path` | `test_no_llm_to_p_model_path`, `test_no_network_or_bedrock_in_the_build_path` |
| *(added)* build reproducibility | `test_frozen_artifacts_are_byte_reproducible` |
| `champion_unchanged` | `test_champion_unchanged` |
| `v2_v3_v4_unchanged` | `test_v2_v3_v4_unchanged`, `test_v5a_artifacts_preserved` |

Plus: the §19 grounding battery, chronology and row-order, formation restraint, metric
semantics coverage, priming scans, manifest hash reproduction, packet hash reproduction and
the cost ceiling.

**Frozen-suite regression:** `tests/research/hypothesis_engine/` + the V5A and V4 pre-spend
suites — **543 passed**. One pre-existing environmental failure is excluded and reported in
§16 below.

---

## 15. Findings raised and closed during the build

| finding | severity | disposition |
|---|---|---|
| Two similarity axes produced the same `PROFILE:` id | would have been a duplicate-id defect | caught by `assert_unique` **at construction**; the axis is now part of the id grammar |
| Formation-conditioned hypotheses were admissible in the base arm, which has no per-row formation | HS-3 failure mode returning by a side door | closed: conditioning now requires the field on each observation; `test_formation_restraint` guards it |
| First build was 185k tokens per research packet from repeated summary metadata | would have reproduced V5A defect M-1 | closed by the shared-metadata table form; now 65–72k |
| 40 shared records differed across arms | needed classification, not suppression | all 40 are the availability declarations §7 requires to differ; separated in the audit as `EXPECTED_AVAILABILITY_DIFFERENCES`, and unexpected mismatches are 0 |
| `red_cards` null-coerced to zero at the adapter | semantics risk | measured and justified (5.4% implied red rate); exposed with a model-visible caveat rather than silently kept |
| `evidence_id_audit.json` was not byte-reproducible across runs | frozen artifact could not be verified | closed: `id_prefix_counts` was built with `Counter` over a **set**, so its key order followed set-iteration order and varied with `PYTHONHASHSEED` while the content stayed identical. Now sorted; `test_frozen_artifacts_are_byte_reproducible` re-runs the whole build under a different hash seed and requires every artifact to be byte-identical. Verified at seeds 1, 2, 3 and 12345: **7/7 identical**. |
| The scanner-exemption list for documentation fields had grown to make tests pass | would have weakened the leakage scan | closed: `note` and `cohort_definition` interpolate per-fixture data and are no longer exempt, and `test_documentation_fields_are_static_constants` now asserts every remaining exempted field has an identical value set across all 10 fixtures — the exemption is an enforced invariant, not a list |

---

## 16. Open items reported, not resolved

1. **`tests/research/hypothesis_engine/test_architecture_isolation.py::test_champion_produces_p_model_with_the_llm_packages_uninstalled` fails in this environment.**
   Precisely: the test spawns a subprocess with the LLM packages blocked and runs the
   champion; that subprocess dies on `ModuleNotFoundError: No module named 'sklearn'`
   **before any V5A.1 code path is reached**, and `python3 -c "import sklearn"` fails in
   this environment too. What the run proves absent is `sklearn`, which this work does not
   touch; the test references no V5A.1 module. It is **not** fixed here and should be
   re-run where `sklearn` is installed before spend is authorised. It does not block: the
   property it guards — the champion's independence from the LLM stack — is independently
   asserted by `test_champion_unchanged` (artifact SHA-256) and `test_no_llm_to_p_model_path`
   (import graph of all eight V5A.1 modules).
2. **Summaries remain ~2× the raw rows by volume.** Reported per §12, not tuned.
3. **`possession_for` / `possession_against` are complementary** and therefore redundant with
   each other. Documented in the metric semantics; both columns retained for orientation
   consistency across the 46-column row.

---

## 17. Outcome

- Frozen hashes reproduce: packet hashes and serialized-request hashes recomputed for all 38
  manifest calls.
- `VALID_EVIDENCE_IDS > 0` for every packet; grounded references resolve end-to-end in both
  arms; invalid, cross-fixture, duplicate and unsupported references all fail correctly.
- Research arm is a proven superset of the base arm; 0 unexpected value differences.
- Cell fidelity 26,588 / 0 mismatches; no truncation; no unexplained omission.
- Raw record precedes every summary byte, 10/10.
- No treatment label; truthful availability; no unsupported invited dimension.
- CHAMPION unchanged; V2/V3/V4/V5A module hashes unchanged; the aborted V5A artifacts intact.
- $0 spent. 0 Bedrock, LLM or network calls.

**`V5A1_PACKET_READABILITY_VALIDATED`**
**`V5A1_FULLY_PREREGISTERED`**
**`V5A1_SPEND_AUTHORIZATION_REQUIRED`**
