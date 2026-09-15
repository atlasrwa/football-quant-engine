# V5A.1 Provider Semantics Audit

**Experiment:** `V5A.1_FULL_FIDELITY_EVIDENCE_INTERFACE`
**Mandate:** §16 (resolve xG/npxG before refreeze) and §17 (provider semantics gate)
**Date:** 2026-09-14 · **Spend:** $0 · **Bedrock/LLM/network calls:** 0

Every claim below was measured against the raw provider payloads in
`data/thestatsapi/championship/stats_mt_*.json` (1,656 files), not inferred from field names.

---

## 1. Provider topology — correcting a V5A audit finding

The V5A packet audit recorded defect **M-8** as a suspected cross-provider merge: `xg` read
from `MatchRecord.base["team_a_xg"]` (a FootyStats-schema key) and `npxg` from
`MatchRecord.rich["np_expected_goals"]` (a TheStatsAPI key).

**The finding was right; the attributed mechanism was wrong.** The inconsistency M-8
reported is real and reproduces at the raw-provider level (15.8% of pairs, §2.2) as well as
in the packets (26.8% of cells) — only the *cause* was misattributed.
`scripts/championship_adapter.py`
populates `team_a_xg` / `team_b_xg` from TheStatsAPI's own `overview.expected_goals`
(lines 54–55, 79–80). The FootyStats-style key is a **schema name only**; the value is
TheStatsAPI's. Both fields are therefore single-provider.

So M-8's observation stands in full — the two columns are mutually inconsistent, at a rate
slightly higher than M-8 measured — but the cause is inside the provider feed, not in our
merge. Nothing about the exclusion decision changes; the reason recorded for it does. Every
metric exposed in V5A.1 comes from
**TheStatsAPI**, read through `championship_adapter`. There is no cross-provider merge
anywhere in the V5A.1 evidence path, so §17's "if two providers disagree semantically, keep
them separate" does not arise.

---

## 2. xG / npxG — resolution (§16, a hard pre-spend dependency)

### 2.1 The intended relationship is confirmed by the data

Across all raw `(overview.expected_goals, np_expected_goals.all)` pairs (n = 3,242):

| xG − npxG (0.1 bins) | count | reading |
|---|---:|---|
| **+0.0** | **2,214** | no penalty in the match — the two agree exactly |
| +0.1 | 150 | |
| +0.2 | 56 | |
| +0.3 | 23 | |
| +0.4 | 24 | |
| +0.5 | 10 | |
| +0.6 | 17 | |
| +0.7 | 24 | |
| **+0.8** | **182** | one penalty (penalty xG ≈ 0.79) |
| +0.9 | 15 | |
| **+1.6** | **6** | two penalties |
| −0.1 | 300 | **impossible** under npxG = xG − penalty xG |
| −0.2 | 114 | impossible |
| −0.3 | 41 | impossible |
| −0.4 | 29 | impossible |
| −0.5 | 9 | impossible |
| −0.6 | 6 | impossible |

The modes at +0.0, +0.8 and +1.6 establish the definition unambiguously: **npxG is
non-penalty xG and `overview.expected_goals` is total xG.** Of the 517 pairs differing by
more than +0.05, 201 (38.9%) fall in [0.70, 0.85] — penalty-shaped.

### 2.2 …and violated in one pair in six

| measure | value |
|---|---|
| raw pairs compared | 3,242 |
| `npxg > xg` by more than 0.05 | **511 (15.8%)** |
| mean violation | −0.177 |
| worst violation | **−0.990** |
| shape of the violation distribution | smooth and monotone decaying (300 / 114 / 41 / 29 / 9 / 6), **not** penalty-shaped |

Measured again on the packet side (the 10 V5A Arm B packets, 1,050 comparable cell pairs):
`npxg > xg` in **281 pairs (26.8%)**, excess up to 1.01, mean excess 0.088.

Non-penalty xG cannot exceed total xG. A smooth error distribution with no penalty mode is
the signature of **two independently-maintained provider estimates** that are refreshed
asynchronously, not of a derived pair.

### 2.3 Can npxG be repaired rather than dropped?

No. Repair would need a penalty or penalty-xG field to recompute npxG from xG. Scanning
every key of `MatchRecord.base`, `.rich` and `.extra` across the corpus, the only
penalty-like field is `touches_in_penalty_area` — a location count, unrelated to penalty
kicks. **There is no penalty field in this corpus**, so npxG cannot be reconstructed.

### 2.4 Classification and decision

| §16 category | verdict |
|---|---|
| provider semantics legitimate | ✗ — the definitional relationship is violated in 15.8% of observations |
| **provider-source inconsistency** | ✅ **THIS** |
| normalization bug | ✗ — `championship_adapter` reads both fields faithfully from their documented nodes |
| field mapping bug | ✗ — both map to the correct TheStatsAPI nodes, same provider |
| unknown | ✗ — the mechanism is identified |

**DECISION: `npxg` is EXCLUDED from V5A.1 model-visible evidence.** `xg` (total, penalties
included) is exposed with its coverage declared. The exclusion is serialized into every
packet in the `METRIC_SEMANTICS.excluded_metrics` block with the reason above, so the model
sees that the omission is deliberate rather than an accident.

Enforced by `test_xg_npxg_semantics_resolved_or_npxg_excluded`: `npxg` is absent from
`CANONICAL_METRICS`, present in `EXCLUDED_METRICS`, the string `npxg_for` appears in no
payload, and a hypothesis targeting `npxg` is refused by the admissibility gate in both arms.

### 2.5 xG coverage

Corpus-wide `xg` coverage is **4,194 / 5,319 = 78.85%** — matching the 78.8% the aborted
V5A claimed. Per fixture, coverage over the serialized rows is measured at build time and
declared in the availability map as `EXPOSED` (≥ 50%) or `EXPOSED_LOW_COVERAGE`. The
metric's `caveat` field states the coverage and that non-penalty xG is not available.

---

## 3. Red cards — a second semantics question the V5A audit did not reach

`overview.red_cards` at the provider, over 3,312 team-matches:

| value | count |
|---|---:|
| `null` | 2,988 (90.2%) |
| `0` | 154 |
| `1` | 166 |
| `2` | 4 |

`championship_adapter` coerces null → 0 (`rc_h if rc_h is not None else 0`). The provider
emits an explicit `0` sometimes, so null is not self-evidently "omitted zero" — the question
had to be settled empirically.

- `yellow_cards` is null in exactly **160** team-matches, and **all 160** coincide with a
  null `red_cards`: those are matches where the whole card block is missing.
- That leaves 2,828 team-matches where yellows are reported and reds are null.
- Treating null as zero gives **170 red cards in 3,152 reported team-matches = 5.4%**, which
  matches the real-world per-team red-card rate.

**DECISION: `red_cards` is EXPOSED**, with `null_policy: NULL_COERCED_TO_ZERO_AT_ADAPTER`
and a model-visible caveat stating the counts and warning that a `0` in that column may be a
provider omission rather than an observed zero. The coercion is justified, and the model is
told so rather than left to discover it.

---

## 4. Decomposition identities — verified, then documented

The V5A packet audit flagged shot-family semantics as AMBIGUOUS because nothing in the
packet said which decomposition was exhaustive. Both are now measured and stated:

| identity | exact | differ | verdict |
|---|---:|---:|---|
| `total_shots == shots_on_target + shots_off_target + blocked_shots` | 3,266 | 6 | **holds (99.8%)** |
| `total_shots == shots_inside_box + shots_outside_box` | 3,270 | 2 | **holds (99.9%)** |
| `possession_home + possession_away == 100` | 1,636 | 0 | **holds (100%)** |

These are written into `METRIC_SEMANTICS`, so `blocked_shots` says it is counted inside
`total_shots`, `shots_inside_box` says the inside/outside split is exhaustive, and
`possession` says it is a percentage whose two sides are complementary.

---

## 5. Per-metric semantics gate (§17)

All 23 exposed metrics carry `source_field`, `provider`, `units`, `definition`, `direction`,
`null_policy` and `merge_policy`, asserted by
`test_every_exposed_metric_has_documented_semantics`. Every metric is `SINGLE_SOURCE_NO_MERGE`.

| metric | source (TheStatsAPI) | units | note |
|---|---|---|---|
| accurate_crosses | `passes.accurate_crosses` | count | completions only; **no attempts denominator exists**, so it is not a rate |
| big_chances | `overview.big_chances` | count | subjective provider classification |
| blocked_shots | `shots.blocked_shots` | count | counted inside `total_shots` (verified) |
| clearances | `defending.clearances` | count | |
| corners | `overview.corner_kicks` | count | |
| final_third_entries | `passes.final_third_entries` | count | |
| fouls | `overview.fouls` | count | |
| goals | fixture score (`score_home`/`score_away`) | count | from the result, not the stats block |
| interceptions | `defending.interceptions` | count | |
| offsides | `attack.offsides` | count | |
| possession | `overview.ball_possession` | percent | sums to 100; the two sides are the same information |
| red_cards | `overview.red_cards` | count | null→0 coercion, justified in §3 |
| saves | `goalkeeping.saves` | count | |
| shots_inside_box | `shots.shots_inside_box` | count | inside+outside exhausts `total_shots` |
| shots_off_target | `shots.shots_off_target` | count | |
| shots_on_target | `overview.shots_on_target` | count | includes saved and scored |
| shots_outside_box | `shots.shots_outside_box` | count | |
| tackles | `defending.tackles` | count | |
| throw_ins | `passes.throw_ins` | count | |
| total_shots | `overview.total_shots` | count | both decompositions verified exhaustive |
| touches_in_box | `attack.touches_in_penalty_area` | count | exposed under its own name, never as "dangerous attacks" |
| xg | `overview.expected_goals` | float_xg | **total xG, penalties included**; 78.9% coverage |
| yellow_cards | `overview.yellow_cards` | count | a second yellow is counted in both card columns |

### Excluded, with the reason serialized into every packet

| metric | category | reason |
|---|---|---|
| **npxg** | PROVIDER_SOURCE_INCONSISTENCY | §2 above |
| **dangerous_attacks** | SEMANTIC_CONFLICT_NO_CANONICAL_MAPPING | corpus carries only `touches_in_penalty_area` as a proxy; exposing it under the FootyStats concept name would be a false canonical metric created by name matching (§17). `touches_in_box` is exposed under its own name instead |
| **attacks** | NOT_PROVIDED_BY_SOURCE | no field in either corpus supplies it |
| **total_bookings** | DERIVED_NOT_OBSERVED | would be `yellow_cards + red_cards`, but reds carry a coercion policy and a second yellow is double-counted; both components are exposed separately |

`schema_v2` and `vocabulary` are frozen and still admit all four names. They are blocked
**per packet** by `v5a1_admissibility`, and the packet declares the exclusions so the model
can see the same boundary the gate enforces. This is the fix for V5A defect M-3.

---

## 6. Non-metric context

`UNSUPPORTED_CONTEXT` is serialized into every packet and covers `expected_formation`,
`lineup`, `injuries`, `weather`, `player_ratings`, `referee`, `minute_level_events`,
`half_time_state` and `market_prices`. Each states what is missing and why. The availability
map carries the matching declaration with the full exposure triple.

---

## 7. Outcome

**`V5A1_PROVIDER_SEMANTICS_VALIDATED`**

Every exposed metric has a documented source, direction, unit, null policy and merge policy;
every exclusion has a measured reason; the xG/npxG conflict is resolved by exclusion with the
evidence recorded; no ambiguous field is silently retained and no exclusion is silently made.
