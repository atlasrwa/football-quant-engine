# V8B.1 — deterministic hypothesis search interface (`v8b1_search_v1`)

**Status: frozen design, pending implementation + tests. No outcome, effect, p-value, or OOS
status is exposed anywhere in this interface.**

## 1. Purpose

Per instruction (§24-§27 of the V8B protocol, carried into V8B.1): Sonnet must not be asked to
mentally enumerate the admissible hypothesis universe from memory, and the full universe must
never be pasted into the prompt. Instead Sonnet is given a deterministic, outcome-blind search
tool — analogous to a researcher querying a database — that lets it navigate the same universe
V7.1's own generic enumerator (`controls.py::enumerate_pool`) and ontology
(`ontology.py::COMPARATOR_BINDINGS`, `FILTER_DIMENSIONS`) already define.

## 2. What the interface returns (and never returns)

For a query, the interface returns a bounded, deterministically-ordered list of **canonical
hypothesis candidates**, each with:

```json
{
  "hypothesis_id": "<ir_id() hex digest — the SAME identity ir.py already computes>",
  "structural_description": "<IR.describe() — plain-English reconstruction, unchanged>",
  "target_metrics": ["shots_on_target"],
  "subject": "HOME_TEAM",
  "side": "FOR",
  "comparator": "SUBJECT_CONDITIONAL_VS_BASELINE",
  "conditions": [{"dimension": "opponent_profile", "value": "HIGH", "axis": "shots_against"}],
  "capability_status": "SUPPORTED",
  "admissible_competitions": ["champ", "epl", "laliga", "laliga2", "ligue1", "ligue2"],
  "complexity": {"n_conditions": 1, "n_target_metrics": 1, "uses_similarity": false}
}
```

**Never returned, by construction (not by convention — see §5's test requirement):** historical
effect, `oos_quality_score`, direction agreement, p-value, terminal state, candidate-feature
status, fold results, or anything computed from a real target fixture's observed statistic.
The interface is built entirely from `ontology.py`, `capability.py::CapabilityContract`, and
`ir.py::build_ir` — none of which read an outcome (confirmed already, `uses_llm: False,
reads_outcomes: False, reads_prose: False` in `ontology.version_stamp()`; `contains_outcomes:
False, contains_effect_estimates: False` in `capability.envelope()`).

## 3. Query grammar Sonnet may use

Structural filters only, matching the fields already in `ontology.py`/`capability.py` (no new
vocabulary invented):

| filter | values | source |
|---|---|---|
| `target_metric` | any audited metric name | `capability.METRIC_SEMANTICS` |
| `subject` | `HOME_TEAM` \| `AWAY_TEAM` | `ontology.py` (mapped from IR's `SUBJECT`/`FIXTURE_OPPONENT` roles at query time) |
| `side` | `FOR` \| `AGAINST` | `ontology.PERSPECTIVES` |
| `comparator` | any of the 10 frozen comparators | `ontology.COMPARATOR_BINDINGS` |
| `mechanism_type` | free-text tag mapped deterministically onto comparator families (e.g. `"attack_x_defense"` → `SUBJECT_VS_FIXTURE_OPPONENT`/`SUBJECT_CONDITIONAL_VS_BASELINE` with an `opponent_profile` condition; `"similar_opponent"` → `SIMILAR_OPPONENT_COHORT`; `"recent_regime"` → `SUBJECT_RECENT_VS_LONG_BASELINE`) | new, but a pure relabeling of existing comparators, not a new grammar |
| `opponent_profile_dimension` | any of `PROFILE_AXES` (`goals_for`, `goals_against`, `shots_on_target_for`, `shots_on_target_against`, `possession_for`, `shots_against`) | `execution.py::PROFILE_AXES` |
| `venue` | `HOME` \| `AWAY` | `ontology.FILTER_DIMENSIONS["historical_venue_conditioning"]` |
| `competition_conditioned` | `true` \| `false` | maps to a `competition=SAME` condition |
| `window` | `ALL_PRIOR` \| `W5` \| `W10` | `ontology.WINDOWS` |
| `max_conditions` | integer | bounds `len(conditions)` |
| `max_results` | integer, capped at 50 | pagination bound, frozen (§4) |

Sonnet supplies a subset of these; unset filters are wildcards. The interface enumerates the
**already-existing candidate pool for the current target fixture** (i.e. it is called once per
fixture, with that fixture's own admissible universe as context — the SAME universe
`controls.enumerate_pool`/`slot_inhabitation` already prove is inhabited), filters by the
query, and returns up to `max_results`.

## 4. Determinism contract

- **Same query, same fixture → same result set, same order.** Ordering is: primary key
  `capability_status` rank (`SUPPORTED` before `RESTRICTED` before others — structural
  properties only, never an outcome-derived rank), secondary key `n_conditions` ascending
  (simpler first — a structural complexity property, not a quality judgment), tertiary key
  `hypothesis_id` (the SHA-256 `ir_id()`) ascending as the final deterministic tie-break.
- **`max_results` is frozen at 50 per call** (this document), never changed mid-run.
- **No `random`, no `hash()`, no timestamp-dependent ordering** — the same SHA-256-based
  determinism discipline `controls.py::_stream_int` already uses elsewhere in this codebase.
- The candidate pool for a given fixture is itself deterministic: it is the set of canonical
  IDs reachable by `build_ir` from the ontology's own finite grammar, restricted to the
  metrics `capability.classify_metric` reports as `SUPPORTED`/`RESTRICTED` for that fixture's
  competition — not a sample, not a truncation of a larger set based on anything outcome-
  related.

## 5. Required tests before this interface is used in any real call

1. **No-outcome-field test**: assert programmatically that no key in any returned candidate
   dict matches a denylist (`effect`, `score`, `p_value`, `oos_quality_score`,
   `direction_agreement`, `terminal_state`, `candidate_feature`, `survives`) — a structural
   test on the return schema itself, not a manual review.
2. **Determinism test**: the same query against the same fixture, called twice, returns
   byte-identical JSON.
3. **Query correctness test**: a query with `comparator=SIMILAR_OPPONENT_COHORT` returns only
   candidates whose `comparator` field is exactly that value; a query with
   `max_conditions=0` returns only candidates with an empty `conditions` list; etc. — one
   assertion per filter dimension.
4. **Canonical-ID round-trip test**: every returned `hypothesis_id` resolves, via
   `ir.build_ir` on the same structural spec, back to an `IR` whose own `ir_id()` matches —
   proving the ID is not a free-floating string Sonnet could later mismatch against a
   different structural meaning.

## 6. Why this satisfies §28 (final selection must use canonical IDs)

Sonnet's tool-use loop is: query the search interface → read `hypothesis_id` +
`structural_description` + capability metadata for a handful of candidates → decide which (if
any) deserve investigation → emit a final selection **referencing `hypothesis_id` values
already returned by the search tool in this same call**, never a freely-typed metric name or
condition. The response schema (defined in the research protocol, §9 of this task list)
validates every submitted `hypothesis_id` against the set of IDs the search tool actually
returned during that fixture's session; an unrecognized ID fails validation exactly like an
unrecognized `evidence_ref` does (§30 of the V8B instructions).
