# V8B.1 — evidence packet design (`v8b1_packet_v1`)

**Status: frozen design, pending implementation + tests. No target outcome read.**

## 1. Design principle (per §8-§11 of the V8B protocol, carried into V8B.1)

Not only averages. Not only prose. Not thousands of unstructured numbers without navigation.
The packet is exactly three layers:

```
RAW PIT-SAFE HISTORICAL ROWS
+
DETERMINISTIC NAVIGATION SUMMARIES
+
CAPABILITY ENVELOPE
```

Reuses `src/research/hypothesis_v71/corpus_index.py::PITIndex` (strict PIT accessors),
`similarity.py::SimilarityEngine` (membership only, never a score),
`capability.py::CapabilityContract.envelope()` (already built exactly for this purpose — its
own docstring says "the machine-readable capability envelope a FUTURE generator may be
shown"), and `search.py` (the query tool, §2 of `V8B1_HYPOTHESIS_SEARCH_SPEC.md`). No new
PIT/shrinkage/similarity logic is written for the packet — it assembles existing, already-
audited primitives.

## 2. Symmetric Team A / Team B raw rows

For each of Team A (home) and Team B (away), for every metric `capability.classify_metric`
reports as `SUPPORTED` or `RESTRICTED` for the target fixture's competition:

```json
{
  "metric": "shots_on_target",
  "for": {"raw_n": 34, "unique_fixtures": 34, "window": "ALL_PRIOR"},
  "against": {"raw_n": 34, "unique_fixtures": 34, "window": "ALL_PRIOR"},
  "home_away_split": {"home_for_n": 17, "away_for_n": 17},
  "provider": "thestatsapi", "unit": "count", "resolution": "match"
}
```

Identical construction for Team A and Team B — the SAME function call with the subject swapped
— so there is no structural asymmetry in what either team is shown (the §9 "symmetric
treatment" requirement, checked by an explicit test: §7 below).

Raw values themselves (the actual per-match observations) are exposed as **navigation-summary
statistics**, not dumped as thousands of bare numbers — see §3. This follows the audited
`EvidencePacketBuilder` pattern already in `src/research/llm_matchup/evidence.py`, reused in
spirit (deterministic, provenance-tagged, PIT-safe) though this packet targets V7.1's ontology
vocabulary rather than the older `llm_matchup` schema, since selections must resolve to V7.1
canonical hypothesis IDs.

NULL vs ZERO: every summary statistic distinguishes "no prior observations" (`null`, an
absent/unavailable value) from "a genuinely measured zero" (`0.0`), exactly as
`corpus_index.PITIndex._read` and `scorer.py`'s own degenerate-case handling already do. A
metric with fewer than `pit.MIN_RAW_N=20` prior observations for a team is marked
`"coverage": "THIN"` rather than either omitted or silently averaged.

## 3. Deterministic navigation summaries

Per team, per metric, per perspective (FOR/AGAINST):

- **Long-run**: `pit_mean` over `ALL_PRIOR` (uniform weighting) — reuses
  `PITIndex.pit_mean` directly.
- **Recent**: `pit_mean` restricted to the team's most recent `W5`/`W10` matches, AND the
  frozen `TIME_DECAY` shrunk estimate (via `recency.Recency.shrink`) — reported side by side
  with the long-run figure so recent-vs-long divergence is directly visible without requiring
  Sonnet to compute a difference itself.
- **Home/Away split**: `pit_mean(..., venue="home")` / `venue="away"`.
- **Competition environment**: `PITIndex.env_mean` for the same metric, so a team's own figure
  can be read against its competition's baseline without an extra request.
- **Opponent-profile context** (for the FIXTURE OPPONENT only, not the subject): which PIT
  tercile (`HIGH`/`MID`/`LOW`) the opponent falls into on each of the six frozen
  `PROFILE_AXES`, reusing the SAME tercile construction `execution.py::build_context` already
  computes — not a new profiling method.
- **Similar-opponent membership** (not a score): for each team, the `k` most similar historical
  opponents to the fixture opponent, reused directly from `SimilarityEngine.similar_opponent_ids`
  — returns team **identities**, never a distance number. Sonnet sees "Team A's record against
  opponents historically similar to Team B" as a navigation pointer, computed the same way the
  compiler itself would compile a `SIMILAR_OPPONENT_COHORT` hypothesis — not a preview of the
  answer, since no aggregate value for that cohort is computed or shown; only which past
  fixtures qualify (fixture identifiers, not outcomes-of-interest).

None of these summaries are the ANSWER to any hypothesis — they are the same PIT-safe
descriptive statistics the compiler's own `compile_query` would read, exposed for navigation.
No summary contains a historical hypothesis's effect, survival, or p-value (§10's explicit
prohibition, carried into V8B.1) — structurally guaranteed by the fact that these summaries are
built by `PITIndex`/`SimilarityEngine` calls, neither of which has ever computed a hypothesis
effect (confirmed: `PITIndex`/`SimilarityEngine`'s own version stamps both declare
`reads_outcomes: False`/`llm_produces_similarity_score: False`).

## 4. Capability envelope

`capability.CapabilityContract.envelope()`, reused **verbatim, unmodified** — this function
already exists specifically for this purpose. Tells Sonnet which metrics/comparators/
conditions are `SUPPORTED` vs `RESTRICTED` vs unavailable for this fixture's competition,
before it queries the search interface, so it can query with informed filters rather than
guessing.

## 5. Formation (§11-§12 of the V8B protocol)

For this RETROSPECTIVE historical-target experiment: formation is included ONLY if a
genuinely PIT-safe historical source exists (a recorded formation for a COMPLETED prior match,
with no announcement-timestamp requirement since the match itself is already resolved — this
mirrors `hypothesis_engine/prompt_v2.py`'s own existing rule: *"Recorded formations for
COMPLETED matches are legitimate historical context."*). The **target fixture's own**
formation is never included — `"target_formation": "FORMATION_UNKNOWN"` always, unconditionally,
regardless of whether formation data exists elsewhere in the corpus for other matches. No
present-day webpage is ever consulted for a historical target (§11's explicit prohibition). The
T-60-minute prospective web-formation path (§12/§29 of the V8B protocol) is a separate,
future, NOT-YET-BUILT upgrade path, unaffected by and not blocking this retrospective
experiment.

## 6. What is explicitly excluded from every packet

- Target fixture outcome (goals, shots, cards, any observed statistic for T itself).
- Any later fixture's data.
- Closing odds, settlement, or any market information.
- Any historical hypothesis's effect, survival state, p-value, or candidate-feature status.
- Any numeric similarity/distance score (membership only, per §3).
- Formation for the target fixture itself (always `FORMATION_UNKNOWN`).

## 7. Required tests before this packet touches a real Sonnet call

1. **Symmetry test**: for a real fixture, Team A's packet block and Team B's packet block
   (with subject/opponent swapped) are byte-identical in *structure* (same keys, same
   metric set, same summary fields) — only values differ.
2. **No-outcome-leakage test**: assert no packet key or value contains the target fixture's
   own observed statistics (cross-check every numeric field's provenance against `PITIndex`
   accessors, which structurally cannot read position ≥ the target's own position).
3. **NULL-not-zero test**: a metric with `< MIN_RAW_N` prior observations for a team renders
   as `"coverage": "THIN"` with `null` values, never a fabricated `0.0`.
4. **Determinism test**: building the same packet twice from the same corpus state yields
   byte-identical JSON (packet content-hashed, mirroring `llm_matchup/evidence.py`'s own
   `packet_hash`).
5. **Formation-unknown invariant**: `target_formation` is `"FORMATION_UNKNOWN"` for every
   fixture in the manifest, with no code path that could set it otherwise.
