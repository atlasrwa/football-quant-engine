# V3 Evidence Forensic Audit — What Sonnet 4.6 Actually Saw

**Type:** ZERO-SPEND read-only forensic audit. No Bedrock/LLM call, no network read, no
modification of V2/V3/V4/CHAMPION/`p_model`/calibration/predictions/features/gates/
thresholds. V3's frozen `FAIL` verdict is **unchanged**; this audit describes *what V3
tested*, it does not rescore it.

**Question audited:** *Did the V3 evidence package expose enough of the available
historical football information for Sonnet to reason intelligently about team conditions,
venue behavior, formations, opponent types, attacking/defensive profiles, and
interactions?*

**Answer (supported quantitatively below): No, for the conditional and temporal
dimensions.** The provider corpora contained the raw history needed to derive venue,
window, and opponent-profile structure for 10 of 11 fixtures, but the V3 evidence builder
collapsed all of it into unconditional lifetime scalar means. Sonnet was asked to reason
about conditional football while being shown only unconditional averages.

**Primary artifacts read (hashes verified):**
- `out/MATERIALIZED_PACKETS_sonnet46_v3.json` — the exact prompt-visible packets.
- `out/hypothesis_v3_sonnet46/hypothesis_states.jsonl` — frozen requests/responses;
  `packet_hash` and `serialized_request_sha256` present and matched per fixture.
- `out/v3_hypothesis_measurement/frozen_hypothesis_corpus.json` — 112 accepted reference
  hypotheses.
- Upstream PIT-safe corpus via `corpus_adapter.load_index()` (the same index V3 measurement
  used).

Audit script (read-only): `research/hypothesis_engine/_audit_v3_evidence.py` →
`out/v3_evidence_audit/capability_matrix.json`.

---

## 1. Exactly what Sonnet saw (reconstructed, not summarized)

Every reference packet has the identical structure. One evidence item, verbatim:

```json
{
 "id": "HOME_ATK_corners_406027",
 "metric": "corners_for",
 "value": 4.8792,
 "sample_n": 40,
 "reliability": "HIGH",
 "shrinkage_level": "SHRUNK",
 "temporal_status": "PIT_SAFE",
 "source_field": "('rich', 'corner_kicks')",
 "source_provider": "thestatsapi",
 "cutoff_unix": 1756645200,
 "max_source_time_unix": 1756040400,
 "scope": {"metric": "corners", "side": "FOR", "subject": "HOME",
           "venue": "ALL", "window": "ALL_PRIOR"}
}
```

**Structural facts, verified across all 11 clean fixtures (see capability_matrix.json):**

| property | value |
|---|---|
| evidence items per fixture | 76 (74 for mt_012232411) |
| distinct metrics | 19, each as FOR/AGAINST × HOME/AWAY subject = 76 scalars |
| `scope.window` values | **`ALL_PRIOR` only** (100%) |
| `scope.venue` values | **`ALL` only** (100%) |
| conditioning in any scope | **none** — no venue split, no window split, no formation split, no opponent-profile split |
| exposes a distribution (sd/p25/p75)? | **No** |
| exposes per-match rows / chronology? | **No** |
| shrinkage | every item `SHRUNK` scalar mean |
| identities | aliased: `HOME_TEAM`/`AWAY_TEAM`, `COMPETITION` (no club/league names) |

Separated extraction (A–L):
- **A. fixture metadata:** `{home: HOME_TEAM, away: AWAY_TEAM, competition: COMPETITION}`,
  `information_cutoff_unix`. Identity-aliased.
- **B. evidence items:** 76 unconditional shrunk scalar means (above).
- **C. capability/availability:** `capability_manifest` with `available_metrics` (19),
  `available_dimensions` (5), `unsupported_context` (weather, injuries, minute-level
  events, player ratings, expected formation), formation `coverage`.
- **D. profile bands:** **none in the evidence.** The vocabulary *offers* profile bands as
  something to ask about, but no banded opponent-profile evidence item was provided.
- **E. formation:** only `formation_distribution`, a **count histogram** (e.g.
  `{HOME_TEAM: {BACK_FOUR: 3}, AWAY_TEAM: {BACK_FOUR: 3}}`). No formation-conditioned metric.
- **F. venue:** only the label `venue=ALL` on every item. **No venue-conditioned behavior.**
- **G. competition:** aliased tag `COMPETITION`; league-environment values not exposed as
  evidence items (offered as a comparison to request, not shown).
- **H. historical-window:** `ALL_PRIOR` only. No W5/W10/season/decay/recent-vs-long.
- **I. opponent-profile:** **none.** No similarity axis, no response-vs-similar-opponents.
- **J. raw numerical metrics:** present but only as one aggregated mean per metric-side.
- **K. summaries/aggregations:** this is *all* the evidence is — shrunk lifetime means.
- **L. other:** `vocabulary` (what may be asked), `notes`, `data_quality`
  (`n_evidence`, `n_pit_safe`, `n_unavailable`).

Hash verification: each fixture's packet `packet_hash` matches the frozen
`hypothesis_states` record; `serialized_request_sha256` is present (e.g.
`ae163ae4…` for mt_010243515). No packet was altered by this audit.

## 2. Upstream data lineage (per evidence field)

Traced for the corners example, representative of all 76:

```
TheStatsAPI /stats payload  (rich block "corner_kicks", home/away pair, NULL!=ZERO)
  → championship_adapter.adapt_match  (provider normalization)
  → canonical metric "corners" FOR/AGAINST  (corpus_adapter.team_value)
  → historical aggregation: mean over ALL prior matches strictly < cutoff  (shrunk n/(n+k))
  → evidence-builder item {metric, value, sample_n, reliability, shrinkage_level, scope}
  → serialized Sonnet input (scope.venue=ALL, scope.window=ALL_PRIOR)
```

Provenance is carried on every item (`source_provider`, `source_field`), so lineage is
recorded, not inferred from names. Provider split for the 19 exposed metrics:
- **TheStatsAPI (rich):** corners, accurate_crosses, total_shots, shots_on/off_target,
  blocked_shots, shots_inside_box, touches_in_box, final_third_entries, possession,
  tackles, clearances, interceptions, big_chances, saves, throw_ins.
- **base (adapter):** goals, fouls, yellow_cards.
- **Derived canonical:** the shrunk mean and reliability band (transformation, not a raw
  provider value).
- **Profile classifications:** *none produced* at the evidence stage.
- **Unavailable (declared):** weather, injuries, minute-level events, player ratings,
  pre-match expected formation.

The aggregation step is where all conditional and temporal structure is destroyed: the
transformation is `list[prior matches] → single shrunk scalar`, discarding opponent, venue,
date, and formation of each contributing match.

## 3. Upstream capability inventory (independent of what V3 exposed)

Measured directly from the PIT-safe index at each fixture cutoff.

**Match context available PIT-safe:** kickoff, competition, home/away, final historical
score, recorded formation (low coverage — §7), referee (FootyStats corpus). Starting
lineup / substitutions / pre-match expected formation: **not** PIT-provably available (the
manifest's `unsupported_context` is honest here). HT score / minute-level: only GOAL
minutes timestamped → half-state is **PIT_UNSAFE** for general metric splitting.

**Attacking/defensive metrics available PIT-safe (both teams, all fixtures except the
thin-history one):** all 19 exposed metrics plus their FOR/AGAINST orientation, drawn from
prior completed matches. Coverage is high (the exposed scalars themselves prove
availability; sample_n 27–104 for 10/11 fixtures).

## 4. What conditional analysis was DERIVABLE before kickoff

Measured, per fixture, from raw prior matches (not asserted):

**Venue splits — DERIVABLE for 10/11 fixtures, for ALL 19 metrics.**
For every clean fixture except `mt_013233190`, **all 19 exposed metrics had ≥4 home AND ≥4
away prior observations for both teams** (`n_metrics_venue_splittable = 19/19`). Example
(mt_010244159, Fulham home): corners home_n=35 / away_n=36; SoT 35/36; crosses 35/36;
possession 35/36 — every split cleanly measurable. Sonnet saw `venue=ALL` for all of them.

**Recent-vs-long — DERIVABLE for 10/11 fixtures.** Every team except the thin-history pair
had ≥10 prior matches (n_prior 27–104), so W5, W10, season, and recent-minus-long were all
constructible. V3 exposed only `ALL_PRIOR`. **This means the uniform "ALL_PRIOR" was an
evidence-builder choice, not an upstream limitation** — decisively so.

**Opponent-profile — DERIVABLE.** V4 already demonstrated opponent-profile cohorts are
highly measurable downstream from this same corpus (opponent_profile family measurable rate
0.981, median conditional N 14). None of that response-vs-similar-opponents information was
placed in the evidence packet.

**Interactions (venue×profile, venue×formation, crossing-profile×corner-generation, etc.)
— DERIVABLE in principle** wherever the constituent cohorts are populated (venue and
profile both are). Not claimed predictive; only that the raw data could support asking/
measuring them. Formation-based interactions are gated by formation coverage (§7).

**Formation splits — mostly NOT derivable (see §7)** due to genuine coverage, not builder
choice.

## 5. Information-loss classification (11 fixtures × 10 capabilities = 110 cells)

| class | count | which capabilities |
|---|---|---|
| `RAW_AVAILABLE_AND_EXPOSED` | 11 | unconditional scalar means (the one thing shown) |
| `RAW_AVAILABLE_BUT_AGGREGATED` | 22 | per-match temporal structure; distribution/heterogeneity |
| `RAW_AVAILABLE_BUT_NOT_EXPOSED` | 12 | venue-conditioned behavior (10 fixtures) + formation where contrastive (2) |
| `DERIVABLE_BUT_NOT_CONSTRUCTED` | 32 | recent-vs-long; opponent-profile response; interactions; formation where coverage moderate |
| `BLOCKED_BY_PROVIDER_COVERAGE` | 11 | formation on sparse fixtures; venue/window on the thin-history fixture |
| `PIT_UNSAFE` | 11 | half-time-state conditional metrics (minute-level absent) |
| `UNSUPPORTED_BY_PROVIDER` | 0* | (weather/injuries/lineups declared separately in manifest, not among the 10 audited conditional capabilities) |

*Only 1 of the 10 audited conditional capabilities per fixture is genuinely
provider-blocked in the general case (formation); half-state is genuinely PIT-unsafe.
**Roughly 60% of audited conditional capability cells were available or derivable upstream
but not exposed / not constructed** (`22 + 12 + 32 = 66` of 110), versus `11 + 11 = 22`
genuine provider/PIT limitations and 11 exposed.

## 6. Raw history vs V3 representation (representative fixture)

**mt_010244159 — Fulham (home) vs Aston Villa (away), EPL.**

*Raw historical behavior available before kickoff (Fulham, 71 prior matches):*
- corners FOR: 35 home matches + 36 away matches, each with opponent, formation, corners,
  corners conceded, shots, SoT, crosses, possession, cards recorded per match.
- venue split fully populated (home_n=35, away_n=36) for all 19 metrics.
- ≥10 recent matches available → W5/W10/season all constructible.

*What Sonnet saw for Fulham corners:* one item —
`corners_for = <shrunk mean>, sample_n=71-ish, venue=ALL, window=ALL_PRIOR`. Plus one
`corners_against` scalar. No home/away split, no last-10, no per-opponent row, no
distribution.

| dimension | raw availability | in V3 evidence |
|---|---|---|
| opponent per match | yes | **omitted** |
| home/away split | yes (35/36) | **collapsed to ALL** |
| formation per match | ~17% coverage | **collapsed to a count histogram** |
| corners / conceded | yes, per match | **averaged to 1 scalar each** |
| shots / SoT / blocked / crosses / possession | yes, per match | **averaged, 1 scalar each** |
| distribution / SD | computable | **omitted** |
| recent vs long (W5/W10) | yes | **omitted (ALL_PRIOR only)** |
| opponent-profile response | derivable | **omitted** |

The same pattern holds for every clean fixture (capability_matrix.json).

## 7. Formation audit (why only 3/12 were contrastive)

Per-fixture recorded-formation coverage from raw priors:

| fixture | home prior / cov / contrastive | away prior / cov / contrastive | dominant cause |
|---|---|---|---|
| mt_010243515 | 40 / 0.175 / no | 40 / 0.175 / no | (A) coverage too low |
| mt_010243537 | 104 / 0.106 / no | 50 / 0.160 / no | (A) coverage |
| mt_010243938 | 69 / 0.174 / no | 70 / 0.129 / no | (A) coverage |
| mt_010244159 | 71 / 0.183 / no | 71 / 0.169 / no | (A) coverage |
| **mt_010244193** | 67 / 0.149 / **yes** | 67 / 0.164 / no | contrastive on home side |
| **mt_010441320** | 64 / 0.219 / **yes** | 64 / 0.156 / no | contrastive on home side |
| mt_010441491 | 37 / 0.324 / no | 79 / 0.165 / no | (A/C) coverage/N |
| mt_010444904 | 56 / 0.214 / no | 14 / 0.286 / no | (A/C) coverage/N |
| mt_012232295 | 37 / 0.000 / no | 37 / 0.027 / no | (A) provider coverage ≈ 0 |
| mt_012232411 | 27 / 0.000 / no | 27 / 0.074 / no | (A) provider coverage ≈ 0 |
| mt_013233190 | 4 / 0.250 / no | 4 / 0.250 / no | (C) N too small (thin history) |

Separation of causes:
- **(A) provider formation coverage genuinely insufficient** — dominant. Coverage is
  0.00–0.32; a formation-conditioned cohort is overwhelmingly missingness. This is a real
  provider limitation, not an evidence-builder failure.
- **(D) team overwhelmingly one formation** — a contributor where a family reaches ≥4 but no
  second family does.
- **(C) N too small** — the thin-history fixture.
- **(B) enough raw formation existed but builder failed to expose it** — **not** the cause:
  coverage is genuinely low.
- **(E) normalization/identity loss** — not evidenced; the back-line-count family mapping is
  deterministic.

**Formation is the one dimension where the bottleneck is genuinely the provider, not the
evidence builder.** The audit's 3/12-contrastive figure is corroborated: only mt_010244193
and mt_010441320 reach a contrastive home-side split, and formation-conditioned metrics are
measurable in essentially none.

## 8. Opponent-profile audit

**What Sonnet received about opponent profiles: nothing.** No band, no underlying metric
conditioned on opponent type, no historical values, no distribution, no sample N, no
similarity axes, no response-vs-similar-opponents. The vocabulary *offered* `opponent_profile`
as a dimension to ask about (bands LOW/MID/HIGH over a closed axis set), but the evidence
contained zero opponent-profile items.

Yet **37 of 112 accepted hypotheses asked opponent-profile questions anyway** — Sonnet was
proposing "how does this team behave against opponents like X" with only the team's own
unconditional averages in hand. V4 later showed those cohorts are highly measurable
downstream (measurable rate 0.981). So the rich opponent-profile information was
`DERIVABLE_BUT_NOT_CONSTRUCTED` and entirely hidden from the LLM.

## 9. Venue audit

**Sonnet received only the label `venue=ALL`** on every one of the 76 items — never
venue-conditioned behavior. There is no `home corners vs away corners`, no `home SoT vs
away SoT`, no `home vs away concession`, no home crosses/possession split anywhere in the
packet.

The distinction is decisive because **the splits were available**: 10/11 fixtures had all
19 metrics cleanly splittable (≥4 home & ≥4 away per team). And Sonnet clearly wanted them:
**58 of 112 accepted hypotheses requested venue conditioning or a `SUBJECT_VENUE_BASELINE`
comparison**, e.g. H1/mt_010243515: *"Does the away team generate corners consistent with
its overall baseline…"* with `conditions:[venue=AWAY]`, `comparison=SUBJECT_VENUE_BASELINE`
— but the only evidence it could cite was the unconditional `AWAY_ATK_corners` scalar. This
is exactly the venue tautology V3/V4 flagged: it is an *evidence-shape artifact*, not a
model error. A venue label is not venue-behavior evidence.

## 10. Metric-relationship audit

V3 exposed 19 metrics **individually as independent scalar means**. It exposed **no
covariance, no cross-metric structure, no per-match co-occurrence**. Sonnet could not
inspect crosses↔corners, possession↔shots, blocked-shots↔corners, SoT↔goals, tackles/
fouls↔cards, or opponent-crossing-concession↔subject-corner-generation at the match level —
only ratios of separate averages it computed in its head. Because per-match rows are
absent, no heterogeneity or conditional dependence between metrics was observable.

## 11. Temporal-compression audit

Everything is `ALL_PRIOR`. Sonnet could **not** see individual prior matches, chronological
ordering, decay, trend, regime change, recent divergence, or formation change across time.
For a team with 71 priors, 71 matches × ~19 metrics ≈ 1,300 per-match observations were
compressed into ~38 scalars — a ~35× temporal-information reduction, before also discarding
venue and opponent. Critically, W5/W10 were derivable (10/11 fixtures ≥10 priors), so the
compression was a construction choice. No tactical-regime claim is made — the point is only
that the data to *look for* one was removed.

## 12. Context-budget analysis

- **Actual V3 packet size:** ~39.2 KB / packet (~9.8K tokens of JSON); reported
  `input_tokens` ≈ 21.5K (schema + vocabulary overhead roughly doubles the visible JSON).
  The 76 scalars themselves are ~33 KB of highly redundant serialization (repeated scope
  keys, long ids).
- **A richer structured research table** exposing, per team: last-10 match rows for ~8 key
  metrics (10 × 8 ≈ 80 numbers), home/away split means (19 × 2), formation split where
  coverage allows, and opponent-profile response summaries (a handful of axes × bands),
  plus availability metadata — is on the order of **2–4× the current evidence payload**,
  i.e. well within a normal 100–200K context window. Estimated ~25–60 KB structured, still
  a fraction of the model's capacity.
- Conclusion: **a compact structured table could expose materially more football
  information (venue splits, recent-vs-long, opponent-profile response, and limited
  per-match rows) without dumping provider JSON and without exceeding practical context
  limits.** The current packet is not context-constrained; it is design-constrained.

## 13. Human-readable fixture audit

See `research/hypothesis_engine/V3_EVIDENCE_HUMAN_AUDIT.md` (companion artifact): for each
of the 11 clean fixtures it lists the upstream data available, the exact evidence Sonnet
saw, all accepted raw hypotheses, their compiled interpretation, and the important upstream
information Sonnet did not see. Hypotheses are listed in full, not ranked or filtered by V4
outcomes.

## 14. What V3 actually tested — classification

Quantitative basis:
- Evidence uniformly unconditional (venue=ALL, window=ALL_PRIOR) across 11/11 fixtures.
- ~60% of audited conditional-capability cells were available/derivable-but-not-shown.
- Venue: available for 10/11 × all 19 metrics, exposed for 0.
- Recent-vs-long: available for 10/11, exposed for 0.
- Opponent-profile: derivable (V4-proven), exposed for 0.
- Formation: genuinely provider-limited (coverage 0.00–0.32) — a real data limit.
- Half-state: genuinely PIT-unsafe.

The attacking/defensive **level** information was rich (19 metrics, both sides, high N); the
**conditional and temporal** structure was compressed or absent, while **formation** and
**half-state** were genuinely provider/PIT-limited. That is a split verdict:

**V3_CONTEXT_CLASSIFICATION: MIXED_CONTEXT_TEST.**

Rich unconditional metric breadth; compressed venue/temporal/opponent-profile structure
that *was* available; genuine provider limits on formation and half-state.

## 15. Bottleneck ranking

1. **Evidence-builder limitation (PRIMARY).** Venue splits, recent-vs-long windows, and
   opponent-profile responses were available/derivable from the PIT-safe corpus for 10/11
   fixtures but were aggregated away into unconditional scalar means. This is the single
   largest, most fixable loss.
2. **Prompt serialization / representation limitation (SECONDARY).** Even the information
   present was shown as 76 disconnected scalars with no per-match rows, no distributions,
   and no cross-metric structure — and at low information density (~33 KB for 76 numbers).
3. **Provider-data limitation (REAL, NARROW).** Formation coverage (0.00–0.32) and
   half-time/minute-level state are genuine provider gaps. This bottleneck is real but
   confined to formation and match-state.
4. **Normalization limitation (MINOR).** No evidence of identity/formation-mapping loss;
   deterministic mappings held.
5. **LLM reasoning limitation (NOT DEMONSTRABLE AS PRIMARY).** Because rich conditional
   information was **not** placed in front of Sonnet, this audit cannot attribute the V3
   FAIL primarily to model reasoning. Sonnet in fact repeatedly *requested* venue and
   opponent-profile structure (58 and 37 of 112 hypotheses) it was never shown. The FAIL is
   consistent with an evidence/representation ceiling, not a proven reasoning ceiling.

## 16. Recommendation (information-fidelity basis; NOT a V5 design, NOT tuned on V4)

**Recommended: D — hybrid.** A future generator experiment should feed
match-level raw metrics (a bounded last-N window) **+** deterministic long-run and split
summaries **+** availability metadata:

- per-team **home/away split** means for the exposed metrics (available 10/11 fixtures);
- **recent-vs-long** (W5/W10/season) summaries (available 10/11 fixtures);
- a compact **opponent-profile response** summary over a few PIT-safe similarity axes
  (derivable; V4-proven measurable);
- a bounded block of **per-match rows** (opponent, venue, key metrics) to expose
  chronology, distribution, and cross-metric co-occurrence;
- explicit **availability/coverage metadata** so the model can see where data is thin
  (especially formation) rather than inferring from silence.

Option A (unchanged evidence) is not recommended: it demonstrably hides available
conditional structure. Options B/C alone are partial; the hybrid preserves both level and
structure within a practical context budget (§12). Formation should be carried with its
coverage flag and treated as frequently unavailable rather than forced. This recommendation
is grounded in information fidelity, not in any V4 predictive outcome.

---

## Architecture confirmation

- $0.00. No Bedrock/LLM/network. Read-only.
- No V2/V3/V4 frozen artifact modified. V3 `FAIL` verdict untouched (this classifies what
  V3 tested; it does not rescore).
- CHAMPION untouched (`0b8f5ff3…`). `p_model`, calibration, predictions, features, gates,
  thresholds untouched. No feature promoted.
- New files only: `_audit_v3_evidence.py`, `out/v3_evidence_audit/capability_matrix.json`,
  this report, and `V3_EVIDENCE_HUMAN_AUDIT.md`.

**V3_EVIDENCE_FORENSIC_AUDIT_COMPLETE**

**V3_CONTEXT_CLASSIFICATION: MIXED_CONTEXT_TEST**
