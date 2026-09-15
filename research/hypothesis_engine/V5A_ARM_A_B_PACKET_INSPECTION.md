# V5A Arm A / Arm B Packet Inspection — Pre-Spend Authorization Audit

**Scope:** ZERO-SPEND, read-only, manual + structural inspection of the frozen V5A Arm A and
Arm B packets.
**Date:** 2026-09-14
**Bedrock calls made:** 0. **LLM calls made:** 0. **Network calls made:** 0.
**Artifacts modified:** none. Packets, prompts, schemas, manifests, hashes, thresholds,
experiment design, V2/V3/V4, CHAMPION and `p_model` were read only.

**Question under audit:** *Are the exact Arm B packets that will be sent to Sonnet both
scientifically complete and cognitively readable, and is Arm A vs Arm B genuinely isolated
to evidence representation?*

**Answer in one line:** The packets are frozen, intact, complete and truncation-free, but the
arms are **not** isolated to evidence representation, and the shared validator/firewall
cannot resolve any Arm B evidence reference — so an Arm B grounded hypothesis is rejected by
construction. **ABORT.**

---

## Inspected artifacts

| Path | Bytes | Role |
|---|---|---|
| `research/hypothesis_oos/out/v5a/PREREGISTRATION.json` | 14,009 | frozen manifest + cost model |
| `research/hypothesis_oos/out/v5a/arm_a_packets.json` | 431,827 | Arm A packets (11 fixtures) |
| `research/hypothesis_oos/out/v5a/arm_b_packets.json` | 1,469,717 | Arm B packets (11 fixtures) |
| `research/hypothesis_oos/out/v5a/exposure_audit.json` | 12,801 | frozen exposure audit |
| `research/hypothesis_oos/out/v5a/BYTELEVEL_ARM_{A,B}_mt_010244159.request.txt` | 39,298 / 137,846 | byte-level request dumps |
| `src/research/hypothesis_oos/v5a_prompt.py` | — | `SYSTEM_PROMPT`, `build_user_payload` |
| `src/research/hypothesis_oos/v5a_full_fidelity.py` | — | Arm B builder |
| `research/hypothesis_engine/_build_v5a.py`, `_freeze_v5a.py` | — | build / freeze |
| `src/research/hypothesis_engine/{validator,validator_v2,firewall_v2,query_plan,schema,schema_v2,availability,similarity}.py` | — | shared stack |

The exact serialized payload was reconstructed through the production path
`v5a_prompt.build_user_payload()` (`json.dumps(packet, sort_keys=True,
separators=(",",":"), default=str)`) and the request string through
`SYSTEM_PROMPT + "\x00" + payload`, i.e. the identical expression used by `_freeze_v5a.py`
to produce the frozen manifest. No pretty-printed reconstruction was substituted for the
serialized bytes anywhere in this audit. Exact payloads for the three deeply inspected
fixtures were written to the session scratchpad (not the project tree).

---

## 1. Frozen hash verification

All 20 paired calls verified: packet hash recomputed from packet body, request hash
recomputed from `SYSTEM_PROMPT + "\x00" + payload`, byte count recomputed from the
serialized string.

| FIXTURE_ID | ARM | REQUEST_HASH | BYTES | ESTIMATED_INPUT_TOKENS | HASH_MATCH |
|---|---|---|---:|---:|---|
| mt_010243515 | A | `9c1bad721b03a4d8f537e5447056865c88c7b93d9c53c41464ffbabebb07b71d` | 36,529 | 23,429 | TRUE |
| mt_010243515 | B | `18c6208700f00a645f4bedf98e5b9974f05dd651108569e723c84f5fff3bd26c` | 135,057 | 77,226 | TRUE |
| mt_010243537 | A | `9bf3cb0a3eca0ab72c9a1a13eea928d7f2136943b191f03d900216d858d643de` | 36,697 | 23,521 | TRUE |
| mt_010243537 | B | `d7c2c43d6d3f47f543d5ebf14becb1dbaed68bd302eb5d5da4b5ddb9087bed35` | 134,980 | 77,184 | TRUE |
| mt_010243938 | A | `21f2c317d675065a90e680427c08439ef7b314a52aa398cedd8810f0002e4380` | 36,527 | 23,428 | TRUE |
| mt_010243938 | B | `5717160f79c38882d610035fbf40ccf015bca34fa0cd1be0527264b1346cf03f` | 135,107 | 77,253 | TRUE |
| mt_010244159 | A | `c8e8eb7b18115f74084f9966d275401a9e3227422c782b75adfd10bcf0ab3b83` | 36,534 | 23,432 | TRUE |
| mt_010244159 | B | `2f2b8d96c77a0a5bcb2153fab7edd59f5235e6ccbcb355a7bcf34055ed530b67` | 135,082 | 77,239 | TRUE |
| mt_010244193 | A | `9cd53a4d6f472ffbab746b6f0791bd005968c7c84b79076fa9d7c660394b1ffe` | 36,548 | 23,440 | TRUE |
| mt_010244193 | B | `070311a465530ad04e204e600b94f7ad3311d9dbe5c3806241ce41e4ec351afc` | 135,095 | 77,246 | TRUE |
| mt_010441320 | A | `ea14d86d8311f07ddec7c3a1362cac923068704b37e93fe9afa0843e0b20166a` | 36,542 | 23,436 | TRUE |
| mt_010441320 | B | `bfaab5df98dd51ccd96ae466e0b78a8ccfe611fe6dd978b3330472ddde283357` | 135,147 | 77,275 | TRUE |
| mt_010441491 | A | `194fcd7343d2979e106bd943c0c7266602517d709d41273062c9f2040a76c11c` | 36,529 | 23,429 | TRUE |
| mt_010441491 | B | `6f4e0aab531bad68e91f3eeb7301860818afe03f5d0820a565d485efc391814e` | 135,205 | 77,306 | TRUE |
| mt_010444904 | A | `48e927691b17659df70aa63bd279871a2c7c9ce65453bb1a86c7f0c56e2458cd` | 36,611 | 23,474 | TRUE |
| mt_010444904 | B | `709caae80dde5d5562b8f71bad9c1660620e2bc8e1d24feb755a80c6570b030d` | 129,403 | 74,139 | TRUE |
| mt_012232295 | A | `ff46ba51c8ae312109a7b3db2190084b2d594d00b95ef970ba7d8cd09d719a0b` | 36,623 | 23,481 | TRUE |
| mt_012232295 | B | `aa3d87a2cf1e92630e3bd0158ef68164a3ce7b1276cd7544ec862436f31aa45a` | 131,885 | 75,494 | TRUE |
| mt_012232411 | A | `f9681c40fa39a55685470e9eaf773a54ee5e7c2c2f116f47d7161c77991e8d54` | 35,768 | 23,014 | TRUE |
| mt_012232411 | B | `2274ec95dbe18eef8ccd6095de3b3381830a69d1f25edeef04b4de11481d9f99` | 129,476 | 74,178 | TRUE |

**HASH_MISMATCHES = 0.** Packet-body hashes additionally agree with `exposure_audit.json`
(`arm_a_packet_hash` / `arm_b_packet_hash`) for all 10 fixtures. No HARD STOP on hash
integrity.

Supplementary provenance checks:

- Arm A packets are **byte-identical** to `research/hypothesis_engine/out/MATERIALIZED_PACKETS_sonnet46_v3.json`
  under key `reference::<fixture_id>` for all 10 fixtures. Arm A is the genuine frozen V3
  body, taken verbatim by `_build_v5a.py` (`arm_a[fid] = v3[f"reference::{fid}"]`), not a
  reconstruction.
- `BYTELEVEL_ARM_{A,B}_mt_010244159.request.txt` are faithful: the section following the
  `=== USER (exact bytes) ===` marker at offset 2,737 equals `build_user_payload(packet)`
  exactly. They are a delimiter-wrapped copy, not a re-render.
- CHAMPION artifact `data/discovery/pilotC_stat_mixer.json` sha256
  `0b8f5ff3…c00c9` — `frozen_sha256 == current_sha256`. Untouched by this audit.

### Deterministic fixture selection (rule fixed before opening packet content)

Rule, declared ahead of inspection: sort the 10 paired fixtures by **Arm B serialized
payload bytes** ascending; ties broken by fixture ID ascending; take index `0` (smallest),
index `floor((n-1)/2) = 4` (median), index `n-1 = 9` (largest). No ties occurred.

| rank | fixture | Arm B bytes | selected |
|---:|---|---:|---|
| 0 | mt_010444904 | 129,403 | **SMALLEST** |
| 1 | mt_012232411 | 129,476 | |
| 2 | mt_012232295 | 131,885 | |
| 3 | mt_010243537 | 134,980 | |
| 4 | mt_010243515 | 135,057 | **MEDIAN** |
| 5 | mt_010244159 | 135,082 | |
| 6 | mt_010244193 | 135,095 | |
| 7 | mt_010243938 | 135,107 | |
| 8 | mt_010441320 | 135,147 | |
| 9 | mt_010441491 | 135,205 | **LARGEST** |

Selection used size only. No fixture was chosen for being interesting, and no prior
hypothesis or result influenced the choice.

---

## 2. Exact A/B difference inventory

Serialized top-level fields, compared across arms (identical for all 10 fixtures).

### 2.1 Fields present in one arm only

| field | A | B | classification |
|---|---|---|---|
| `evidence` (76 shrunk scalars, each with `id`) | ✅ | ❌ | INTENDED_EVIDENCE_DIFFERENCE *(but see HS-1)* |
| `data_quality` | ✅ | ❌ | INTENDED_EVIDENCE_DIFFERENCE |
| `formation_distribution` | ✅ | ❌ | **UNINTENDED_EXPERIMENT_DIFFERENCE** — the shared `availability.build_ontology()` reads this key for `observed_levels`; Arm B therefore resolves to `observed_levels=()` even though its rows carry 20 recorded formations, while Arm A resolves to `('BACK_FOUR',)`. The ontology handed to the compiler differs in kind, not in evidence. |
| `match_level_history` | ❌ | ✅ | INTENDED_EVIDENCE_DIFFERENCE |
| `derived_summaries` | ❌ | ✅ | INTENDED_EVIDENCE_DIFFERENCE |
| `opponent_profile_context` | ❌ | ✅ | INTENDED_EVIDENCE_DIFFERENCE |
| `availability_map` | ❌ | ✅ | INTENDED_EVIDENCE_DIFFERENCE |
| `history_policy` | ❌ | ✅ | **UNINTENDED_EXPERIMENT_DIFFERENCE** — declares a 30-match cap that governs Arm B only (see §2.3) |
| `row_encoding` | ❌ | ✅ | INTENDED_EVIDENCE_DIFFERENCE |
| `arm` = `"B_full_fidelity"` | ❌ | ✅ | **UNINTENDED_EXPERIMENT_DIFFERENCE** — unblinded treatment label, first key in the serialized payload (offset 1) |

### 2.2 Fields present in both

| field | identical? | classification |
|---|---|---|
| `fixture` (`HOME_TEAM`/`AWAY_TEAM`/`COMPETITION`) | **TRUE** | identical as preregistered |
| `fixture_id` | **TRUE** | identical as preregistered |
| `information_cutoff_unix` | **TRUE** | identical as preregistered |
| `vocabulary` (`hypothesis_vocabulary_v1`) | **TRUE** | identical as preregistered |
| `packet_schema_version` | FALSE (`fixture_context_packet_v1` vs `full_fidelity_view_v1`) | INTENDED_EVIDENCE_DIFFERENCE |
| `notes` | FALSE (builder/row-count strings) | INTENDED_EVIDENCE_DIFFERENCE |
| `packet_hash` | FALSE (necessarily) | INTENDED_EVIDENCE_DIFFERENCE |
| `capability_manifest` | **FALSE** | **UNINTENDED_EXPERIMENT_DIFFERENCE** (see §2.3) |

### 2.3 The two substantive unintended differences

**(a) Different underlying match population.** Arm A's scalars are means over the team's
*entire* PIT-safe prior history. Arm B is capped at `max_matches_per_team = 30`. The arms
therefore summarise **different sets of matches**, and Arm B is *not* a superset of Arm A's
information — Arm A's numbers are computed partly from matches Arm B never shows.

| fixture | Arm A `notes` prior_n (home/away) | Arm A `sample_n` range | Arm B rows (H/A) | Arm B ALL_PRIOR `sample_n` |
|---|---|---|---|---|
| mt_010243515 | 40 / 40 | 36–40 | 30 / 30 | 29–30 |
| mt_010243537 | 104 / 50 | 47–104 | 30 / 30 | 28–30 |
| mt_010243938 | 69 / 70 | 65–70 | 30 / 30 | 27–30 |
| mt_010244159 | 71 / 71 | 65–71 | 30 / 30 | 27–30 |
| mt_010244193 | 67 / 67 | 64–67 | 30 / 30 | 28–30 |
| mt_010441320 | 64 / 64 | 63–64 | 30 / 30 | 29–30 |
| mt_010441491 | 37 / 79 | 36–79 | 30 / 30 | 27–30 |
| mt_010444904 | 56 / 14 | 13–56 | 30 / 14 | 4–30 |
| mt_012232295 | 37 / 37 | 3–37 | 30 / 30 | 2–30 |
| mt_012232411 | 27 / 27 | 1–27 | 27 / 27 | 24–27 |

`exposure_audit.json` records `MATCH_ROWS_OMITTED` of 0–94 per fixture with
`omission_reason: frozen_history_policy(max_matches_per_team=30)`. The omission is declared
(so it is not hidden truncation — §7 passes), but it is an **information-set** difference,
not a representation difference.

Compounding this, Arm A's scalars carry `shrinkage_level: "SHRUNK"`, while Arm B's
`DERIVED_SUMMARY` values are plain unshrunk means. The same nominal quantity
(`corners_for`, `ALL_PRIOR`, `venue=ALL`) is a shrunk 71-match estimate in Arm A and a raw
30-match mean in Arm B.

**(b) Different metric inventory.** Arm A exposes 19 distinct metrics; Arm B exposes 24.
Arm B adds `npxg`, `offsides`, `red_cards`, `shots_outside_box`, `xg`. The
`capability_manifest.available_metrics` block differs accordingly (19 vs 24), as does
`capability_manifest.coverage.*.candidate_n` (142 vs 60 for mt_010244159 — itself a
consequence of (a)). Arm A is internally consistent (19 advertised, 19 present), so this is
a cross-arm asymmetry, not an Arm A bug.

### 2.4 Preregistered-identical checklist

| item | status | evidence |
|---|---|---|
| target fixture | ✅ IDENTICAL | `fixture_id` equal per pair |
| cutoff | ✅ IDENTICAL | `information_cutoff_unix` equal per pair |
| aliases | ✅ IDENTICAL | `fixture` block equal; `HOME_TEAM`/`AWAY_TEAM`/`COMPETITION` in both |
| model | ✅ IDENTICAL | `us.anthropic.claude-sonnet-4-6`, one `model_id` in the manifest |
| temperature | ✅ IDENTICAL | `0.0`; `max_tokens` 8192 |
| system instructions | ✅ IDENTICAL byte-for-byte | single `P.SYSTEM_PROMPT` used for both arms (see §17 for why this is not sufficient) |
| output schema | ✅ IDENTICAL | `hypothesis_set_schema_v2`, content hash `7879c6ad…86077` |
| hypothesis count limits | ✅ IDENTICAL | `MAX_HYPOTHESES` shared from `schema_v1` |
| compiler contract | ✅ IDENTICAL module | `query_plan.compile_hypothesis`; takes no packet — arm-agnostic |
| firewall contract | ⚠️ **module identical, behaviour asymmetric** | `firewall_v2.evidence_values(packet)` reads `packet["evidence"]` → **76 values for Arm A, 0 for Arm B** |
| validator | ⚠️ **module identical, behaviour asymmetric** | `validator_v2` builds `valid_ids` from `packet["evidence"][*]["id"]` → **76 for Arm A, 0 for Arm B** (see §12/HS-1) |
| ontology | ❌ **DIFFERS** | `availability.build_ontology` reads `formation_distribution` (Arm A only) |
| scoring / evaluation instructions | ✅ IDENTICAL | single `evaluation_rubric` in the prereg, applied to both arms |

**UNINTENDED_EXPERIMENT_DIFFERENCE count = 5**
(`formation_distribution`/ontology, `history_policy` match cap, `arm` treatment label,
`capability_manifest` metric inventory, and the population/shrinkage divergence).

This alone satisfies the stated HARD STOP condition *"Arm A/B differ in more than evidence
representation"* and falsifies the preregistered claim
`shared_stack.only_evidence_representation_differs: true`.

---

## 3. Deep inspection — smallest / median / largest

### 3.1 Common Arm B anatomy (all three)

Serialization is `sort_keys=True, separators=(",",":")` — one line, no whitespace, keys in
**alphabetical** order. The resulting reading order of the packet is:

```
arm → availability_map → capability_manifest → derived_summaries{AWAY_TEAM, HOME_TEAM}
    → fixture → fixture_id → history_policy → information_cutoff_unix
    → match_level_history{AWAY_TEAM, HOME_TEAM} → notes → opponent_profile_context
    → packet_hash → packet_schema_version → row_encoding → vocabulary
```

`match_level_history.<TEAM>` is `{columns: [55 names], n_rows: N, values: [[…55 cells…] × N]}`
— **row-major**, one inner list per match. `columns` is emitted once. Metric columns are
the 24 canonical metrics × `{_for, _against}` = 48, plus 7 context columns
(`match_alias`, `kickoff_unix`, `competition`, `venue`, `opponent_alias`,
`own_formation_family`, `opponent_formation_family`).

`derived_summaries.<TEAM>` is a flat list of ~240 objects, each with exactly
`{type, metric, side, window, venue, value, sample_n, cutoff_unix, reliability, provenance}`.
Windows are `ALL_PRIOR`/`W5`/`W10` at `venue: "ALL"`, plus `ALL_PRIOR` at `venue: "HOME"`
and `"AWAY"` (emitted only when n ≥ 3).

### 3.2 mt_010444904 — SMALLEST (129,403 B ≈ 70,654 tok)

- cutoff `1763910900` (2025-11-23). HOME_TEAM 30 rows (2025-02-15 → 2025-11-16, last row
  7 days before cutoff); AWAY_TEAM **14 rows** (2025-08-15 → 2025-11-17, 5 days before
  cutoff). The asymmetry is the reason this is the smallest packet, and it is visible in
  `notes` (`away_rows=14`) and in `n_rows`.
- 44 match rows × 48 metric cells = 2,112 cells; 476 derived summaries.
- 182 null metric cells (8.6% of cells) — the highest null density of the three.
- Section sizes: `match_level_history` 14,819 B (**11.5%**); `derived_summaries`
  106,404 B (**82.2%**); `opponent_profile_context` 2,055 B (1.6%); `vocabulary` 3,047 B
  (2.4%); `capability_manifest` 1,874 B (1.4%); `availability_map` 300 B (0.2%).
- Raw : summary byte ratio **1 : 7.18**.

### 3.3 mt_010243515 — MEDIAN (135,057 B ≈ 73,741 tok)

- cutoff `1756645200` (2025-08-31). Both teams 30 rows (2024-11-09 → 2025-08-24 / 08-23).
- 60 rows × 48 = 2,880 cells; 480 derived summaries; 116 null metric cells (4.0%).
- `match_level_history` 19,315 B (**14.3%**); `derived_summaries` 107,554 B (**79.6%**).
- Raw : summary **1 : 5.57**.
- Two `match_alias` values (`m_mt_745355352`, `m_mt_972822643`) appear in **both** teams'
  blocks — the teams met twice inside the 30-match window (see §12).

### 3.4 mt_010441491 — LARGEST (135,205 B ≈ 73,821 tok)

- cutoff `1777644900` (2026-05-01). Both teams 30 rows (2025-10-04 → 2026-04-26 /
  2025-10-06 → 2026-04-24).
- 60 rows × 48 = 2,880 cells; 480 derived summaries; 120 null metric cells (4.2%).
- `match_level_history` 19,435 B (**14.4%**); `derived_summaries` 107,582 B (**79.6%**).
- Raw : summary **1 : 5.54**. Highest formation coverage of the ten (26.7%) — still
  `LOW_COVERAGE`.
- One cross-team `match_alias` collision (`m_mt_191000707`).

### 3.5 Arm A, same three fixtures — what Sonnet actually receives

Arm A is 76 objects (74 for mt_012232411) of the form:

```json
{"cutoff_unix":1777116600,"id":"HOME_ATK_corners_406027","max_source_time_unix":1776511800,
 "metric":"corners_for","reliability":"HIGH","sample_n":71,
 "scope":{"metric":"corners","side":"FOR","subject":"HOME","venue":"ALL","window":"ALL_PRIOR"},
 "shrinkage_level":"SHRUNK","source_field":"('rich', 'corner_kicks')",
 "source_provider":"thestatsapi","temporal_status":"PIT_SAFE","value":5.0813}
```

- **Fixture metadata:** `fixture` (`HOME_TEAM`/`AWAY_TEAM`/`COMPETITION`), `fixture_id`,
  `information_cutoff_unix`. Present and identical to Arm B.
- **Metric summaries:** 19 metrics × `{FOR, AGAINST}` × `{HOME, AWAY}` subject = 76 shrunk
  scalar means. Each carries `sample_n`, `reliability`, `shrinkage_level`,
  `temporal_status`, `max_source_time_unix`, `source_provider`, `source_field` and a stable
  `id`.
- **Temporal scope:** `window` is `ALL_PRIOR` for **all 76** items. There is no W5, no W10,
  no season split, and no date on any observation.
- **Venue representation:** `venue` is `ALL` for **all 76** items. Venue appears only as a
  fixture-level label (`fixture.home` / `fixture.away`) and as an advertised dimension in
  `capability_manifest.available_dimensions`. **No venue-conditioned evidence exists.**
- **Opponent-profile representation:** absent. No `opponent_profile_context`, no `OPP_`
  alias anywhere in the Arm A payload, no cohort, no band.
- **Formation representation:** `formation_distribution` only — e.g. mt_010244159 gives
  `{"HOME_TEAM": {"BACK_FOUR": 2}, "AWAY_TEAM": {"BACK_FOUR": 2}}`, against a
  `capability_manifest.coverage.own_formation_family` of `usable_n 25 / candidate_n 142`
  (0.1761). Only one family is observed, so the shared ontology marks the dimension
  `AVAILABLE_LOW_CONTRAST` ("a condition on it compares a cohort with itself").
- **Availability metadata:** `data_quality = {n_evidence: 76, n_pit_safe: 76,
  n_unavailable: 0}` plus `capability_manifest.unsupported_context` (injuries, weather,
  expected_formation, minute_level_events, player_ratings). There is **no
  `availability_map`**.
- **Other evidence:** none.

**Arm A exposure, explicitly:**

| dimension | exposed in Arm A? |
|---|---|
| match-level rows | **NO** |
| venue-conditioned historical behaviour | **NO** (every item `venue: ALL`) |
| recent-vs-long history | **NO** (every item `window: ALL_PRIOR`) |
| opponent-profile response history | **NO** |
| cross-metric match-level structure | **NO** (76 independent scalars; no shared row) |

Arm A is the genuine frozen V3 compressed body, hash-identical to the V3 materialised
packet file. It is not a reconstructed approximation.

**The information difference vs Arm B** is therefore real and large in one direction
(Arm B adds 44–60 dated, venue-tagged, opponent-tagged, cross-metric-aligned observations
and 462–480 windowed/venue-split aggregates that Arm A entirely lacks) — and real in the
*other* direction too: Arm A's scalars summarise up to 104 matches per team where Arm B is
capped at 30, and Arm A carries per-item provider provenance that Arm B carries nowhere.

---

## 4. Raw-observations vs derived-summaries visibility

Arm B does have explicitly separated, explicitly named sections: `match_level_history` and
`derived_summaries`, and every summary object self-labels `"type": "DERIVED_SUMMARY"` and
carries `"provenance": "mean of serialized match rows"` (or `"venue-conditioned mean of
serialized match rows"`). `notes` states *"match-level rows are actual canonical
observations; DERIVED_SUMMARY blocks supplement but do not replace them."*

**Could a reader mistake a derived summary for a raw observation?** Unlikely on inspection
of an individual object — a summary has no `match_alias`, no `kickoff_unix`, no
`opponent_alias`, and carries `type: DERIVED_SUMMARY`. Rated **LOW risk of confusion**.

**Do summaries dominate?** Yes, decisively.

| fixture | match rows | raw bytes | raw % | summary objects | summary bytes | summary % | raw : summary |
|---|---:|---:|---:|---:|---:|---:|---|
| mt_010444904 (smallest) | 44 | 14,819 | 11.5% | 476 | 106,404 | 82.2% | **1 : 7.18** |
| mt_010243515 (median) | 60 | 19,315 | 14.3% | 480 | 107,554 | 79.6% | **1 : 5.57** |
| mt_010441491 (largest) | 60 | 19,435 | 14.4% | 480 | 107,582 | 79.6% | **1 : 5.54** |

In token terms (0.546 tok/B calibration): roughly **8,100–10,600 tokens of raw rows against
58,100–58,700 tokens of derived summaries** per Arm B call.

The cause is structural, not a design choice: each summary object repeats all ten keys
(`type`, `metric`, `side`, `window`, `venue`, `value`, `sample_n`, `cutoff_unix`,
`reliability`, `provenance`) as full strings ≈ 220 B per scalar, while the columnar row
encoding amortises 55 column names across 30 rows ≈ 330 B per 55-cell match. One scalar
mean costs about two-thirds of what an entire 55-cell match observation costs.

Reported as required. No change made to the packets.

---

## 5. Full-data visibility / truncation (all 10 fixtures)

Cross-checked against `exposure_audit.json` (`hard_fail: false`,
`cell_fidelity: {checked: 27744, clean: true, mismatches: 0}`).

| FIXTURE | EXPECTED_ROWS | SERIALIZED_ROWS | EXPECTED_METRIC_COLUMNS | SERIALIZED_METRIC_COLUMNS | EXPECTED_CELLS | SERIALIZED_CELLS | DECLARED_OMITTED | UNEXPLAINED_OMISSION | TRUNCATION_DETECTED |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| mt_010243515 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 20 | 0 | **FALSE** |
| mt_010243537 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 94 | 0 | **FALSE** |
| mt_010243938 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 79 | 0 | **FALSE** |
| mt_010244159 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 82 | 0 | **FALSE** |
| mt_010244193 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 74 | 0 | **FALSE** |
| mt_010441320 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 68 | 0 | **FALSE** |
| mt_010441491 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 56 | 0 | **FALSE** |
| mt_010444904 | 44 | 44 | 48 | 48 | 2,112 | 2,112 | 26 | 0 | **FALSE** |
| mt_012232295 | 60 | 60 | 48 | 48 | 2,880 | 2,880 | 14 | 0 | **FALSE** |
| mt_012232411 | 54 | 54 | 48 | 48 | 2,592 | 2,592 | 0 | 0 | **FALSE** |

Checks run per fixture on the serialized payload string:

- `n_rows == len(values)` for both team blocks — **TRUE, 10/10**.
- `len(row) == len(columns) == 55` for every row — **TRUE, 10/10** (1,076 rows total).
- Literal scan for `"..."`, `…`, and `/truncat|elided|clipped/i` in the payload —
  **no hits, 10/10**.
- No abbreviated arrays, no display-only clipping, no silently omitted trailing rows: the
  last serialized row is in every case the most recent admitted match, 4–8 days before
  cutoff.
- `admitted_history_serialization_rate: 1.0` for all 10 in the exposure audit.
- The 0–94 omitted matches per fixture are **declared** by `history_policy` and reported
  with `omission_reason` and `UNEXPLAINED_OMISSION: 0`. This is policy exclusion, not
  hidden truncation.

**No truncation. §7 passes.** (The policy exclusion is nonetheless a cross-arm confound —
see §2.3(a).)

PIT and leakage checks, all 10 fixtures:

- Every Arm B row `kickoff_unix < information_cutoff_unix` — **TRUE**.
- The target fixture's own match id never appears as a row — **TRUE**.
- Arm A `max_source_time_unix <= cutoff_unix` for every evidence item — **TRUE**.
- Identity-leak scan: 30 real club/competition tokens taken from `exposure_audit.json`
  (`real_home`, `real_away`, `competition`) searched case-insensitively across all 20
  payloads — **0 hits**. Aliasing holds.
- No target outcome, score, or post-cutoff observation appears in either arm.

---

## 6. Arm B readability inspection

Read as a research model encountering the packet cold.

### Fixture orientation — **READABLE_WITH_EFFORT**
`{"away":"AWAY_TEAM","competition":"COMPETITION","home":"HOME_TEAM"}` is unambiguous once
found, but `sort_keys` places the `fixture` block at **81.2–84.0%** through the payload,
after ~108 KB of derived summaries. The cutoff (`information_cutoff_unix`) sits immediately
after it. A reader learns *which fixture this is* only after two-thirds of the prompt.
The block is also degenerate: it restates the alias constants and adds nothing beyond
confirming that `HOME_TEAM` plays at home.

### Team history boundaries — **CLEAR**
`match_level_history` is keyed by `HOME_TEAM` / `AWAY_TEAM` with explicit `n_rows`, and
`notes` repeats `home_rows=N`, `away_rows=M`. No ambiguity about where one team's rows end.
Note the alphabetical key order puts **AWAY_TEAM first**.

### Chronology — **READABLE_WITH_EFFORT**
Rows are strictly ascending by `kickoff_unix` in all 20 team blocks (verified), and the
system prompt states "in chronological order". But: `kickoff_unix` is a raw epoch integer
(`1757772000`), there is no ISO date anywhere, and **nothing inside the packet states the
direction** — the `columns` list does not say "ascending", and `notes` does not mention
ordering. A reader must either trust the system prompt or compare two integers to learn
that the *last* row is the most recent. Distinguishing "recent" from "older" is possible but
requires an explicit act of inference, and mapping W5/W10 onto specific rows requires
counting backwards from the end of a 30-element array.

### Match orientation (subject FOR/AGAINST vs fixture HOME/AWAY) — **READABLE_WITH_EFFORT, with a residual confusion risk**
Every metric column is suffixed `_for` / `_against`, and the subject is fixed by the
enclosing key (`match_level_history.HOME_TEAM`). The system prompt states "canonical
FOR/AGAINST metrics per match". So orientation is recoverable.

The residual risk is real and worth stating plainly: the token `HOME` carries **two
different meanings** in the same packet and the packet never distinguishes them.
1. `match_level_history.HOME_TEAM` — subject identity in the *upcoming* fixture.
2. `values[i][venue] == "HOME"` — the subject's venue in *that historical* match.
3. `derived_summaries[*].venue == "HOME"` — venue-conditioned aggregate.
4. `opponent_profile_context.axes.<axis>.HOME` — **the HOME_TEAM as subject**, *not* a venue
   (see §10).

A reader who forms the rule "HOME = venue" from (2) and (3) will misread (4) exactly
backwards. There is no glossary in the packet resolving the collision.

### Opponent identity — **CLEAR (within a row), AMBIGUOUS (across teams)**
Every row carries `opponent_alias` (`OPP_001`…), assigned deterministically in first-seen
chronological order across both teams. Within one team's block, association is unambiguous.
Across blocks the alias space is shared, so `OPP_002` denotes the same real club in both
teams' histories — genuinely useful. See §12 for the `match_alias` collision problem.

### Competition identity — **CLEAR**
`competition` per row is `COMPETITION` for the target's own competition, `COMP_002`… for
others. Identity-neutral; 0 identity leaks confirmed by scan. `include_all_competitions:
true` in `history_policy` tells the reader why non-`COMPETITION` rows appear.

### Missingness — **READABLE_WITH_EFFORT**
JSON `null` vs `0.0` is a hard type distinction and is used correctly: e.g. mt_010244159
has 112 `null` metric cells against 207 genuine `0.0` cells. `null` and zero are never
conflated. *However*: no column is ever omitted (all 55 always present), so "omitted" is
not a state the reader can encounter, and the packet nowhere explains what `null` means —
provider did not report it, versus not applicable to that competition, versus not
applicable to that metric. Coverage is documented only for formation, not for metric cells.
A reader sees `null` and cannot tell which kind of absence it is.

### Formation — **CLEAR**
`own_formation_family` and `opponent_formation_family` are per-row and explicitly `null`
when absent. `availability_map.formation` reads `LOW_COVERAGE` in **all 10 fixtures**, and
`capability_manifest.coverage.own_formation_family` gives `candidate_n`, `usable_n`,
`missing_n`, `coverage_rate`. `availability_map.expected_formation` reads `UNAVAILABLE`,
and `capability_manifest.unsupported_context.expected_formation` spells out in prose that a
future fixture's formation is unknown and that hypotheses must range over observed
historical distribution instead. The recorded-vs-expected distinction is well made.

### Metric semantics — **AMBIGUOUS** (see defect M-7)
`vocabulary.metrics` is a bare list of 27 names with **no definitions**. `capability_manifest`
adds none. Specifically unresolved from the packet alone:
- `accurate_crosses` — completed crosses; total crosses attempted is not exposed, so a
  reader cannot tell whether this is a volume or an accuracy measure, and no denominator
  exists anywhere in the packet.
- `xg` vs `npxg` — both present as separate columns; the packet nowhere states that `npxg`
  excludes penalties, nor that `xg` includes them. Worse, the two columns are **mutually
  inconsistent in the data**: across all 1,050 comparable `(xg, npxg)` pairs in the ten
  Arm B packets, `npxg > xg` in **281 pairs (26.8%)**, by up to **1.01 xG**
  (mean excess 0.088). Non-penalty xG cannot exceed total xG, so this is not rounding.
  See defect M-8.
- `total_shots` vs `shots_on_target` + `shots_off_target` + `blocked_shots`, and
  `shots_inside_box` + `shots_outside_box` — the packet does not state which decomposition
  is exhaustive or whether blocked shots are counted inside `total_shots`.
- `possession` — no unit stated; values (`54.0`/`46.0`) imply percent summing to 100, but
  the reader must infer this.
- `yellow_cards` / `red_cards` — whether a second yellow is double-counted is unstated;
  `total_bookings` exists in the vocabulary but in neither packet.
- **Provider-specific exclusions are not in the packet at all.** The
  `dangerous_attacks` exclusion (proxy-only, `DO_NOT_MERGE`) is recorded in
  `PREREGISTRATION.json` and `exposure_audit.json` — but `dangerous_attacks` *is* listed in
  `vocabulary.metrics`, which the system prompt calls "the closed set of metrics … you may
  use", and nothing in the packet says it is excluded.
- **Arm B carries no `source_provider` / `source_field` on any row or summary.** Arm A
  carries both on all 76 items. Sonnet must infer provider semantics from names alone in
  precisely the arm designed to test whether it can reason from the real record.

---

## 7. Cross-metric inspection capability — **PASS**

`values` is **row-major**: each element of `values` is one 55-cell list describing one
match. `columns` maps position → name once. Metric-level co-occurrence is therefore fully
preserved — a reader can read `accurate_crosses_for`, `corners_for`, `possession_for`,
`shots_on_target_for`, `blocked_shots_against`, `tackles_for`, `fouls_for`,
`yellow_cards_for` off **the same row** for the same match.

Worked example, `mt_010244159` HOME_TEAM `values[0]` (`m_mt_747395666`, HOME vs `OPP_001`):
`accurate_crosses_for 3.0`, `corners_for 3.0`, `possession_for 54.0`, `total_shots_for 10.0`,
`shots_on_target_for 3.0`, `blocked_shots_for 0.0`, `tackles_for 24.0`, `fouls_for 20.0`,
`yellow_cards_for 1.0`, `xg_for 0.85`, `npxg_for 0.92`.

All four of the example relationships named in the mandate are inspectable at match level:
crosses↔corners, possession↔shots/SoT, blocked shots↔corners, tackles/fouls↔cards.

**Metrics are NOT serialized into separate independent arrays. No MATERIAL DESIGN DEFECT on
cross-metric alignment.** Verified: `len(row) == len(columns) == 55` for all 1,076 rows
across all 10 fixtures; `exposure_audit.cell_fidelity` confirms 27,744 cells checked,
0 mismatches against the canonical record.

Caveat, not a defect: the **derived summaries destroy** co-occurrence (each is a single
scalar), and they occupy ~80% of the packet. Cross-metric structure exists only in the 11.5–14.4%
of the packet that is rows.

---

## 8. Venue inspection capability — **PASS**

1. **Per-observation venue:** every row carries `venue ∈ {HOME, AWAY}`, verified present
   and valid on all 1,076 rows across all 10 fixtures. Venue is attached to the historical
   observation itself, not merely to the target fixture.
2. **Deterministic venue summaries:** `derived_summaries` includes `venue: "HOME"` and
   `venue: "AWAY"` entries at `window: ALL_PRIOR` for each metric×side, each with its own
   `sample_n` and `reliability`, emitted only when n ≥ 3. E.g. mt_010244159 HOME_TEAM
   `accurate_crosses FOR`: `HOME 4.9333 (n=15)`, `AWAY 4.4 (n=15)`, `ALL 4.6667 (n=30)`.
3. `availability_map.venue` = `AVAILABLE` in all 10 fixtures, gated on ≥ 4 home and ≥ 4
   away rows for both teams.

Arm A, by contrast, has **zero** venue-conditioned evidence (all 76 items `venue: ALL`) while
`capability_manifest.available_dimensions` advertises `venue` and the shared prompt invites
"venue (home vs away) behavior". See §13.

---

## 9. Temporal inspection capability — **PARTIAL**

| requirement | verdict | evidence |
|---|---|---|
| exact chronology available | ✅ | `kickoff_unix` on every row; strictly ascending in all 20 team blocks |
| W5/W10 understandable relative to chronology | ⚠️ | `W5`/`W10` summaries carry `sample_n` and `window`, but **nothing maps them onto row indices**. The builder uses `rows[-5:]`/`rows[-10:]`; the packet never says so. A reader must infer "W5 = the last five rows" from the label alone. |
| longer-run distinguishable | ✅ | `ALL_PRIOR` vs `W5` vs `W10`, with `sample_n` and `reliability` on each |
| no future observation | ✅ | every `kickoff_unix < information_cutoff_unix`, 10/10; target row never present |

Date ranges for the three deeply inspected fixtures:

| fixture | cutoff | HOME span | AWAY span | days: last row → cutoff |
|---|---|---|---|---|
| mt_010444904 | 2025-11-23 | 2025-02-15 → 2025-11-16 (30) | 2025-08-15 → 2025-11-17 (14) | 7 / 5 |
| mt_010243515 | 2025-08-31 | 2024-11-09 → 2025-08-24 (30) | 2024-11-09 → 2025-08-23 (30) | 7 / 8 |
| mt_010441491 | 2026-05-01 | 2025-10-04 → 2026-04-26 (30) | 2025-10-06 → 2026-04-24 (30) | 4 / 6 |

Note the spans differ substantially between fixtures (9.3 months vs 3.2 months for the same
30 rows) and between teams within a fixture (mt_010444904: HOME spans 9 months, AWAY 3).
Nothing in the packet flags this, so "recent" and "long-run" are not comparable across
teams or fixtures without the reader computing the spans from epoch integers.

`vocabulary.windows` offers `SEASON_TO_DATE`, but no row carries a season field and no
`SEASON_TO_DATE` summary exists in either arm — a hypothesis using that window is
uncheckable against the packet.

---

## 10. Opponent-profile inspection capability — **MATERIAL DEFECT (M-2)**

What Sonnet actually sees, in full, per axis:

```json
"corners_for": {
  "AWAY": {"bandable_n":23,"candidate_n":23,"coverage_rate":1.0,
           "status":"AVAILABLE","upcoming_opponent_band":"MID"},
  "HOME": {"bandable_n":23,"candidate_n":23,"coverage_rate":1.0,
           "status":"AVAILABLE","upcoming_opponent_band":"MID"}}
```

| requirement (§14) | verdict | detail |
|---|---|---|
| what profile dimension is described | ✅ CLEAR | the axis key names metric+side; 8 axes present |
| which team/opponent direction applies | ❌ **AMBIGUOUS** | the keys are `HOME`/`AWAY`. In the builder these are `subj_label` — **the subject team**, so `axes.corners_for.HOME.upcoming_opponent_band` is the band of *AWAY_TEAM* (HOME_TEAM's upcoming opponent). Nothing in the packet says this. Everywhere else in the packet `HOME`/`AWAY` means venue. The most natural misreading — "HOME = home-venue split of the opponent's profile" — is wrong, and the second-most-natural — "HOME = the home team's own band" — is also wrong (it is that team's *opponent's* band, i.e. inverted). |
| cohort sample N | ⚠️ PARTIAL | `candidate_n` / `bandable_n` = the size of the **banding pool** (teams in the competition before cutoff, 23), *not* the number of the subject's own matches against similarly-profiled opponents. There is no cohort N, because there is no cohort. |
| response metric | ❌ **ABSENT** | no response value of any kind is serialized |
| baseline | ❌ **ABSENT** | no baseline is serialized |
| availability | ✅ | `status`, `coverage_rate`; `availability_map.opponent_profile = AVAILABLE` in all 10 |

**The block carries no response history.** It states only which tercile the single upcoming
opponent occupies. Crucially, **historical opponents are not banded** — `columns` has
`opponent_alias` but no opponent-band column, and no per-opponent profile table exists. A
reader therefore **cannot identify which past matches were against HIGH-band opponents**, and
so cannot form, inspect, or ground a similar-opponent cohort comparison from this packet.

This directly contradicts the builder's own docstring — *"band the UPCOMING opponent and
report the subject's response cohort vs its overall baseline"* — which describes a response
cohort the implementation never constructs.

Consequences for the experiment as preregistered:
- `availability_map.opponent_profile` asserts `AVAILABLE`, and the system prompt instructs
  "Do not ask about an unavailable dimension" — so the model is affirmatively told the
  dimension is usable.
- The rubric scores `appropriate_opponent_profile_use`, and `research_families` includes
  `OPPONENT_PROFILE_INTERACTION` — a family the packet cannot ground.
- `vocabulary.dimensions.opponent_profile.axes` lists **15** axes; only **8** are banded
  (`PROFILE_SIMILARITY_AXES`). The 7 unbacked axes (`shots_for`, `shots_against`,
  `tackles_for`, `fouls_for`, `yellow_cards_for`, `total_bookings_for`,
  `accurate_crosses_against`) are all accepted by `schema_v2`'s `axis` enum.

**Do the profile summaries masquerade as predictive effects?** No. They are stated as
descriptive rank-bands with coverage and no effect language. On neutrality the block is
clean; on sufficiency it is not.

Also noted: `similarity_version` is `"opponent_similarity_v1_pending"` — the string
`_pending` is frozen into a spend-authorising artifact (defect N-6).

---

## 11. Formation inspection capability — **PASS**

| fixture | recorded formation cells | null formation cells | coverage | families observed | `availability_map.formation` |
|---|---:|---:|---:|---|---|
| mt_010243515 | 20 | 100 | 0.167 | BACK_FOUR, BACK_THREE | LOW_COVERAGE |
| mt_010243537 | 18 | 102 | 0.150 | BACK_FOUR, BACK_THREE | LOW_COVERAGE |
| mt_010243938 | 18 | 102 | 0.150 | BACK_FOUR, BACK_THREE | LOW_COVERAGE |
| mt_010244159 | 20 | 100 | 0.167 | BACK_FIVE, BACK_FOUR | LOW_COVERAGE |
| mt_010244193 | 18 | 102 | 0.150 | BACK_FOUR, BACK_THREE | LOW_COVERAGE |
| mt_010441320 | 26 | 94 | 0.217 | BACK_FIVE, BACK_FOUR, BACK_THREE | LOW_COVERAGE |
| mt_010441491 | 32 | 88 | 0.267 | BACK_FIVE, BACK_FOUR, BACK_THREE | LOW_COVERAGE |
| mt_010444904 | 22 | 66 | 0.250 | BACK_FOUR, BACK_THREE | LOW_COVERAGE |
| mt_012232295 | 2 | 118 | 0.017 | BACK_FOUR | LOW_COVERAGE |
| mt_012232411 | 4 | 104 | 0.037 | BACK_FOUR | LOW_COVERAGE |

- **Recorded historical formation** — per-row `own_formation_family` /
  `opponent_formation_family`. ✅ distinguishable.
- **Missing formation** — explicit JSON `null`, never an empty string or `"UNKNOWN"`.
  ✅ distinguishable.
- **Histogram / summary** — `capability_manifest.coverage.{own,opponent}_formation_family`
  with `candidate_n` / `usable_n` / `missing_n` / `coverage_rate`. ✅ present.
- **Target expected formation** — **absent**, as it must be.
  `availability_map.expected_formation = UNAVAILABLE`, and
  `capability_manifest.unsupported_context.expected_formation` states in prose that no
  provider supplies a pre-match expected formation or timestamped lineup, that a future
  fixture's formation is therefore unknown, and that hypotheses must range over observed
  historical distribution or be formation-independent. `availability_map.lineup =
  PIT_UNSAFE`. ✅ PIT-safe.

**Over-weighting risk: LOW.** Low coverage is signalled three independent ways (per-row
nulls, `coverage_rate`, `LOW_COVERAGE` status), formations are never given prominence of
position or formatting, and two of ten fixtures have essentially no formation evidence
(1.7%, 3.7%) with the status flagging it. The shared ontology independently marks the
dimension `AVAILABLE_LOW_CONTRAST` where only one family is observed. Nothing in the
packet encourages over-weighting.

One asymmetry, folded into §2: Arm B's rows carry 20 recorded formations for mt_010244159,
but because `availability.build_ontology()` reads `packet["formation_distribution"]` — a key
Arm B does not have — the ontology handed to the compiler for Arm B reports
`observed_levels=()`, versus `('BACK_FOUR',)` for Arm A. Arm B's richer formation record is
invisible to the shared availability layer.

---

## 12. Evidence-reference integrity — **HARD STOP (HS-1)**

`schema_v2` requires `evidence_refs` on every hypothesis (`minItems: 0`, but a `SUFFICIENT`
hypothesis with no refs is rejected by the validator). The system prompt instructs: *"put the
match rows or summary ids that motivated it in `evidence_refs`"*. The rubric's first
criterion is *"groundedness (evidence_refs resolve to real rows/summaries)"*.

### 12.1 What identifiers the packet actually offers

| arm | citable identifier | count per packet | stable? |
|---|---|---:|---|
| A | `evidence[*].id` (e.g. `HOME_ATK_corners_406027`) | 76 | ✅ unique, stable |
| B | `match_alias` (e.g. `m_mt_747395666`) | 44–60 | ⚠️ unique within a team block; **collides across teams** |
| B | derived summary id | **0 — no `id` key exists** | ❌ |

`derived_summaries[*]` keys are exactly `{cutoff_unix, metric, provenance, reliability,
sample_n, side, type, value, venue, window}`. **There is no identifier on any of the ~480
summary objects.** A hypothesis motivated by a venue split or a W5-vs-ALL_PRIOR contrast —
precisely the behaviour the experiment is built to elicit — has nothing to cite.

### 12.2 Duplicate / ambiguous identifiers

`match_alias` is `f"m_{r.fixture_id}"`, i.e. the real match id. When the two teams met inside
the 30-match window, the *same* alias names two different rows with **opposite FOR/AGAINST
orientation** — one in each team's block.

| fixture | cross-team `match_alias` collisions | colliding aliases |
|---|---:|---|
| mt_010243515 | 2 | `m_mt_745355352`, `m_mt_972822643` |
| mt_010243537 | 0 | — |
| mt_010243938 | 1 | `m_mt_404678402` |
| mt_010244159 | 1 | `m_mt_252067206` |
| mt_010244193 | 2 | `m_mt_196560708`, `m_mt_626439604` |
| mt_010441320 | 1 | `m_mt_010443713` |
| mt_010441491 | 1 | `m_mt_191000707` |
| mt_010444904 | 0 | — |
| mt_012232295 | 0 | — |
| mt_012232411 | 1 | `m_mt_743353973` |
| **total** | **9 across 7 of 10 fixtures** | |

A reference `m_mt_252067206` does not say whose perspective it is. The mandate's suggested
scheme (`HOME_M01`, `AWAY_M01`, `SUMMARY_HOME_CORNERS`) would resolve both this and 12.1;
neither is present.

### 12.3 The decisive finding: Arm B references cannot resolve at all

`validator_v2.validate` (line 116–118) and `validator._validate_one` (line 264) resolve
references as:

```python
valid_ids = set()
if packet:
    valid_ids = {it.get("id") for it in (packet.get("evidence") or []) if it.get("id")}
...
unknown = [r for r in refs if r not in valid_ids]
```

**Arm B packets have no `evidence` key.** Measured: `valid_ids` = **76 for Arm A, 0 for
Arm B**, all 10 fixtures.

Verified empirically, zero spend, by running the frozen `validator_v2` on a hand-written,
schema-valid, genuinely grounded hypothesis (HOME_TEAM corners-for at home vs venue
baseline) against each arm's real frozen packet:

```
ARM A | ref='HOME_ATK_corners_406027'                accepted=True   failure=None
ARM B | ref='m_mt_747395666'                         accepted=False  failure=INSUFFICIENT_EVIDENCE
        "evidence_refs not present in the packet actually sent: ['m_mt_747395666'];
         a reference the packet does not contain is ungrounded football knowledge, not evidence"
ARM B | ref='SUMMARY_HOME_corners_FOR_ALL_PRIOR'     accepted=False  failure=INSUFFICIENT_EVIDENCE
ARM B | ref='HOME_M01'                               accepted=False  failure=INSUFFICIENT_EVIDENCE
```

The *identical* hypothesis is accepted in Arm A and rejected in Arm B. And there is no
reference string that can succeed: `valid_ids` is the empty set, so `unknown` is non-empty
for **every** non-empty `evidence_refs`, while an empty `evidence_refs` is itself rejected
("a SUFFICIENT hypothesis must cite at least one evidence id").

**Arm B's maximum achievable accepted-SUFFICIENT-hypothesis rate is exactly 0.** The only
outcome the shared validator can accept from Arm B is `INSUFFICIENT_EVIDENCE` abstention.

The same coupling hits the firewall. `firewall_v2.evidence_values(packet)` also reads
`packet["evidence"]`, returning **76 values for Arm A and 0 for Arm B**. The module comment
at line 169 states this determines *"A-vs-B provenance: True when every literal in the match
was found in the packet's supplied evidence. False on an A assigned by fallback (no packet,
or unresolvable)."* Arm B numeric citations are therefore all classified as unresolvable
fallback. The preregistered "firewall-clean rate" comparison is not measuring the same
quantity in the two arms.

The $7.18 spend would purchase a guaranteed Arm B failure on `groundedness`,
`evidence_referenced_rate` and `compilability` that is an artifact of the shared stack's
coupling to the V3 packet shape — **not** a measurement of whether full-fidelity evidence
improves LLM research questions. This is the experiment's primary outcome, and its value in
Arm B is determined before the first token is generated.

---

## 13. Prompt-instruction ↔ available-data support matrix

The single `SYSTEM_PROMPT` (2,737 B, byte-identical across arms) is written entirely against
the **Arm B** packet shape. It tells the model, unconditionally: *"You will receive, for
both teams: match_level_history … derived_summaries … opponent_profile_context …
availability_map … capability_manifest and vocabulary."* Four of those five blocks do not
exist in Arm A.

| # | Task the prompt invites | ARM A | ARM B |
|---|---|---|---|
| 1 | "match_level_history: a table of actual prior matches … Inspect them directly" | **UNSUPPORTED** — no such key | SUPPORTED_BY_PACKET |
| 2 | "derived_summaries … ALL_PRIOR / W5 / W10, and HOME / AWAY splits" | **UNSUPPORTED** — no such key; all 76 items are `ALL_PRIOR`/`ALL` | SUPPORTED_BY_PACKET |
| 3 | "opponent_profile_context: rank-bands of the upcoming opponent … with coverage" | **UNSUPPORTED** — no such key, no `OPP_` alias anywhere | PARTIALLY_SUPPORTED — bands present; no response history, no cohort, direction ambiguous (§10) |
| 4 | "availability_map: which dimensions are AVAILABLE / LOW_COVERAGE / UNAVAILABLE / PIT_UNSAFE" | **UNSUPPORTED** — no such key; `data_quality` instead asserts `n_unavailable: 0` | SUPPORTED_BY_PACKET |
| 5 | "capability_manifest and vocabulary: the closed set … you may use" | SUPPORTED (19 metrics) | SUPPORTED (24 metrics) — but see #12 |
| 6 | "attacking behavior and defensive concession" | SUPPORTED (FOR/AGAINST scalars) | SUPPORTED |
| 7 | "venue (home vs away) behavior" | **UNSUPPORTED** — 76/76 items `venue: ALL`; venue exists only as a fixture label and an advertised dimension | SUPPORTED_BY_PACKET (per-row venue + venue summaries) |
| 8 | "opponent characteristics / similar-opponent cohorts" | **UNSUPPORTED** | **UNSUPPORTED for cohorts** — historical opponents are not banded, so no cohort is constructible (§10); only the upcoming opponent's band is given |
| 9 | "recent (W5/W10) versus longer-run behavior" | **UNSUPPORTED** — 76/76 items `window: ALL_PRIOR` | SUPPORTED_BY_PACKET |
| 10 | "formation ONLY when the availability_map says it is supported" | **UNSUPPORTED** — no availability_map to consult; `formation_distribution` shows 1 family | PARTIALLY_SUPPORTED — `LOW_COVERAGE`, so the instruction resolves to "do not use it" |
| 11 | "interactions ONLY when the visible record gives a concrete reason" | **UNSUPPORTED** — no record is visible, only 76 marginal scalars | SUPPORTED_BY_PACKET (row-level co-occurrence, §7) |
| 12 | "Ground every hypothesis: put the match rows or summary ids … in `evidence_refs`" | SUPPORTED (76 stable ids) | **UNSUPPORTED** — no summary ids exist; no reference resolves (§12) |
| 13 | "Do not ask about an unavailable dimension" | **UNSUPPORTED** — no availability_map; `data_quality.n_unavailable: 0` affirmatively signals nothing is unavailable | SUPPORTED_BY_PACKET |
| 14 | `vocabulary` offers `attacks`, `dangerous_attacks`, `total_bookings` | **UNSUPPORTED** (absent from data and from `capability_manifest`) | **UNSUPPORTED** (same; `dangerous_attacks` is an explicit `DO_NOT_MERGE` exclusion the packet never states) |
| 15 | `vocabulary` offers dimensions `half_score_state`, `period`, `referee` | **UNSUPPORTED** | **UNSUPPORTED** (`availability_map.half_time_state = UNAVAILABLE`; referee not built) |
| 16 | `vocabulary.windows` offers `SEASON_TO_DATE` | **UNSUPPORTED** | **UNSUPPORTED** — no season field on any row, no such summary |
| 17 | `vocabulary`/`schema_v2` offer 15 `opponent_profile` axes | **UNSUPPORTED** | **PARTIALLY_SUPPORTED** — 8 of 15 banded; 7 accepted by the schema with no backing data |
| 18 | `comparisons` include `LEAGUE_ENVIRONMENT_BASELINE`, `SUBJECT_COMPETITION_BASELINE` | **UNSUPPORTED** — no league-environment or per-competition evidence | **UNSUPPORTED** — same; rows carry a competition alias but no competition-level aggregate |

**Count: ARM A has 11 UNSUPPORTED invited dimensions; ARM B has 6.**

The §17 escape clause — *"unless the instructions explicitly tell the model they are
unavailable and to abstain"* — is **not** satisfied for Arm A. Arm A has no
`availability_map`, and its `data_quality` block asserts the opposite
(`n_unavailable: 0`). The prompt's own abstention mechanism ("Do not ask about an
unavailable dimension") is keyed to a block Arm A does not contain.

This is the V3 failure mode reproduced: the control arm is asked to reason about venue,
recency and opponent profile using a packet that contains none of them, and is told the
packet contains all of them. Any Arm B advantage measured under this design is partly the
measurement of a handicapped control.

---

## 14. Context-position analysis (§8)

Positions are **measured** offsets into the exact serialized payload string — key positions
by literal search, block and row spans by locating each block's and row's exact serialized
substring within `match_level_history`. No offset below is interpolated. Percentages are
offset ÷ payload bytes. Token positions are derived from the byte offsets using the frozen
0.546 tok/B calibration and are therefore approximate (marked `~`).

### mt_010444904 (smallest, 129,403 B ≈ 70,654 tok)

| element | byte offset | % through packet | ≈ token position |
|---|---:|---:|---:|
| `arm` (treatment label) | 1 | 0.0% | 0 |
| `availability_map` | 25 | 0.0% | ~14 |
| `capability_manifest` | 345 | 0.3% | ~188 |
| `derived_summaries` start (AWAY_TEAM first) | 2,242 | 1.7% | ~1,224 |
| `derived_summaries.HOME_TEAM` | 55,372 | 42.8% | ~30,233 |
| `fixture` (orientation) | 108,667 | 84.0% | ~59,332 |
| `history_policy` | 108,773 | 84.1% | ~59,390 |
| `match_level_history` key | 109,069 | 84.3% | ~59,552 |
| AWAY_TEAM block span | 109,092 – 114,217 | 84.3% – 88.3% | ~59,564 – ~62,362 |
| **first AWAY_TEAM match row** | **110,198** | **85.2%** | ~60,168 |
| **last AWAY_TEAM match row** | **113,922 – 114,215** | **88.0% – 88.3%** | ~62,201 – ~62,361 |
| HOME_TEAM block span | 114,218 – 123,909 | 88.3% – 95.8% | ~62,363 – ~67,654 |
| **first HOME_TEAM match row** | **115,324** | **89.1%** | ~62,967 |
| **last HOME_TEAM match row** | **123,609 – 123,907** | **95.5% – 95.8%** | ~67,490 – ~67,653 |
| `opponent_profile_context` | 124,095 | 95.9% | ~67,756 |
| `row_encoding` (`COLUMNAR_LOSSLESS`) | 126,307 | 97.6% | ~68,964 |
| `vocabulary` | 126,342 | 97.6% | ~68,983 |

### mt_010243515 (median, 135,057 B ≈ 73,741 tok)

| element | byte offset | % | ≈ token |
|---|---:|---:|---:|
| `arm` | 1 | 0.0% | 0 |
| `availability_map` | 25 | 0.0% | ~14 |
| `capability_manifest` | 345 | 0.3% | ~188 |
| `derived_summaries` (AWAY_TEAM) | 2,246 | 1.7% | ~1,226 |
| `derived_summaries.HOME_TEAM` | 56,043 | 41.5% | ~30,600 |
| `fixture` | 109,821 | 81.3% | ~59,962 |
| `match_level_history` key | 110,223 | 81.6% | ~60,182 |
| AWAY_TEAM block span | 110,246 – 119,896 | 81.6% – 88.8% | ~60,194 – ~65,463 |
| **first AWAY_TEAM match row** | **111,352** | **82.4%** | ~60,798 |
| **last AWAY_TEAM match row** | **119,598 – 119,894** | **88.6% – 88.8%** | ~65,300 – ~65,462 |
| HOME_TEAM block span | 119,897 – 129,559 | 88.8% – 95.9% | ~65,464 – ~70,739 |
| **first HOME_TEAM match row** | **121,003** | **89.6%** | ~66,068 |
| **last HOME_TEAM match row** | **129,263 – 129,557** | **95.7% – 95.9%** | ~70,578 – ~70,738 |
| `opponent_profile_context` | 129,745 | 96.1% | ~70,841 |
| `row_encoding` | 131,961 | 97.7% | ~72,051 |
| `vocabulary` | 131,996 | 97.7% | ~72,070 |

### mt_010441491 (largest, 135,205 B ≈ 73,821 tok)

| element | byte offset | % | ≈ token |
|---|---:|---:|---:|
| `arm` | 1 | 0.0% | 0 |
| `availability_map` | 25 | 0.0% | ~14 |
| `capability_manifest` | 345 | 0.3% | ~188 |
| `derived_summaries` (AWAY_TEAM) | 2,246 | 1.7% | ~1,226 |
| `derived_summaries.HOME_TEAM` | 56,081 | 41.5% | ~30,620 |
| `fixture` | 109,849 | 81.2% | ~59,977 |
| `match_level_history` key | 110,251 | 81.5% | ~60,197 |
| AWAY_TEAM block span | 110,274 – 119,961 | 81.6% – 88.7% | ~60,210 – ~65,499 |
| **first AWAY_TEAM match row** | **111,380** | **82.4%** | ~60,813 |
| **last AWAY_TEAM match row** | **119,677 – 119,959** | **88.5% – 88.7%** | ~65,344 – ~65,498 |
| HOME_TEAM block span | 119,962 – 129,707 | 88.7% – 95.9% | ~65,499 – ~70,820 |
| **first HOME_TEAM match row** | **121,068** | **89.5%** | ~66,103 |
| **last HOME_TEAM match row** | **129,420 – 129,705** | **95.7% – 95.9%** | ~70,663 – ~70,819 |
| `opponent_profile_context` | 129,893 | 96.1% | ~70,922 |
| `row_encoding` | 132,109 | 97.7% | ~72,131 |
| `vocabulary` | 132,144 | 97.7% | ~72,151 |

Output instructions are not in the packet: the system prompt (2,737 B, ~1,495 tok) precedes
the payload, and the response schema is supplied out-of-band via the Bedrock tool/schema
channel.

**Observations (reported, not acted on):**

- The entire match-level record — the sole content that distinguishes Arm B — occupies the
  **final 15.7–18.5%** of the prompt, beginning at 81.5–84.3%.
- `HOME_TEAM` rows are systematically the **last evidence** in the packet, spanning
  88.3–95.9% and ending at 95.8–95.9%; only `notes`, `opponent_profile_context`,
  `packet_hash`, `packet_schema_version`, `row_encoding` and `vocabulary` follow. Under
  alphabetical key ordering, one team's raw evidence is pushed to the tail on **every
  fixture**, deterministically — this is not fixture-specific variance.
- The two teams' records are also asymmetrically placed relative to each other: AWAY_TEAM
  rows occupy roughly 81.6–88.8%, HOME_TEAM rows 88.3–95.9%. The HOME team's entire
  match-level record sits in the last ~12% of the prompt on every fixture.
- `fixture` — the block that establishes *what fixture this is* — sits at **81.2–84.0%**,
  after ~108 KB of aggregates.
- `row_encoding: "COLUMNAR_LOSSLESS"`, the key that tells the reader `values` are
  positional arrays keyed by `columns`, appears at **97.6–97.7%**, i.e. **after** all the
  rows it describes.
- `vocabulary` — declared by the prompt to be "the closed set … you may use" — is the
  **last** block, at 97.7%.
- `opponent_profile_context` sits at 95.9–96.1%.
- Conversely, `availability_map` (300 B) is at 0.0% and `capability_manifest` at 0.3% —
  the constraint blocks are well placed.

No redesign proposed here; recorded for the authorization decision.

---

## 15. Attention-bias / priming assessment — **NONE**

Scanned the system prompt and all 20 serialized payloads for evaluative/directive language:
`important relationship`, `key signal`, `strong divergence`, `use this`, `notable`,
`high-value feature`, `significant`, `striking`, `interesting`, `promising`,
`you should focus`, `most relevant`, `strongest`, `best`, `edge`, `recommend`.

- **Packets (both arms, all 10 fixtures): 0 hits.** No evaluative prose of any kind. The
  packets are pure data structures — no commentary field, no "insight" field, no ordering
  by interestingness.
- **System prompt: 1 hit — `edge`**, in the prohibition *"Do NOT estimate probabilities,
  fair odds, EV, edges, stakes, advantage scores, latent strength, or effect sizes."* This
  is a constraint, not a suggestion. Not priming.
- The prompt does enumerate research directions ("attacking behavior and defensive
  concession; venue …; opponent characteristics …; recent versus longer-run …"), but it
  does so identically for both arms and without asserting that any is valuable or
  divergent. It also actively discourages elaboration: *"Success is NOT more/complex
  hypotheses"* is in the rubric, and the prompt says *"Prefer a simple question when extra
  conditions are unsupported."*

**Frozen label neutrality:**
- `reliability ∈ {LOW, MEDIUM, HIGH}` — a deterministic function of `sample_n`
  (`n ≥ 20` → HIGH, `n ≥ 8` → MEDIUM, else LOW). Mildly evaluative wording, but every
  object carries its `sample_n` alongside, so the label is checkable. The threshold rule
  itself is not stated in the packet (noted as N-4).
- `upcoming_opponent_band ∈ {LOW, MID, HIGH}` — terciles, described neutrally in
  `vocabulary.dimensions.opponent_profile.desc` as *"Band of the opponent's measured
  pre-fixture profile on a named axis. Bands are computed deterministically from history
  strictly before each cohort fixture's kickoff."* No valence attached; HIGH does not mean
  good.
- `status ∈ {AVAILABLE, LOW_COVERAGE, UNAVAILABLE, PIT_UNSAFE}` — factual coverage states.

**Classification: NONE.** Priming is not a reason to withhold authorization.

One structural caveat recorded elsewhere, because it is a demand characteristic rather than
priming: `"arm": "B_full_fidelity"` is the **first key** in the Arm B payload and has no
counterpart in Arm A. The treatment arm identifies itself to the model, unblinded, in the
first 20 bytes. Classified under §18 as M-6.

---

## 16. Arithmetic-burden assessment

**Classification: `SUMMARIES_OVERWHELM_RAW_ROWS`**

The deterministic summaries are, considered alone, well matched to the comparisons the
rubric cares about:

| comparison | summary support | sufficient? |
|---|---|---|
| home vs away | `venue: HOME` / `venue: AWAY` at `ALL_PRIOR`, per metric × side, with `sample_n` | ✅ yes, no arithmetic needed |
| W5/W10 vs longer-run | `W5`, `W10`, `ALL_PRIOR` at `venue: ALL`, per metric × side | ✅ yes |
| team FOR vs opponent AGAINST | `side: FOR` / `side: AGAINST` for all 24 metrics, both teams | ✅ yes |
| opponent-profile response | **no response value, no cohort, no baseline** | ❌ **no** — and the rows cannot substitute, because historical opponents are unbanded (§10) |
| formation coverage | `capability_manifest.coverage.*` + `availability_map.formation` | ✅ yes |

So the arithmetic burden on the *supported* comparisons is low, and the rows are not
required for them. The problem is the converse: the summaries do not *replace* the rows in
content — the rows are complete, canonical and cross-metric-aligned (§5, §7) — but they
overwhelm them in **volume and position**. At 79.6–82.2% of bytes versus 11.5–14.4%, and
with the rows deferred to the final sixth of a ~74,000-token prompt, the packet's structure
points a reader toward pre-chewed scalars and away from the record.

That matters here more than it would in a normal engineering context, because the
experiment's hypothesis is precisely that *exposing the match-level record* changes research
behaviour. The serialization allocates roughly six bytes of aggregate for every byte of
record, and places the aggregates first. If Arm B under-uses the rows, the design will not
be able to separate "the model cannot exploit match-level evidence" from "the packet buried
the match-level evidence behind 58,000 tokens of means."

Note also that the two structures disagree on population where a reader might expect
agreement: a `DERIVED_SUMMARY` at `window: ALL_PRIOR` is the mean over the 30 serialized
rows (`provenance: "mean of serialized match rows"` — correctly stated), whereas the
*same* nominal quantity in Arm A is a shrunk mean over up to 104 matches. Within Arm B the
summaries are internally consistent with the rows; across arms the same label denotes
different things.

**No packet was altered. Reported only.**

---

## 17. Full 10-fixture structural check

| # | FIXTURE | HASH A/B | ROWS H/A | METRIC COLS | EXPOSURE (ser/exp cells) | TRUNC | SECTION BOUNDS | CHRONO ASC | BOTH TEAMS | AVAIL MAP | STABLE EVIDENCE IDs | A/B ISOLATION |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | mt_010243515 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 2 alias collisions | ❌ A n=40 vs B n=30; 19 vs 24 metrics |
| 2 | mt_010243537 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 0 collisions | ❌ A n=104/50 vs B n=30 |
| 3 | mt_010243938 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 1 collision | ❌ A n=69/70 vs B n=30 |
| 4 | mt_010244159 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 1 collision | ❌ A n=71 vs B n=30 |
| 5 | mt_010244193 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 2 collisions | ❌ A n=67 vs B n=30 |
| 6 | mt_010441320 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 1 collision | ❌ A n=64 vs B n=30 |
| 7 | mt_010441491 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 1 collision | ❌ A n=37/79 vs B n=30 |
| 8 | mt_010444904 | ✅ / ✅ | 30 / **14** | 48 | 2,112 / 2,112 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 0 collisions | ❌ A n=56/14 vs B n=30/14 |
| 9 | mt_012232295 | ✅ / ✅ | 30 / 30 | 48 | 2,880 / 2,880 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 0 collisions | ❌ A n=37 vs B n=30 |
| 10 | mt_012232411 | ✅ / ✅ | **27 / 27** | 48 | 2,592 / 2,592 | NONE | ✅ | ✅ | ✅ | ✅ | ❌ 0 summary ids; 1 collision | ❌ A n=27 vs B n=27 (metrics 19 vs 24) |

Column notes:
- **HASH A/B** — packet hash recomputed from body **and** cross-checked against
  `exposure_audit.json`; request hash recomputed against `PREREGISTRATION.json`. 20/20 match.
- **SECTION BOUNDS** — `match_level_history` and `derived_summaries` are distinct top-level
  keys; every summary self-labels `type: DERIVED_SUMMARY`; no raw row appears inside a
  summary list and no summary inside a row block.
- **CHRONO ASC** — `kickoff_unix` strictly ascending in all 20 team blocks; every value
  `< information_cutoff_unix`.
- **BOTH TEAMS** — both `HOME_TEAM` and `AWAY_TEAM` blocks present, non-empty, with
  `n_rows == len(values)`, in every fixture and both arms.
- **AVAIL MAP** — present in **Arm B only**, all 10. Absent from Arm A, all 10.
- **A/B ISOLATION** — fails on every fixture: match population and metric inventory both
  differ (§2.3). Additionally, `valid_ids` = 76 (A) / 0 (B) and firewall
  `evidence_values` = 76 (A) / 0 (B) on every fixture.
- `mt_013233190` is present in both packet files but correctly excluded from the paired set
  and from the manifest (below `min_matches_per_team` in Arm B); the exclusion is symmetric
  across arms and recorded in the prereg. No defect.

---

## 18. Manual human test (§18) — three deeply inspected Arm B packets

Judged as: could a technically competent football analyst, reading **only** this packet,
identify each item? Readability assessment only — no hypotheses generated.

| dimension | mt_010444904 (smallest) | mt_010243515 (median) | mt_010441491 (largest) |
|---|---|---|---|
| how each team has behaved recently | CLEAR (W5/W10 summaries + last rows) — but see AWAY n=14 below | CLEAR | CLEAR |
| how each team has behaved longer-term | CLEAR for HOME (30 rows, 9 months); **READABLE_WITH_EFFORT for AWAY** — 14 rows spanning 3 months is barely "long-term", and only `sample_n` signals it | CLEAR | CLEAR |
| home/away differences | CLEAR (per-row venue + venue-split summaries, n=15/15) | CLEAR | CLEAR |
| attacking output | CLEAR (`_for` columns: shots, SoT, xG, npxG, big chances, touches in box, final third entries, corners, crosses) | CLEAR | CLEAR |
| defensive concession | CLEAR (`_against` mirror of every metric, plus saves, clearances, blocks, interceptions, tackles) | CLEAR | CLEAR |
| opponent-profile context | **AMBIGUOUS** — bands present but HOME/AWAY key direction unstated and inverted vs intuition; no cohort, no response, no baseline (§10) | **AMBIGUOUS** (same) | **AMBIGUOUS** (same) |
| metric co-movement | CLEAR — row-major, 55 aligned cells per match (§7) | CLEAR | CLEAR |
| formation context where available | CLEAR that it is **not** meaningfully available: 22/88 recorded, `LOW_COVERAGE` | CLEAR (20/120, `LOW_COVERAGE`) | CLEAR (32/120, `LOW_COVERAGE`) — highest of the ten and still low |
| what information is unavailable | CLEAR — `availability_map` (11 keys) + `capability_manifest.unsupported_context` (5 prose entries) | CLEAR | CLEAR |

Cross-cutting readability risks affecting all three equally:

- **READABLE_WITH_EFFORT — chronology.** Epoch integers only; ordering direction stated in
  the system prompt but nowhere in the packet.
- **READABLE_WITH_EFFORT — `HOME` token overloading.** Four distinct meanings, no glossary
  (§6).
- **AMBIGUOUS — metric semantics.** `accurate_crosses` (no denominator), `xg` vs `npxg`
  (no definition, and `npxg > xg` in 26.8% of pairs — M-8), shot decomposition,
  `possession` units,
  `dangerous_attacks` in the vocabulary but excluded from the data (§6). No
  `source_provider` / `source_field` anywhere in Arm B.
- **NOT_AVAILABLE — evidence citation.** Nothing in the packet gives the analyst a way to
  name a derived summary (§12).

Overall: an analyst *can* extract the football content from an Arm B packet. The
serialization does not hide the data. Where it fails is in naming the data (citation),
orienting the opponent-profile block, defining the metrics, and placing the record where it
will actually be read.

---

## 19. Cognitive information density — Arm A vs Arm B

| measure | ARM A | ARM B | ratio B:A |
|---|---:|---:|---|
| serialized bytes (median fixture mt_010243515) | 36,529 | 135,057 | **3.70×** |
| estimated input tokens (median) | 19,944 | 73,741 | **3.70×** |
| estimated input tokens (manifest, incl. system) | 23,429 | 77,226 | 3.30× |
| historical observations exposed | **0** | 44–60 | ∞ |
| actual metric cells | 74–76 scalars | 2,112–2,880 cells | **~37×** |
| derived summaries | 76 (all evidence *is* derived) | 462–480 | 6.1× |
| top-level sections | 11 | 15 | 1.36× |
| distinct metrics | 19 | 24 | 1.26× |
| conditioning dimensions actually exercised by the data | **0** (venue=ALL, window=ALL_PRIOR only) | **4** (venue, window W5/W10/ALL_PRIOR, opponent alias, competition) + formation at low coverage | — |
| provider provenance per item | ✅ `source_provider` + `source_field` on all 76 | ❌ **none anywhere** | **0×** |
| stable citable evidence ids | 76 | **0 resolvable** | **0×** |
| firewall-resolvable evidence values | 76 | **0** | **0×** |

Per-fixture detail:

| fixture | A bytes | A tok | B bytes | B tok | B observations | B metric cells | B summaries |
|---|---:|---:|---:|---:|---:|---:|---:|
| mt_010243515 | 36,529 | 19,944 | 135,057 | 73,741 | 60 | 2,880 | 480 |
| mt_010243537 | 36,697 | 20,036 | 134,980 | 73,699 | 60 | 2,880 | 480 |
| mt_010243938 | 36,527 | 19,943 | 135,107 | 73,768 | 60 | 2,880 | 480 |
| mt_010244159 | 36,534 | 19,947 | 135,082 | 73,754 | 60 | 2,880 | 480 |
| mt_010244193 | 36,548 | 19,955 | 135,095 | 73,761 | 60 | 2,880 | 480 |
| mt_010441320 | 36,542 | 19,951 | 135,147 | 73,790 | 60 | 2,880 | 480 |
| mt_010441491 | 36,529 | 19,944 | 135,205 | 73,821 | 60 | 2,880 | 480 |
| mt_010444904 | 36,611 | 19,989 | 129,403 | 70,654 | 44 | 2,112 | 476 |
| mt_012232295 | 36,623 | 19,996 | 131,885 | 72,009 | 60 | 2,880 | 466 |
| mt_012232411 | 35,768 | 19,529 | 129,476 | 70,693 | 54 | 2,592 | 462 |

**Does Arm B add usable structure, or merely volume?** Both, and the split is measurable.

*Genuinely new usable structure* (not obtainable from Arm A at any effort):
- match-level rows with aligned cross-metric co-occurrence — 37× more metric cells, and
  the only place in either arm where two metrics can be read off the same match;
- venue attached to the observation, enabling venue-conditioned reasoning that Arm A cannot
  express at all;
- explicit W5 / W10 / ALL_PRIOR windows against Arm A's single `ALL_PRIOR`;
- dated chronology;
- an `availability_map` that gives the prompt's abstention instruction something to bind to;
- 5 additional metrics.

*Volume without corresponding structure:*
- the 462–480 derived summaries are **79.6–82.2% of the bytes** but are strictly derivable
  from the rows (`provenance: "mean of serialized match rows"`), and they carry ~58,000 of
  the ~74,000 input tokens. Roughly **4.8× the entire Arm A packet, spent on restating
  arithmetic over the rows in the same packet.**
- `opponent_profile_context` is 1.5–1.6% of bytes and, per §10, adds a band label without a
  cohort — structure without the data to use it.

*Net regressions* in Arm B despite being 3.7× larger:
- provider provenance: 76 items → 0;
- resolvable evidence ids: 76 → 0;
- underlying match population: up to 104 per team → 30.

So "larger" is emphatically not "better" here. Arm B adds the one structure the experiment
needs (the record), buries it in the last sixth of the prompt behind an aggregate block
five to seven times its size, and drops two properties (provenance, citability) that the
shared evaluation stack depends on.

---

## 20. Defects by severity

### HARD_STOP

**HS-1 — Arm B evidence references cannot resolve; grounded acceptance is 0 by construction.**
`validator_v2` (L116–118) and `validator._validate_one` (L264) build `valid_ids` solely from
`packet["evidence"][*]["id"]`. Arm B has no `evidence` key: `valid_ids` = ∅ for all 10
fixtures. Every `SUFFICIENT` hypothesis is rejected whatever it cites; an empty
`evidence_refs` is rejected too. `firewall_v2.evidence_values()` is coupled the same way
(76 values for A, 0 for B), so firewall provenance is asymmetric. Demonstrated empirically
at zero spend: an identical, well-formed, grounded hypothesis is `accepted=True` in Arm A and
`accepted=False / INSUFFICIENT_EVIDENCE` in Arm B.

*Mapping note, stated plainly rather than forced into a listed bucket:* this finding does
**not** correspond to any single entry on the mandate's HARD STOP enumeration. The rows
genuinely are raw canonical observations, so *"rows not actually raw canonical
observations"* does not apply, and the provenance gap is a separate finding (M-5). HS-1 is a
HARD STOP on the more general ground that it makes the experiment's **primary outcome
measure structurally unattainable in the treatment arm before any spend** — `groundedness`,
`evidence_referenced_rate` and `compilability` are all pinned at zero for Arm B by the
shared stack, independently of anything Sonnet produces. That is a superset of the
enumerated conditions, and is sufficient on its own to withhold authorization.

**HS-2 — Arm A and Arm B differ in more than evidence representation.**
Five unintended differences (§2): (a) match population — Arm A aggregates the full prior
history (14–104 matches/team) while Arm B is capped at 30, so Arm B is not a superset of Arm
A's information and Arm A's values are additionally `SHRUNK`; (b) metric inventory — 19 vs
24 metrics, with `capability_manifest` differing accordingly; (c) `formation_distribution`
present only in Arm A, changing the ontology the shared availability layer produces;
(d) `history_policy` governs Arm B only; (e) `arm: "B_full_fidelity"` unblinds the treatment
arm in the payload's first key. Falsifies the preregistered
`shared_stack.only_evidence_representation_differs: true`. Maps directly to the mandate's
HARD STOP *"Arm A/B differ in more than evidence representation"*.

**HS-3 — The shared prompt invites unsupported dimensions, with no abstention path in Arm A.**
The single `SYSTEM_PROMPT` promises "for both teams" four blocks Arm A does not contain
(`match_level_history`, `derived_summaries`, `opponent_profile_context`, `availability_map`)
and invites venue, recent-vs-long and opponent-profile reasoning that Arm A cannot support
(all 76 items are `venue: ALL`, `window: ALL_PRIOR`). §13 counts **11 UNSUPPORTED invited
dimensions for Arm A and 6 for Arm B**. The §17 escape clause is not met: Arm A has no
`availability_map` for the prompt's "do not ask about an unavailable dimension" rule to bind
to, and `data_quality.n_unavailable: 0` affirmatively signals the opposite. This is the V3
mistake reproduced in the control arm, and it biases the comparison toward Arm B.

### MATERIAL_SCIENTIFIC_DEFECT

**M-1 — Derived summaries dominate and precede the raw record.** 79.6–82.2% of bytes
(~58,000 tok) vs 11.5–14.4% for rows (~8,100–10,600 tok); raw:summary 1:5.54 to 1:7.18. The
match-level record begins at 81.5–84.3% of the prompt; `HOME_TEAM` rows are deterministically
last among the evidence, spanning 88.3–95.9%. `fixture` orientation appears at 81.2–84.0%; `row_encoding` — which
explains how to read `values` — at 97.6–97.7%, after the rows; `vocabulary` last. Caused by
`sort_keys=True` plus a verbose 10-key summary object (~220 B/scalar vs ~330 B per 55-cell
match). The rows are complete and are not replaced, so this is not the literal "summaries
replace raw rows" HARD STOP — but it confounds the experiment's central hypothesis: low Arm
B row usage could not be distinguished from burial.

**M-2 — Opponent-profile block cannot support the reasoning it is declared to support.**
Only the upcoming opponent's tercile band is serialized: no response metric, no baseline, no
cohort N (`candidate_n`/`bandable_n` size the banding pool, not a cohort). **Historical
opponents are not banded**, so no similar-opponent comparison is constructible from the
packet. Direction is ambiguous: the `HOME`/`AWAY` keys are *subject* labels, so
`axes.X.HOME.upcoming_opponent_band` is the **AWAY_TEAM's** band — the inverse of the
natural reading, in a packet where `HOME`/`AWAY` means venue everywhere else. Meanwhile
`availability_map.opponent_profile = AVAILABLE` (all 10), the rubric scores
`appropriate_opponent_profile_use`, and `research_families` offers
`OPPONENT_PROFILE_INTERACTION`. The builder docstring describes a response cohort the
implementation does not construct.

**M-3 — Vocabulary advertises capabilities neither packet backs, with no precedence rule.**
The prompt calls `vocabulary` "the closed set … you may use". It offers metrics `attacks`,
`dangerous_attacks`, `total_bookings` (absent from both packets; `dangerous_attacks` is an
explicit `DO_NOT_MERGE` semantic exclusion the packet never mentions); dimensions
`half_score_state`, `period`, `referee` (all unavailable); window `SEASON_TO_DATE` (no
season field on any row); comparisons `LEAGUE_ENVIRONMENT_BASELINE` and
`SUBJECT_COMPETITION_BASELINE` (no such evidence); and 15 `opponent_profile` axes against 8
banded. `schema_v2` accepts all of them. Nothing states that `capability_manifest` overrides
`vocabulary`.

**M-4 — Ambiguous evidence identifiers.** Derived summaries carry **no `id`** (≈480 per
packet). `match_alias` collides across teams in **9 instances over 7 of 10 fixtures**, where
the same alias names two rows of opposite FOR/AGAINST orientation. Even if HS-1 were fixed,
a reference like `m_mt_252067206` would not identify a perspective.

**M-5 — Arm B carries no provider provenance.** Arm A has `source_provider` and
`source_field` on all 76 items; Arm B has neither on any row or summary. Combined with the
firewall coupling (76 vs 0 resolvable evidence values), provenance and firewall treatment
differ systematically between arms.

**M-6 — Unblinded treatment label in the payload.** `"arm": "B_full_fidelity"` is the first
key of every Arm B payload (offset 1); Arm A carries no `arm` key. The model is told which
arm it is in, in the first 20 bytes, in an experiment whose outcome is the model's own
behaviour.

**M-7 — Metric semantics are not defined anywhere in the packet.** `vocabulary.metrics` is a
bare name list. Unresolvable from the packet: `accurate_crosses` (completions with no
attempts denominator), `xg` vs `npxg` (undefined; `npxg > xg` occurs in the data),
shot-family exhaustiveness (`total_shots` vs on/off/blocked vs inside/outside box),
`possession` units, second-yellow handling, and the `dangerous_attacks` provider exclusion.
The `xg`/`npxg` inconsistency quantified in M-8 is the concrete cost of this gap.
The mandate is explicit that "Sonnet should not need to infer provider semantics from names
alone"; in Arm B it must, and Arm B is the arm being tested.

**M-8 — `xg` and `npxg` are mutually inconsistent in 26.8% of rows.** Measured across all
1,050 comparable `(xg, npxg)` value pairs in the ten Arm B packets (106 further pairs are
null): `npxg > xg` in **281 pairs (26.8%)**, `npxg == xg` in 422 (40.2%), `npxg < xg` in 347
(33.0%). The excess reaches **1.01 xG** (mean 0.088) — far beyond independent rounding of two
fields. Non-penalty xG cannot exceed total xG under any standard definition, so the two
columns are not drawn from a consistent provider definition. Both are **new in Arm B** (Arm A
exposes neither), `availability_map.xg` asserts `AVAILABLE` on all 10 fixtures, and the
packet carries no `source_field` or `source_provider` for a reader to diagnose the conflict.
A hypothesis contrasting xG with npxG — an obvious and legitimate research question given
that both columns are offered — would be grounded in incoherent data. This falls under the
mandate's stop rule *"semantic conflict"*, alongside the `dangerous_attacks` exclusion the
packet does not disclose.

*(Builder reference, for the fix in a new version:
`v5a_full_fidelity._EXTRA_SOURCE` reads `xg` from `base.team_a_xg`/`team_b_xg`, while `npxg`
is inherited from `corpus_adapter._METRIC_SOURCE`. The two paths are not reconciled. No
change made here.)*

### NON_BLOCKING

- **N-1** — `kickoff_unix` is a bare epoch integer; no ISO date anywhere in the packet.
- **N-2** — Chronological direction is stated only in the system prompt, never in the
  packet (`columns` and `notes` are silent on ordering).
- **N-3** — W5/W10 are never mapped onto row indices; the reader must infer `rows[-5:]`.
- **N-4** — `reliability` thresholds (n≥20 HIGH, n≥8 MEDIUM) exist only in code, not in the
  packet; `sample_n` is present alongside, so the label is checkable.
- **N-5** — `null` semantics are unexplained: provider-missing vs not-applicable is
  indistinguishable. Null and zero *are* correctly distinct (e.g. 112 nulls vs 207 genuine
  zeros in mt_010244159).
- **N-6** — `similarity_version: "opponent_similarity_v1_pending"` — a `_pending` version
  string frozen into a spend-authorising artifact.
- **N-7** — History spans vary widely for the same 30 rows (9.3 months vs 3.2 months) and
  between teams within a fixture; nothing in the packet flags this, so "recent" is not
  comparable across teams or fixtures without computing spans from epoch integers.
- **N-8** — `fixture` is degenerate (`home: "HOME_TEAM"`, `away: "AWAY_TEAM"`,
  `competition: "COMPETITION"`), restating the alias constants and conveying nothing beyond
  confirming that HOME_TEAM is at home.

### COSMETIC

- **C-1** — `BYTELEVEL_ARM_*.request.txt` exist for only 1 of 10 fixtures and use a
  `=== SYSTEM === / === USER (exact bytes) ===` wrapper. Verified faithful (the USER section
  equals `build_user_payload` exactly), so this is a coverage gap, not a fidelity problem.
- **C-2** — `build_opponent_profile_context` docstring describes behaviour
  ("report the subject's response cohort vs its overall baseline") that the function does not
  implement. Documentation, not data — but it is how M-2 escaped notice.

### Confirmed clean (no defect)

Hash integrity 20/20 · packet hashes agree with the exposure audit · Arm A byte-identical to
the frozen V3 packets · byte-level dumps faithful · no truncation, no `"..."`, no abbreviated
arrays, no clipped trailing rows · declared rows = serialized rows 10/10 · 48/48 metric
columns 10/10 · `cell_fidelity` 27,744 cells, 0 mismatches · `UNEXPLAINED_OMISSION` 0 · both
teams present 10/10 · chronology strictly ascending 20/20 blocks · no future data, no
target-fixture row, no target outcome · 0 identity leaks across 30 real-name tokens ×
20 payloads · **cross-metric match-level alignment preserved (row-major, 55 cells/row,
1,076 rows verified)** · venue attached to every observation · formation availability
honestly and redundantly signalled, expected formation correctly withheld · **priming NONE**
· CHAMPION artifact sha256 unchanged · `mt_013233190` symmetrically excluded from both arms.

---

## 21. Authorization recommendation

### ABORT_V5A_CURRENT_VERSION

Three findings independently satisfy the mandate's HARD STOP conditions, and none can be
repaired in place without re-freezing the experiment.

**Why a new frozen version is required, specifically:**

1. **HS-1 is not a packet bug — it is a contract mismatch between Arm B and the shared
   evaluation stack.** `validator_v2` and `firewall_v2` both resolve evidence through
   `packet["evidence"]`, a V3-shaped key. Fixing it means either giving Arm B a flat,
   id-bearing `evidence` projection (changing the packet and every Arm B hash) or teaching
   the validator and firewall to resolve `match_alias` and summary ids (changing
   `module_hashes` for `validator_v2.py` and `firewall_v2.py`, both preregistered). Either
   way `request_manifest`, `serialized_request_sha256` and `schema_content_hash` move. That
   is a new frozen version by definition. Spending $7.18 first would buy a
   guaranteed-zero Arm B groundedness score that measures the plumbing, not the science.

2. **HS-2 means the current design cannot attribute any measured difference to evidence
   representation.** Arm A sees shrunk means over up to 104 matches across 19 metrics; Arm
   B sees raw rows over 30 matches across 24 metrics, under a different ontology, with a
   self-identifying arm label. Whatever the result, "full-fidelity evidence helps" would be
   confounded with "a 30-match window", "five extra metrics", "unshrunk values" and "the
   model knew it was the treatment arm". Restoring isolation requires choosing a single
   history policy and metric inventory for both arms and rebuilding both packet sets — a
   re-freeze.

3. **HS-3 handicaps the control.** Arm A is asked about venue, recency and opponent profile
   with no such evidence and no availability map to abstain against, while
   `data_quality.n_unavailable: 0` tells it nothing is missing. An Arm B advantage under
   this prompt is partly an artifact of a control arm set up to fail. The fix is either an
   arm-appropriate abstention contract or an Arm A availability map — both change the frozen
   prompt or the frozen Arm A packets.

**Do NOT repair V5A in place.** Every candidate fix moves a preregistered hash. Editing the
frozen artifacts and re-running the freeze script would silently invalidate the
preregistration that gives the experiment its evidential value.

M-8 is additionally a live **stop rule** in the frozen preregistration (`semantic conflict`)
and would have to be resolved — or `xg`/`npxg` withdrawn — before either arm is run, since
Arm B offers both columns and declares them available.

**What V5B should carry forward unchanged** (verified sound by this audit and worth
preserving verbatim): the columnar row-major encoding and its cross-metric alignment; the
exposure-audit discipline (`cell_fidelity`, `UNEXPLAINED_OMISSION`, declared
`omission_reason`); PIT enforcement and alias neutrality; the `availability_map` /
`unsupported_context` design; formation honesty; and the packets' complete absence of
evaluative or priming language.

**Suggested scope for a new frozen version** (recorded for the human decision-maker; no
changes made here): a shared history policy and metric inventory across arms; explicit
stable evidence ids on both rows (`HOME_M01`…, `AWAY_M01`…) and summaries
(`SUMMARY_HOME_CORNERS_FOR_W5`…) with validator/firewall resolution to match; reconciliation
or withdrawal of the `xg`/`npxg` pair; a
per-observation opponent band or an honest `availability_map.opponent_profile =
LOW_COVERAGE`; metric definitions and provider provenance in the packet; an ordered
serialization that places fixture orientation, `row_encoding` and vocabulary before the
data and does not defer one team's record to the final 11% of the prompt; and removal of the
`arm` label from the payload.

---

## FINAL DECISION

The packets are frozen and intact, contain the full admitted match-level record with no
silent truncation, preserve match-level cross-metric structure, and are free of priming.
They fail on experimental isolation, on evidence-reference resolvability, and on
prompt-to-data support.

**V5A_PACKET_INSPECTION_ABORT**

**BEDROCK_SPEND_AUTHORIZED_BY_AUDIT: NO**

This audit does not authorize spend. It was conducted entirely offline: 0 Bedrock calls,
0 LLM calls, 0 network calls, 0 bytes of packet, prompt, schema, manifest, threshold,
experiment-design, V2/V3/V4, CHAMPION or `p_model` state modified. Explicit human
authorization remains required after reviewing this report — and on the findings above, the
correct next step is a new preregistered frozen version, not authorization of the current
one.
