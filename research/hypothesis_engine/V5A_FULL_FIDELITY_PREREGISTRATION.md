# V5A — Full-Fidelity Hypothesis-Engine Experiment (PREREGISTRATION)

**Purpose.** Correct the architectural weakness the V3 forensic audit found: V3 exposed
only unconditional shrunk scalar means (`venue=ALL, window=ALL_PRIOR`), so it never fairly
tested the intended LLM research architecture. V5A exposes the **full PIT-safe canonical
match-level football record** under a frozen history policy, then asks the LLM only *what
the deterministic engine should measure*.

**Status: design + zero-spend verification complete. NO Bedrock call has been made.**
Ends at a human spend-authorization gate. `$0.00` spent.

**Governing architecture (unchanged, enforced):** historical provider data → canonical
normalization → PIT fixture research corpus → **full-fidelity LLM research view** → LLM
hypothesis specification → typed deterministic compilation → deterministic measurement →
… → p_model → market → prospective. The LLM is the **research-question layer only** and owns
no numerical predictive authority. A test proves there is no LLM→`p_model` import path.

---

## Experiment design (Phase 20)

| | |
|---|---|
| **Arm A** | frozen V3 compressed evidence body (76 unconditional shrunk scalars), verbatim |
| **Arm B** | full match-level PIT-safe research view (columnar-lossless rows) + DERIVED_SUMMARY + opponent-profile bands + availability map |
| **Only material difference** | evidence representation |
| Shared, identical across arms | model `us.anthropic.claude-sonnet-4-6`; temperature 0.0; **schema_v2** (`7879c6ad…`, identical to V3); validator_v2; firewall_v2; compiler `query_plan.compile_hypothesis`; vocabulary `hypothesis_vocabulary_v1`; aliases HOME_TEAM/AWAY_TEAM/COMPETITION/OPP_nnn; max 12 hypotheses; scoring |

The A/B contrast isolates the effect of evidence fidelity on hypothesis groundedness.

**Fixtures (Phase 20, "same target fixtures where possible"):** the 10 clean V3 reference
fixtures buildable in **both** arms — `mt_010243515, mt_010243537, mt_010243938,
mt_010244159, mt_010244193, mt_010441320, mt_010441491, mt_010444904, mt_012232295,
mt_012232411`. **Excluded:** `mt_013233190` (4 prior matches < `min_matches_per_team=6`;
a genuine data limit; excluded from **both** arms to keep the pairing symmetric).

**Repeatability (self-noise):** the first 3 fixtures are called **3 extra times per arm**
(6 fixture-arms × 3 = 18 extra calls) to estimate generator self-noise, mirroring the V3
repeatability finding (same-input plan overlap ~0.22).

Frozen call counts: **20 base + 18 repeatability = 38 calls.** No other calls permitted.

---

## Phase 1-2 — Provider inventory & canonical normalization

Canonical match metrics exposed as match-level columns (**24**), with provenance
(reuses `corpus_adapter._METRIC_SOURCE` verbatim, plus xg and red_cards which V3 omitted):

- **TheStatsAPI rich:** corners, accurate_crosses, shots_on_target, shots_inside_box,
  shots_outside_box, blocked_shots, touches_in_box, final_third_entries, tackles,
  interceptions, clearances, big_chances, npxg, saves, fouls.
- **extra (raw /stats):** total_shots, shots_off_target, possession, throw_ins, offsides.
- **base:** goals, yellow_cards, **xg** (78.8% corpus coverage), **red_cards** (100%).
- **Excluded — semantic ambiguity:** `dangerous_attacks` (corpus carries only a proxy,
  `touches_in_penalty_area`; no validated canonical mapping → `DO_NOT_MERGE`).
- **Unavailable — measured, not assumed:** HT goals **0.0%** coverage in this corpus →
  `half_time_state = UNAVAILABLE`; injuries/weather/expected-formation absent; lineup
  announcement timestamp unproven → `PIT_UNSAFE`.

Cross-provider pooling is not performed: this corpus is single-provider (TheStatsAPI rich).
Provider provenance is carried on every value and preserved through serialization; a test
asserts it survives.

## Phase 3-4 — PIT cut & frozen history policy

- **Cutoff = target kickoff.** Admissible = kickoff **strictly** `< cutoff`. Target fixture,
  future fixtures, outcomes, settlement, closing line, future odds/lineup/injury/formation
  all excluded. Positive leakage tests injected and pass (§tests).
- **Frozen history policy (`history_policy_v1`), chosen before spend, identical per
  fixture, independent of any outcome/V4 result:** the **most recent 30** prior matches per
  team (`max_matches_per_team=30`), `min_matches_per_team=6`, **all competitions included**.
  Feasibility rationale: last-30 gives 20–30 rows/team (enough to inspect venue, opponent,
  temporal and formation structure), keeps Arm B ≈ 81K input tokens — well within the 200K
  context — and preserves per-match clarity. Last-10 was too thin for venue/opponent splits;
  full-season/all-history blew the token budget without added clarity.
- Per fixture the exposure audit records PIT-available, included, omitted, and the exact
  omission reason (only `frozen_history_policy` here).

## Phase 5-12 — Full-fidelity research view (`full_fidelity_view_v1`)

Path: provider observation → canonical normalization → PIT filter → canonical match row →
serialized packet. **No hidden aggregate-only stage.**

- **Match-level rows, both teams:** every admitted match is a row with aliased opponent,
  venue HOME/AWAY, recorded formation family (or null), and all 24 metrics × FOR/AGAINST
  (55 columns). Actual canonical values — no banding, no shrink, no label substitution, no
  imputation (explicit nulls). Chronological order preserved (Phase 9).
- **DERIVED_SUMMARY blocks (Phase 6):** ALL_PRIOR/W5/W10 and HOME/AWAY split means, each
  marked `DERIVED_SUMMARY` with metric, value, sample_n, window, venue, cutoff, reliability,
  provenance = "mean of serialized match rows". They **supplement, never replace** rows.
- **Opponent-profile context (Phase 7):** deterministic RANK_BAND terciles (LOW/MID/HIGH) of
  the upcoming opponent on 8 structurally-justified axes, with candidate/bandable N and
  coverage. Frozen before outcomes; **not** chosen from V4 performance. No LLM similarity.
- **Venue (Phase 8):** actual H/A on every row **and** home/away split summaries.
- **Formation (Phase 10):** recorded family per row + coverage; availability flag
  (LOW_COVERAGE on all 10 fixtures — a genuine provider limit, ~11–33% coverage). The LLM is
  not penalized for ignoring it (Phase 23).
- **Match state (Phase 11):** not offered — HT state is 0%-coverage `UNAVAILABLE`.
- **Availability map (Phase 12):** per fixture, each dimension is AVAILABLE / LOW_COVERAGE /
  UNAVAILABLE / PIT_UNSAFE. On all 10 fixtures: venue AVAILABLE, recent_vs_long AVAILABLE,
  opponent_profile AVAILABLE, formation LOW_COVERAGE, half_time_state UNAVAILABLE, lineup
  PIT_UNSAFE, xg/red_cards AVAILABLE.

## Phase 13-14 — Data-exposure audit & cell fidelity

Per fixture: `PIT_SAFE_MATCHES_AVAILABLE`, `MATCH_ROWS_INCLUDED`, `MATCH_ROWS_OMITTED`,
`METRIC_CELL_EXPOSURE_RATE`, and every omission's reason.

| fixture | PIT avail | rows incl | omitted | cell exposure | derived sums | unexplained |
|---|---|---|---|---|---|---|
| mt_010243515 | 80 | 60 | 20 | 0.9944 | 480 | 0 |
| mt_010243537 | 154 | 60 | 94 | 0.9951 | 480 | 0 |
| mt_010243938 | 139 | 60 | 79 | 0.9965 | 480 | 0 |
| mt_010244159 | 142 | 60 | 82 | 0.9958 | 480 | 0 |
| mt_010244193 | 134 | 60 | 74 | 0.9958 | 480 | 0 |
| mt_010441320 | 128 | 60 | 68 | 0.9979 | 480 | 0 |
| mt_010441491 | 116 | 60 | 56 | 0.9889 | 480 | 0 |
| mt_010444904 | 70 | 44 | 26 | 0.9451 | 476 | 0 |
| mt_012232295 | 74 | 60 | 14 | 0.9590 | 466 | 0 |
| mt_012232411 | 54 | 54 | 0 | 0.9545 | 462 | 0 |

- **Cell-level fidelity: 27,744 serialized cells checked, 0 mismatches** — every serialized
  value equals the canonical value (no shrinkage/banding/label/imputation).
- All omissions are `frozen_history_policy(max_matches_per_team=30)`. **UNEXPLAINED_OMISSION
  = 0 for every fixture → no hard fail.** (Cell exposure < 1.0 reflects provider nulls for
  some metrics in some matches, e.g. xg 78.8% coverage — explicit nulls, never imputed.)

## Phase 16-19 — Prompt, schema, compiler, firewall

- **Prompt** (`v5a_prompt_v1`): the LLM is instructed it is a research assistant, must NOT
  predict/estimate probabilities/odds/EV/effect sizes, must ground each hypothesis in
  `evidence_refs`, must respect the availability map, and prefer simple questions when
  conditions are unsupported. System prompt structurally identical to V3.
- **Schema** = frozen **schema_v2** (content hash `7879c6ad…`, byte-identical to the V3 run).
  Closed, `additionalProperties:false`; a probability has nowhere to live.
- **Compiler** = frozen `query_plan.compile_hypothesis`; failure classes separated:
  SCHEMA_INVALID / UNSUPPORTED_CONTEXT(_SOURCE) / UNSUPPORTED_METRIC / MISSING_AXIS /
  FIREWALL_VIOLATION / VALID. Infrastructure defects are distinguished from reasoning ones.
- **Firewall** = frozen `firewall_v2` numerical-authority firewall (structural + numeric +
  prose layers); distinguishes evidence citation from effect estimation.

## Phase 21-24 — Evaluation (frozen; NOT "more/complex hypotheses")

Scored on: groundedness, compilability (VALID rate), non-degenerate conditions,
evidence-referenced rate, appropriate venue use, appropriate opponent-profile use,
appropriate recent-vs-long use, restraint on weak formation coverage, meaningful
interactions, baseline diversity, metric-family diversity, redundancy, unsupported-data
rate, fabricated-evidence rate, repeatability vs self-noise.

- **Meaningful interaction (Phase 22):** both conditions independently supported; not
  aliases/duplicates; not contradictory; neither baseline-absorbed; dimensions available;
  sample feasible; a football reason visible in the evidence.
- **Availability-aware (Phase 23):** no penalty for ignoring an UNAVAILABLE/LOW_COVERAGE/
  PIT_UNSAFE dimension (e.g. formation is LOW_COVERAGE on all 10 fixtures).
- **Information-use (Phase 24):** for each fixture, whether rich info was present and used
  appropriately (grounded), never whether the relationship is predictive.

## Phase 25 — Downstream boundary

V5A **stops at hypothesis-generation evaluation.** No predictive coefficients, candidate
features, OOS search, shrinkage tuning, threshold search, profile-definition optimization,
or prospective betting. A PASS triggers a **separate preregistered V5B** measurement stage.

## Verdict gates (frozen)

- **PASS:** Arm B shows materially higher grounded, availability-appropriate use of
  venue/opponent-profile/recent-vs-long than Arm A, at ≥ equal compilability and
  firewall-clean rate, with repeatability above the self-noise floor.
- **MIXED:** improves some dimensions but not others, or improvement within self-noise.
- **FAIL:** no material grounded-use improvement over Arm A, or degraded compilability /
  firewall cleanliness.

## Phase 27-28 — Stop rules & cost

**Stop rules (hard):** PIT leakage; target-fixture leakage; future data; hash mismatch;
unexplained metric omission; provenance failure; semantic conflict; serialization
truncation; schema-invalid rate > 0.30; > 3 consecutive transport failures; cost ceiling.

**Cost (token-calibrated from V3: 0.546 tokens/byte, not chars/4):**

| | |
|---|---|
| calls | 38 (20 base + 18 repeatability) |
| est. input tokens (total) | ~1,904,747 |
| output tokens (mean/p90/max) | 2,576 / 3,195 / 4,096 per call |
| Arm A input ≈ | 21.4K tokens/call · Arm B input ≈ 81K tokens/call |
| **expected cost** | **$7.18** |
| **p90 cost** | **$7.54** |
| **hard ceiling** | **$8.05** |

Pricing recorded at $0.003/1K in, $0.015/1K out (verify against the account rate card
before authorizing).

## Phase 29 — Pre-spend test report

`tests/research/hypothesis_oos/test_v5a_prespend.py` — **22 passed** (full hypothesis_oos
suite **36 passed**). Covers: target excluded; future excluded; injected-future excluded;
no outcome/odds fields; every cell == canonical; no unexplained omission; venue orientation;
chronology; W5/W10 reconstruction; deterministic opponent-profile; formation-availability
matches coverage; deterministic aliases; no club/competition names as values; provider
provenance intact; missing values not imputed; **Arm A == frozen V3**; schema == frozen V3;
CHAMPION unchanged; V3/V4 artifacts present & read-only; **no LLM→p_model path**; prompt
determinism; columnar encoding lossless.

## Module & artifact hashes (freeze)

| module | sha256 (16) |
|---|---|
| v5a_full_fidelity.py | `4879c28f0f208c99` |
| v5a_prompt.py | `8204d63190984c26` |
| schema_v2.py | `a9f96e19c52aa7fd` |
| validator_v2.py | `2a2dc4e68daa7697` |
| firewall_v2.py | `400e89b9ecf79e32` |
| query_plan.py | `184991835110d940` |
| vocabulary.py | `ba123f798a404911` |
| corpus_adapter.py | `5c6cb2c770b2734b` |

Artifacts: `research/hypothesis_oos/out/v5a/PREREGISTRATION.json`,
`arm_a_packets.json`, `arm_b_packets.json`, `exposure_audit.json`, byte-level exports
`BYTELEVEL_ARM_{A,B}_mt_010244159.request.txt`; full packet audit
`research/hypothesis_engine/V5A_FULL_PACKET_AUDIT.md` (631 KB, no truncation).

## Confirmations

- **CHAMPION unchanged:** `data/discovery/pilotC_stat_mixer.json` sha256
  `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` (== frozen). Read-only.
- **V2 / V3 / V4 unchanged:** V5A only reads them; Arm A is byte-identical to the frozen V3
  materialized packets (asserted by test). No frozen artifact mutated.
- **No feature promoted, no p_model/calibration/prediction touched, no LLM→p_model path.**
- **$0.00 spent. No Bedrock call made.**

---

## Human authorization gate

Exact fixtures, history rule, rows/metrics/exposure, calls, cost, gates, and stop rules are
reported above and in the machine-readable preregistration. Nothing further executes until
explicit human authorization to spend is given.

**V5A_FULL_FIDELITY_PREREGISTERED**

**V5A_RAW_DATA_EXPOSURE_VERIFIED**

**V5A_SPEND_AUTHORIZATION_REQUIRED**

STOP — do NOT call Bedrock until explicit authorization is given.
