# V8B.1 — control arm R: structurally matched blind selection (`v8b1_blind_v1`)

**Status: frozen design, pending implementation + tests. Reads no outcome, no LLM output
beyond Sonnet's own valid-selection COUNT per fixture (never its content).**

## 1. Purpose (§38 of the V8B instructions, carried into V8B.1)

For each fixture T, draw a blind, outcome-blind control selection from the SAME admissible
universe `search.py` exposes, matched where practical on structural properties, sized to
exactly `K_valid(T)` = the number of Sonnet's own `SCORE_OK`-eligible valid selections at T
(§40 of the V8B instructions) — so Sonnet can never win or lose purely by selecting more or
fewer hypotheses than its control.

## 2. What "structurally matched" means here

Reuses the exact matching dimensions V7.1's own `controls.py::SLOTS` already defines for its
slot-inhabitation proof (not a new matching scheme):

```
target_metric, subject, side, mechanism family (comparator), complexity (n_conditions),
support bucket (capability_status: SUPPORTED vs RESTRICTED), coverage/capability class
```

Match procedure per fixture T, per Sonnet selection `s` (in the order Sonnet emitted them):

1. Query `search.search()` for the SAME fixture's admissible universe with filters set to
   `s`'s own `target_metrics[0]`, `subject`, `side`, `comparator` (family match).
2. Among the returned candidates, prefer one whose `complexity.n_conditions` and
   `capability_status` match `s`'s exactly.
3. If no exact match exists, relax in a FROZEN, PRE-STATED order (§3) — never chosen ad hoc
   after seeing what's available.
4. Exclude any candidate already used as a control for an earlier Sonnet selection at the SAME
   fixture (no double-counting one control hypothesis as two "independent" control votes).
5. Among remaining ties, break deterministically by `hypothesis_id` (SHA-256 order) — the same
   tie-break discipline used throughout this codebase (`controls.py`, `V6.1`'s own
   `fixture_selection.json`).

## 3. Frozen relaxation order (must not be reordered after seeing results)

1. Exact match on all six dimensions.
2. Relax `n_conditions` (allow ±1), keep everything else exact.
3. Relax `capability_status` (allow `SUPPORTED` in place of `RESTRICTED` or vice versa), keep
   metric/subject/side/comparator exact.
4. Relax `comparator` to any comparator in the SAME mechanism_type family (reusing
   `search.MECHANISM_TYPES`'s own grouping), keep metric/subject/side exact.
5. Relax `side` (FOR↔AGAINST), keep metric/subject exact.
6. If still no candidate: no control is assigned for this Sonnet selection at this fixture,
   recorded as `UNMATCHED` (mirroring V7.1's own honest reporting of its 5 unmatched Endpoint-B
   families rather than forcing a match that does not exist) — never relaxed further.

## 4. What is explicitly NOT used to select the blind control

- The Sonnet selection's own `research_reason`, `mechanism_summary`, or any prose field.
- Any historical hypothesis effect, OOS status, or quality score for the candidate.
- Anything about how well the candidate is expected to perform.

Only structural metadata `search.py` already exposes (which itself excludes all of the above
by construction, per its own denylist test) ever enters the matching decision.

## 5. Determinism

Given the same Sonnet selection set (frozen at `V8B1_SELECTION_FREEZE.json` time) and the same
fixture manifest, arm R's selections are a pure function with no randomness — the relaxation
order and tie-break rule are total and deterministic. Re-running the matcher against a frozen
selection set produces byte-identical output.

## 6. Required tests

1. **Size match**: `len(blind_selections[T]) == K_valid(T)` for every fixture (subject to the
   `UNMATCHED` exception, which is recorded, not silently short).
2. **No double-use**: no `hypothesis_id` is used as a control more than once within the same
   fixture.
3. **No outcome/prose input**: a structural test confirming the matcher function's signature
   and body never reference any Sonnet field other than the six structural matching
   dimensions and the selection count.
4. **Determinism**: same frozen selection set, same manifest → byte-identical blind arm output
   across two independent runs.
5. **Relaxation-order test**: constructed cases at each relaxation tier, confirming the matcher
   picks the tightest available match and never skips a tier that has a valid candidate.
