# LLM evidence vNext + hypothesis→validation→shadow bridge

Base `055868235` (PR #22 tip). Three parts: repair and version the LLM evidence season
semantics (A–C, G), build the research bridge (D), and rehearse the apparatus at zero spend
(H). Item 5 was **not** attempted.

`LIVE_SONNET_CALLS=0 · BEDROCK_PAID_CALLS=0 · NEW_SONNET_SPEND_USD=0 · RAW_CORPUS_EXPORTED=false`

---

## A. Target-season semantics — call-site audit

`cohorts.HistoryIndex.current_season(team, before)` returns the season the team **last played
in**. Used as the current-season filter, a fixture early in a new season-instance received
prior-season history as current-season state, and cold-start floors were met by stale data.

| Call site | Means | Action |
|---|---|---|
| `evidence.py:108` `_team_block` season filter | **B** target's season | → `target_season` |
| `evidence.py:183-184` style clusters for A/B | **B** | → `target_season` |
| `evidence_v2.py:163-164` packet build season | **B** | → `target_season` |
| `phaseb_harness.py:131-132` eligibility + formation projection | **B** | → `target_season` |
| `evidence_v2.py:68` `_resolution_status` | **B** (inherits its caller's key) | → via caller |
| *(no production caller)* | **A** "last played" | `current_season` kept, unchanged |
| `test_formation_policy.py:142,153` | **A** — exercises `current_season` itself | left as-is |
| `test_matchup_leakage.py` (6 sites) | **A** — exercises `current_season` itself | left as-is |

There is **no A-class production caller**. `current_season` is retained anyway: it answers a
legitimate different question, and its docstring now says why it is not the right input here.

`target_season(target)` derives from `season_of(target)` alone, so **one key filters both
sides** (A3) and neither team can drift into a different season. Zero target-season history
means abstain, never a prior-season fallback.

**Verified at four levels** (A4), because an index repair says nothing about what reaches a
packet: `HistoryIndex` → evidence/cohort builder → phaseb candidates → built packet. Positive
control included: genuine S2 history restores eligibility and evidence, and `sample_n` never
exceeds the real S2 history — so the test cannot pass because the fixture was excluded for an
unrelated reason.

## B. Simultaneous kickoff in the LLM evidence path — `VERIFIED_ALREADY_CORRECT`

Not assumed from PR #22. Every temporal comparison in `llm_matchup/` is a strict `<`, and
there is no incremental accumulator of the kind repaired there. Proven at **packet level**: a
partner match at exactly the target kickoff versus strictly later yields an identical
`packet_hash` — stronger than field-by-field, and it would catch a leak arriving by a path no
grep found.

**No production code was changed for Part B.** The regression test is kept.

## C. Evidence lineage versioning

The frozen 4.5/4.6 arms build packets through the very builder corrected here
(`phaseb_harness` → `EvidencePacketBuilderV2` → `evidence.py`), so this is a different
instrument and gets a new lineage:

```
OLD_LINEAGE  cohort_policy_v1 / fixture_evidence_packet_v2   HISTORICAL_FROZEN
NEW_LINEAGE  cohort_policy_v2 / fixture_evidence_packet_v4   CORRECTED_SUCCESSOR
```

`fixture_evidence_packet_v4` skips v3 because `hardening/versions_v2` already uses that name.
`cohort_policy_v2` propagates through `versions_v2 → versions_v3 → versions_v3_sonnet46` **by
design** — those arms consume the corrected builder, so the signal is correct, not collateral.

Two consequences were **predicted, then measured**:

| | |
|---|---|
| `check_compatible` vs the frozen 4.5 manifest | `False`, on exactly one field: `version_stamp.cohort_policy_version` `cohort_policy_v1 → cohort_policy_v2` |
| `adapter_v4._cache_key` for an identical packet hash | `f5e7cf68… → 6a62ea00…`, so no corrected packet can read old-lineage cache |

A resume now aborts `ABORT_RESUME_GENERATION_MISMATCH`, and `freeze_v3_sonnet46.verify_freeze`
gains a third drift cause beyond the two catalogued in PR #21. **That is the apparatus built
over PRs #20–#22 correctly detecting a real instrument change.**

## D. The research bridge

`HypothesisProposal → canonical IR → validation → deterministic measurement → ShadowResearchRecord`

**Numerical firewall in ONE place** (`firewall.py`): inbound allow-list over proposal fields,
outbound deny-list asserted on every record. Split across the canonicalizer and the record
builder, a third path could add a field and both checks would still pass. Field names are
normalised to tokens **and** to a separator-stripped whole — `ev` is one token, while
`expected_value` is only recognisable rejoined. A test caught that gap; it is closed. Nested
fields are found recursively.

**Canonicalization** is a closed vocabulary, no fuzzy fallback; identical proposals give
identical ids, field order is immaterial, and `similar_opponent_intent` is **refused** as a
measurement axis rather than silently dropped.

**Provider validation** is grounded in `cohorts.ALL_METRICS` — the only place the corpus's own
field mapping is declared. Nothing is imputed; half-split periods are refused for metrics with
no half mapping; FootyStats and TheStatsAPI are not assumed equivalent.

**PIT validation** re-checks the rows the measurement will consume rather than trusting the
selector. **Support validation** reuses `cohorts.MIN_HISTORY` — no second, weaker threshold.

**Measurement** is descriptive only. NULL means *not recorded* and is dropped, never coerced
to zero. No probability, edge, EV or stake is produced.

**Status taxonomy**: the mandated nine plus `FORBIDDEN_PREDICTION_FIELD`. Justified — the
proposal was well-formed and was refused for carrying a prediction; collapsing it into
`AMBIGUOUS_PROPOSAL` would hide the only signal that the LLM is being used as a predictor.
Rejections are always emitted as records, or the rejection distribution is unmeasurable.

## G. Immutability

23 frozen artifacts + CHAMPION SHA256-recorded before any edit; **all byte-identical after**.
Nothing regenerated, rebaselined or back-stamped. The synthetic golden-vector builders in
`golden.py` / `counter_golden.py` hard-code the old literals and are deliberately left pinned
to the historical lineage.

## H. Exposed-50 apparatus rehearsal — `DEVELOPMENT_REAL_CORPUS_APPARATUS_REHEARSAL`

All 50 pilot fixtures from `V8B1_PILOT50_SELECTION_FREEZE.json` resolve in the corpus.
Deterministic stub proposals — **not** model output — through the exact production bridge.

| | |
|---|---|
| N_FIXTURES / N_PACKETS_BUILT / failures | 50 / 50 / 0 |
| N_PROPOSALS | 300 |
| N_VALID_MEASURABLE / N_REJECTED | 200 / 100 |
| rejections | `UNSUPPORTED_METRIC` 50, `UNSUPPORTED_PROVIDER_SEMANTICS` 50 |
| N_MEASUREMENTS_OK / FAILED | 200 / 0 |
| N_SHADOW_RECORDS | 300 |
| SAME_KICKOFF_LEAKAGE_COUNT | **0** |
| TARGET_OUTCOME_DEPENDENCE_COUNT | **0** |
| FUTURE_DATA_DEPENDENCE_COUNT | **0** |
| OLD_CACHE_REUSE_COUNT | **0** (expected 0) |
| CHAMPION_UNCHANGED | true |

The leakage counters are **measured, not asserted**: each is a re-run of the accept-path
proposal against a perturbed corpus (simultaneous partner / future match / mutated target
outcome) over a bounded deterministic 10-fixture probe.

No directional performance result is reported. The artifact contains derived diagnostics
only — no corpus rows.

## Limitations — stated, not hidden

* **`N_SEASON_BOUNDARY_FIXTURES = 0`**: the exposed-50 cohort contains no fixture whose team
  lacks target-season history, so this rehearsal **does not exercise the Part A repair**.
  That repair's evidence is the synthetic four-level suite, not this run.
* **The rehearsal's proposals are stubs.** It measures whether the apparatus connects, not
  whether an LLM would produce useful hypotheses.
* **Item 5 not attempted.** Paid execution requires explicit authorization after an
  independent pre-spend audit.
* **`HarnessContext.__init__` loads the corpus and coverage index itself**, so it cannot be
  constructed with synthetic data without bypassing `__init__`. Logged **P3** (testability),
  not a blocker.
* Model identity, spend enforcement, lock/preflight, output-root and freeze-coverage findings
  are untouched and remain open.
