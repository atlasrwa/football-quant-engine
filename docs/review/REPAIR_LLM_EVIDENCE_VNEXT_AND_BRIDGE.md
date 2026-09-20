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

---

# Amendment — three pre-spend audit blockers closed

`START 6a60d4248 · END 93247f7c1 · 5 commits · 153 tests passed`

The audit was right on all three. Each was reproduced in the code before being repaired.

## Blocker 1 — the bridge did not require the actual packet

`run_proposal` defaulted to `packet_hash="NO_PACKET"`, so the executed path was
`corpus → proposal → measurement`, with packet provenance and `evidence_refs` never
structurally bound and a caller-supplied hash trusted without recomputation. V1's
`N_PACKETS_BUILT=50` was reported while **no packet was built at all**.

`run_proposal(raw, *, packet, proposal_source)` now requires the packet object. There is no
NO_PACKET path. `packet_binding.verify_packet` checks lineage versions, fixture/kickoff
binding against both proposal and target, a **recomputed** `packet_hash`, information cutoff,
and that every `evidence_ref` exists in *this* packet. `PACKET_BINDING_FAILED` is its own
status. `DETERMINISTIC_REHEARSAL` may omit refs; `LLM_PROPOSAL` may not.

## Blocker 2 — provenance did not bind the measured values

A historical stat can be corrected while ids, kickoffs, season and membership stay identical;
the measurement changes and no identity moves. Added `cohort_source_hash`,
`baseline_source_hash`, `measurement_input_hash` (canonical per-row tuples including the
measured value, with `__NULL__` bound explicitly) and `target_bounded_vintage`.
`cohort_identity_hash` is re-scoped to membership/structure and now binds chronological
order. `corpus_vintage()` is **removed**, not left as a trap.

## Blocker 3 — provider provenance was inferred from storage shape

Traced, not guessed: `_to_adapter_shape` maps a **TheStatsAPI** fixture into FootyStats
*schema*, and `adapt_match` reads `yellow_cards` from `overview.yellow_cards` in the
TheStatsAPI `/stats` payload. The registry is now an explicit table (provider, source_path,
container, period support, NULL semantics) and records `CORPUS_STORAGE_SCHEMA` separately
from `provider`. Untraced metrics are not advertised as supported.

**Versions** — bumped by semantic responsibility, with the unchanged ones documented:
validator `v1→v2`, measurement `v1→v2`, shadow record `v1→v2`, registry `v1→v2`; proposal
schema, canonical IR and compiler **unchanged** because their meaning did not change.

## Exposed-50 V2 (V1 superseded, not overwritten)

| | |
|---|---|
| packets built / failures | 50 / 0 |
| proposals → valid / rejected | 300 → 200 / 100 |
| **N_REAL_PACKET_HASHES / N_NO_PACKET_RECORDS** | **300 / 0** |
| valid / invalid evidence-ref bindings | 300 / 0 |
| same-kickoff / target-outcome / future / source-hash mismatch | 0 / 0 / 0 / 0 |

Leakage probes compare the **complete** measurement payload (cohort, baseline, contrast, and
all four identity hashes). V1 compared only `cohort`.

## Season-boundary real-corpus diagnostic

The exposed-50 cohort has zero boundary fixtures, so it never exercised the repair. Scanning
the full corpus **without changing that cohort**:

| | |
|---|---|
| corpus fixtures / team-target pairs | 5,319 / 10,638 |
| season-boundary pairs | 134 (champ 40, epl 23, laliga 20, laliga2 18, ligue1 18, ligue2 15) |
| **old semantic met support on prior-season rows** | **134 of 134** |
| **new semantic abstains** | **134 of 134** |
| new semantic valid on target-season history | 0 |

Both halves of the claim established. No outcomes, no performance; derived refs only.

## Still true after the amendment

23 frozen artifacts + CHAMPION byte-identical; V1 rehearsal artifact untouched;
`LIVE_SONNET_CALLS=0`, `BEDROCK_PAID_CALLS=0`, `NEW_SONNET_SPEND_USD=0`,
`RAW_CORPUS_EXPORTED=false`, Item 5 not attempted.

**P2/P3 carried forward:** `HarnessContext.__init__` loads the corpus itself (P3,
testability); the rehearsal's proposals remain deterministic stubs, so it measures apparatus
connectivity and not hypothesis quality.

---

# Surgical dual-provider amendment

Three residual pre-spend issues, closed additively. No redesign, no broadened experiment.

## 1. Packet provenance is established BEFORE the proposal is parsed

**The defect.** `run_proposal` parsed the proposal first. A forbidden or malformed LLM
response therefore produced a shadow record with **no packet provenance at all** — a stub
target with `kickoff_unix=0` and `packet_binding_verified=false`. Invalid model output is
still a *treatment result*: if it is not attributable to the exact packet the model saw, the
rejection-reason distribution cannot be tied to any instrument.

**The repair.** Packet verification is split into two stages that cannot be reordered by
accident, because Stage A takes no proposal argument at all:

| stage | function | depends on the proposal? |
|---|---|---|
| A | `verify_packet_envelope(packet, by_fixture, raw_fixture_id=…)` | **no** |
| B | `verify_proposal_evidence_refs(packet, identity, evidence_refs=…)` | yes |

Stage A verifies type, schema/cohort lineage, recomputed hash, fixture identity, kickoff,
cutoff, and resolves the target **from the packet's own `fixture_id`**. The raw payload's
`fixture_id` is read defensively — a payload malformed in every other respect must still not
bind to a packet for another fixture — and a payload with no readable id is a *parse* failure,
not a binding failure.

**Failure precedence**, decided rather than emergent, and pinned by tests:

```
invalid packet                           -> PACKET_BINDING_FAILED
valid packet + forbidden field           -> FORBIDDEN_PREDICTION_FIELD  (packet identity kept)
valid packet + malformed proposal        -> AMBIGUOUS_PROPOSAL          (packet identity kept)
valid packet + valid proposal + bad ref  -> PACKET_BINDING_FAILED
```

One collision the taxonomy does not resolve is **decided explicitly**: a payload carrying
both a forbidden field *and* a mismatched fixture id reports `PACKET_BINDING_FAILED`, because
the packet is the instrument. The status would otherwise lose the more fundamental fault — so
the rejection reason names *both* causes and a test asserts it, rather than letting the
"the LLM tried to predict" signal disappear silently.

## 2. Packet cutoff must EQUAL the target kickoff

v2 accepted `information_cutoff_unix <= target.kickoff_unix`. That is leak-free but **not
sufficient**: deterministic measurement consumes every row with
`kickoff_unix < target.kickoff_unix`, so a packet cut at 14:00 for a 15:00 kickoff conditions
the model on a strictly smaller information set than the measurement it is compared against.
For this confirmatory experiment the two must be identical, so equality is required.

The test builds an earlier-cut packet and **re-hashes it correctly**, then asserts the
rejection reason names the *cutoff* — not `hash_mismatch`. Without that assertion a botched
re-hash would make the test pass for the wrong reason and leave the rule unverified.

Equality is also confirmed as a *property of the production builder* on real data:
`PACKET_CUTOFF_EQUALS_TARGET_KICKOFF_COUNT = 50/50`. This does not generalise arbitrary
snapshot times; a future experiment needing them versions a new protocol.

## 3. Provider provenance is genuinely dual-provider

The registry is re-keyed from `metric -> capability` to
**`(provider, canonical_metric) -> ProviderCapability`**. Under the old shape a metric had
one capability and the second provider was *unrepresentable*.

**`yellow_cards` is the proof the pair key is necessary.** FootyStats genuinely exposes
`team_a_yellow_cards` (`footystats/normalizer.py:184`). TheStatsAPI exposes
`overview.yellow_cards`, which `championship_adapter` then parks in a storage field *also*
called `team_a_yellow_cards`. Identical spelling, two providers. **Storage schema ≠ provider.**

| | FootyStats | TheStatsAPI |
|---|---|---|
| yellow_cards | `team_a_yellow_cards/team_b_yellow_cards` | `overview.yellow_cards` |
| corners | `team_a_corners/team_b_corners` | `overview.corner_kicks` |
| xG | `team_a_xg/team_b_xg` | `overview.expected_goals` |
| npxG | **absent** — traced, not assumed | `np_expected_goals.all.{home\|away}` |

Capabilities carry a `status`; only `MEASURABLE` is measurable and everything else fails
closed. FootyStats entries are traced **only** from the real normalizer — nothing is
populated from a documentation list. `total_shots` is declared `UNVALIDATED_EQUIVALENCE`
rather than silently mapped, because FootyStats' shot count has never been measured against
TheStatsAPI's. `semantic_equivalence_validated` is `False` on every entry.

**No implicit anything.** `resolve_measurement_provider` resolves only the two single-provider
policies and **raises** on `PREFERRED_PROVIDER_WITH_FALLBACK` and `VALIDATED_BLEND` — the
cross-provider code path does not exist, which is how `IMPLICIT_PROVIDER_FALLBACK=false` and
`IMPLICIT_PROVIDER_BLEND=false` are *earned* rather than asserted. Cross-provider resolution
belongs to `src/research/reconciliation/reconciler.py`; the policy enum is imported from
`src/research/reconciliation/policy.py` rather than re-declared, so no competing framework is
created. `BridgeContext` additionally refuses to be constructed with a policy that resolves to
a provider the corpus did not come from, so FootyStats provenance cannot be fabricated over
TheStatsAPI-derived rows.

**The current rehearsal is NOT a blend.** Its policy is frozen to `THESTATSAPI_ONLY`, which
is what the traced load path actually is:
`load_corpus -> multisrc_corpus.load_season -> championship_adapter.adapt_match(stats_json)`.

## 4. npxG follows the existing evidence, rather than being re-pathed

The old registry advertised npxG as supported at a **fictitious** path,
`np_expected_goals.np_expected_goals`. `championship_adapter._cell` special-cases the metric:
the node is the *root* key `np_expected_goals`, then `[period][side]`.

Correcting the path would not have made npxG valid. `V5A1_PROVIDER_SEMANTICS_AUDIT.md §2`
already measured the semantics: npxG exceeded **total** xG by >0.05 in **511 of 3,242** raw
pairs (15.8%, worst −0.99), with a smooth non-penalty-shaped error distribution;
classified `PROVIDER_SOURCE_INCONSISTENCY`; unrepairable because the corpus has no penalty
field. So `("thestatsapi","npxg")` is `EXCLUDED_PROVIDER_SEMANTICS` — the entry is **retained
with its true source path** for audit, because excluded is not the same as absent.
`("footystats","npxg")` does not exist and is **not** inferred from FootyStats' xG.

## 5. Source hashes bind provider identity (3H)

`source_hash` now takes the resolved capability as a **parameter** and binds provider,
capability id and the provider's own source field into every row *and* the payload header.
Identical rows with identical values but a different provider produce a different hash — a
provider substitution can no longer be invisible. `capability_identity(None)` raises rather
than defaulting: a measurement whose provenance cannot be named must not produce a provenance
hash, because a placeholder would collide across providers.

## Versions — semantic responsibility, not cosmetics

| version | change | why |
|---|---|---|
| `hypothesis_validator_v2 → v3` | **bumped** | verification order split; cutoff equality |
| `deterministic_measurement_v2 → v3` | **bumped** | provider identity bound into source hashes |
| `shadow_research_record_v2 → v3` | **bumped** | provider fields; parse-rejected records now carry verified packet identity |
| `provider_capability_registry_v2 → v3` | **bumped** | re-keyed to `(provider, metric)` — a change of *identity* |
| `hypothesis_proposal_v1` | unchanged | proposal *shape* identical; parse order is bridge execution, not schema |
| `canonical_hypothesis_ir_v1` | unchanged | IR semantics and id derivation untouched |
| `hypothesis_compiler_v1` | unchanged | canonicalization logic untouched |

`cohort_identity_hash` and the target-bounded vintage embed `MEASUREMENT_VERSION` and
therefore move with it. That is intended: a v2 hash asserted a weaker provenance claim than a
v3 hash, and the two must not compare equal.

## Exposed-50 V3 (V1 and V2 superseded, neither overwritten)

V2's templates were all well-formed, so the amendment's headline claim would never have been
exercised on real data. V3 adds a forbidden-field template, an unknown-field template and an
npxG template.

| | |
|---|---|
| fixtures / packets built / failures | 50 / 50 / 0 |
| proposals → valid / rejected | 450 → 200 / 250 |
| **parse rejections retaining packet identity** | **100** |
| **N_REAL_PACKET_HASHES / N_NO_PACKET_RECORDS** | **450 / 0** |
| packet-bound rejections | 0 |
| valid / invalid evidence-ref bindings | 350 / 0 |
| cutoff == kickoff | **50 / 50** |
| measurement provider counts | `{thestatsapi: 450}` |
| provider policy | `THESTATSAPI_ONLY` |
| **N_NPXG_ACCEPTED** | **0** |
| same-kickoff / target-outcome / future / source-hash mismatch | 0 / 0 / 0 / 0 |

Rejections: `UNSUPPORTED_PROVIDER_SEMANTICS` 100 (npxG 50 + half-split `big_chances` 50),
`UNSUPPORTED_METRIC` 50, `FORBIDDEN_PREDICTION_FIELD` 50, `AMBIGUOUS_PROPOSAL` 50. The 100
parse rejections each carry a real, recomputed `packet_hash` — under the previous ordering all
100 would have carried none.

Leakage probes compare the complete measurement payload, now including
`measurement_provider` and `provider_capability_id`.

## Still true after this amendment

V1/V2/season-boundary artifacts and CHAMPION byte-identical
(`0b8f5ff3…c00c9`); no production path imports the bridge; `LIVE_SONNET_CALLS=0`,
`BEDROCK_PAID_CALLS=0`, `NEW_SONNET_SPEND_USD=0`, Item 5 not attempted.

**P2/P3 carried forward:** proposals remain deterministic stubs, so the rehearsal measures
apparatus connectivity, not hypothesis quality (unchanged from V2). FootyStats capabilities
are declared but not *exercised* — no FootyStats-backed corpus reaches this bridge yet, so
their source fields are traced rather than round-tripped. `xg` is declared for both providers
but sits outside the IR vocabulary, so it is not measurable here.
