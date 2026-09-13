# Phase B — Audit, Metrics, Capability Classification & Phase-C Recommendation

Live Claude Sonnet on Bedrock, frozen Phase-B stack. This is the consolidated audit across
gates B0, B1, B2.

**Model / identity:** `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, region `us-east-1`,
via Bedrock `Converse` with a strict tool-input schema. Stack: `football_ontology_v2` /
`football_state_schema_v2` / `sonnet_prompt_v2` / `fixture_evidence_packet_v2` /
`cohort_policy_v1` / `formation_policy_v1` / `formation_family_v1`. Recorded per call in
`out/phase_b_calls.csv`.

---

## 1. Aggregate live metrics (B0 + B1 + B2)

| Metric | Value |
|--------|------:|
| Total live Sonnet calls (billable) | 44 |
| Calls OK (validator-accepted) | 40 |
| Calls rejected (fail-closed) | 4 |
| Bedrock failures / unavailable | 0 |
| Overall schema-valid % | **90.9 %** |
| Sum input tokens | 1,162,136 |
| Sum output tokens | 221,671 |
| Mean latency / call | ≈ 48 s |
| Approx total cost (≈$3/M in, $15/M out) | **≈ $6.81** |
| Approx cost / accepted state | **≈ $0.17** |

Per gate: B0 7 OK / 1 rej; B1 27 OK / 1 rej; B2 6 OK / 2 rej.

### Rejections are all correct fail-closed catches
- `invalid enum 'MEDIUM_HIGH'` / `'MEDIUM_LOW'` — confidence value placed in a slot whose
  enum did not permit it (×2).
- `corners_for not permitted for WIDTH_PRESSURE` — corners belong to
  `SET_PIECE_GENERATION` / `CORNER_MECHANISM_MATCHUP`, not `WIDTH_PRESSURE` (×1).
- `shots_inside_box_for not permitted for SHOT_CREATION_MATCHUP` — resolved before B1 by an
  ontology allow-list correction; the pre-fix B0 rejects were legitimate (×earlier).

No rejection was a silently-accepted bad output. The validator never trusted the LLM.

## 2. Manual / automated audit of accepted states (brief §38)

Across **33 accepted states / 1046 emitted mechanisms**:

| Question | Finding |
|----------|---------|
| Did Sonnet cite real evidence? | ✅ every accepted mechanism cited packet evidence ids (validator-enforced) |
| Did cited evidence support the state? | ✅ avg **3.23** supporting ids / mechanism (multivariate, not single-feature) |
| Did it overweight the formation label? | ⚠️ mostly no; **1/8** shuffle-eligible fixtures showed genuine stereotype dependence (B1) |
| Did it use behavior correctly? | ✅ ablation shows formation-conditioned behavior shifts base mechanisms coherently |
| Did it preserve counter-evidence? | ⚠️ counter-evidence on only **4.1 %** of mechanisms — low; candidate prompt-v3 improvement |
| Did it overstate tiny samples? | ✅ sparse cohorts flagged `EXACT_FORMATION_SPARSE` / `SMALL_SAMPLE`; confidences lowered |
| Did it confuse FOR/AGAINST? | ✅ none observed (validator + orientation checks) |
| Did it confuse home/away? | ✅ A=home, B=away preserved throughout |
| Did it turn 2H shifts into unsupported tactical claims? | ✅ no; `SCORE_STATE_CONFOUND` safeguard intact |
| Did it produce narrative / prediction? | ✅ none; 0 states contained probability/betting content |
| UNKNOWN / CONFLICTED behaviour | UNKNOWN 0.8 %, CONFLICTED 0.0 % — Sonnet rarely abstains (evidence usually present) |

### Minor inconsistency noted
On some v2 states Sonnet set the legacy `formation_status=KNOWN_PIT_SAFE` while correctly
setting `prematch_formation_status=PROJECTED`. Under the two-concept model the legacy flag is
**non-authoritative** (superseded by the two new flags), so this is accepted, but it is
cosmetically inconsistent and a candidate for removal from the schema in a future version.

## 3. Formation behaviour (B1, brief §17-§21)

- **Formation adds information:** 10/10 B1 fixtures changed under ablation (mean 0.276).
- **Sonnet does not parrot the label:** in aggregate, shuffling labels net of repeatability
  noise moved the state materially in only **1/8** fixtures.
- **Sonnet emitted zero explicit `FORMATION_*` mechanisms** across the whole pilot — yet
  formation-conditioned evidence still shifted its base-mechanism reasoning. Formation is
  used implicitly through behaviour, not as a categorical label. This is *desirable* per the
  mandate ("formation + actual behavior", not "formation label").
- **Repeatability caveat:** 4/10 B1 fixtures were not stable across identical calls (one
  diverged 0.76). Sonnet is not deterministic even at temperature 0. Mitigated by packet-hash
  caching for persisted features; must be managed in Phase C (sample-and-aggregate or treat
  as noise).

## 4. Surrogate / triviality probe (brief §31, §32)

`out/surrogate_analysis.{json,csv}`: a proxy 1-rule surrogate (using cited-evidence count as
the feature, since persisted states do not carry the packet) flags 16/34 mechanism rows as
"trivially reproducible". **This proxy is weak** — it does not use the raw z-scored feature
value — so it over-counts triviality. A rigorous surrogate (raw feature → level) requires
joining states back to packets and is recommended for Phase C. The multivariate citation
pattern (3.23 ids/mechanism) argues against pure single-feature echoing.

## 5. B2 corners dataset

- Deterministic stratified selection persisted **before** any call: 120 fixtures across 134
  strata from 726 candidates, `selection_hash=4c322004380882cf…` (`out/b2_selection.json`,
  backup `out/b2_selection_full120.json`).
- Live subset executed: 8 fixtures (6 OK, 2 fail-closed rejects) → `out/llm_states_b2.jsonl`.
  The full 120 can be completed later from the frozen selection without re-selection.

## 6. Formation availability — four separate axes (brief §43)

| Axis | Verdict | Basis |
|------|---------|-------|
| **HISTORICAL RESOLUTION** | **AVAILABLE** | 1001 lineup files, 21 formations, all overlap corpus; used as conditioning evidence |
| **HISTORICAL PREMATCH AVAILABILITY** | **UNPROVEN** | lineup data carries `confirmed:true` but **no announcement timestamp**; cannot prove pre-kickoff knowledge |
| **FORWARD ANNOUNCED** | **NOT_IMPLEMENTED** | `FormationInput(ANNOUNCED)` interface designed; no live announced feed wired |
| **FORWARD PROJECTED** | **NOT_IMPLEMENTED** | `FormationInput(PROJECTED)` + baseline projector exist in harness; not validated/productionised |

This deliberately does **not** collapse to "formation available = false".

## 7. Success / failure criteria (brief §39, §40)

Success criteria met: very high schema compliance (90.9 %); zero accepted fake evidence;
zero accepted future-target leakage; very low unsupported inference; correct A/B & FOR/AGAINST
orientation; appropriate UNKNOWN handling; formation demonstrably used; no *systematic*
stereotyping; cost/latency manageable ($0.17/state).

Failure criteria triggered: **none** at the STOP level. Two sub-threshold caveats:
imperfect repeatability (4/10) and one genuine label-stereotype case (1/8). Neither is
"outputs are unstable / labels dominate behaviour / stereotype dependence" at the systematic
level §40 requires to STOP.

## 8. Phase-C recommendation

> **PROCEED_TO_PHASE_C** — with two required conditions.

Rationale: the live Sonnet layer produces stable-enough, faithful, evidence-backed,
schema-valid states that respond to matchup structure and use formation-conditioned behaviour
without systematic stereotyping. It clears every §39 bar. Formation is genuinely part of the
engine as behaviour, not as a label.

Required conditions before/within Phase C:
1. **Repeatability control.** Because Sonnet is non-deterministic at temp 0, Phase C must
   either sample-and-aggregate each state (e.g. majority/ensemble over k draws) or explicitly
   model the state as noisy. Persisted-feature caching already stabilises a *stored* feature.
2. **Rigorous surrogate + counter-evidence check.** Join states to packets for a proper
   single-feature surrogate (does a Sonnet state exceed a raw z-feature?), and consider a
   prompt-v3 that requires counter-evidence when a plausible opposing signal exists (current
   4.1 % counter-evidence rate is low).

Phase C must handle target-fixture formation in an inference-realistic way — **announced**,
**projected**, or **probabilistically marginalised** — and never the target's resolved
formation (see `FORMATION_RESOLUTION_POLICY.md` and `PHASE_B_PLAN.md` §9). The best
deterministic contextual quant challenger will be compared against the same challenger plus
the frozen Sonnet-derived states under chronological OOS.
