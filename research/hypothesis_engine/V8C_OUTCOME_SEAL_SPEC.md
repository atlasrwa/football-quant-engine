# V8C outcome seal spec (`v8c_outcome_seal_v1`) — P0

## 1. The defect

`hypothesis_v8c.experiment.run_experiment` (the version on 938acaf58) looped over fixtures
doing, in one process, per iteration:

```
build universe → S select → R select → H select → SCORE THE TARGET
```

So fixture 1's outcome was opened while fixtures 2..N had not yet been selected. Every
selection after the first was made inside a process that had already read real target
outcomes. That is not a freeze; it is a rolling disclosure.

It does not matter that the selection code does not *read* the scored value. The guarantee an
outcome seal has to provide is that **no selection can depend on any outcome**, and a single
process that holds both capabilities cannot provide it — only argue for it.

## 2. The seal: two physically separate processes

| | process 1 | process 2 |
|---|---|---|
| module | `select_freeze.py` | `score_frozen.py` |
| driver | `_run_v8c_select.py` | `_run_v8c_score.py` |
| does | selects S/R/H for the **entire** cohort | scores exactly the frozen selections |
| may read an outcome | **no** | yes |
| imports a scorer | **no** | yes |
| ends by | writing a durable hashed freeze, then **exiting** | writing results |

Process 2 starts only after process 1 has exited. The seal is therefore an operating-system
fact: at the moment any outcome is read, every selection is already on disk and hashed.

## 3. Why the import assertion is real

`select_freeze.assert_no_scorer_loaded()` scans `sys.modules` for any module whose name
contains `scorer` and raises `OutcomeSealViolation` if one is present. It runs at entry and at
exit of the selection pass.

That check is only meaningful if the pre-T code genuinely does not need a scorer. It used not
to be: `pre_t.py` imported `v8c.scorer` for `_weighted_variance`, `ZERO_VARIANCE_FLOOR` and
`unique_opponents_of_cohort`. Those are **cohort** properties, not scoring functions — every
one is computed from strictly-prior observations — so they were hoisted into
`cohort_stats.py`, which imports nothing that can read an outcome.

`ZERO_VARIANCE_FLOOR` is stated **literally** there rather than imported from the frozen V8B.2
scorer, because importing it would load a scoring module and silently defeat the assertion.
The no-drift guarantee is preserved by
`test_outcome_seal.py::test_zero_variance_floor_matches_frozen_scorer`, which asserts the
literal equals the frozen value.

Verified: importing `select_freeze`, `universe`, `controls`, `pre_t`, `grammar`,
`pit_context`, `blind_index` and `cohort_stats` in a clean interpreter loads **zero** modules
matching `scorer`.

## 4. Freeze integrity

The freeze payload carries a `freeze_hash` over its own content. `score_frozen.load_and_verify_freeze`
recomputes it **before touching any outcome** and raises `FreezeIntegrityError` on mismatch,
so a selection edited after the freeze stops scoring dead rather than being scored.

It also refuses when the freeze records `target_outcomes_viewed == true`.

Writes are atomic (`write` → `fsync` → `os.replace`), so a half-written freeze can never be
scored.

## 5. Defense in depth: `TargetBlindIndex`

The wrapper is the **second** layer, not the first. V1 announced a seal it did not have: it
guarded `team_value` but re-exported `.recs`, `.vals`, `.series`, `.pos` and `.comp_idx` as
plain passthroughs, and `vals[metric][target_pos]` hands over the target's own `(home, away)`
pair directly, as does `recs[target_pos].base`.

V2 seals every route:

| accessor | sealed behaviour |
|---|---|
| `team_value(target_pos, …)` | `None` (or raises under `strict`) |
| `vals[metric][target_pos]` | `None` |
| `recs[target_pos]` | `SanitizedRecord` — `fixture_id`, `competition`, `kickoff_unix`, `home/away`, `home_id/away_id` kept; `base`, `rich`, `extra` **empty** |
| `prior_entries(...)` | strictly-prior by construction; a sealed position appearing is recorded and raises under `strict` |

Metadata is preserved because `compile_query`, `_entity_id`, `_select` and
`unique_opponents_of_cohort` genuinely need `competition`/`kickoff_unix`/`home_id`/`away_id`
for entity resolution and the PIT cutoff. None of those is a statistic.

Every read is counted. `target_outcomes_viewed` is true only if a sealed position's own
observation was actually **served** — it is a measurement, not a declaration, and it is
written into the freeze and hashed.

## 6. What the tests prove

| test | proves |
|---|---|
| `test_pre_t_import_set_loads_no_scorer` | in a **subprocess**, the whole pre-T import set loads no scoring module |
| `test_two_process_seal_end_to_end` | spawns process 1, waits for it to **exit**, then spawns process 2; the freeze exists and its hash matches |
| `test_seal_assertion_raises_when_a_scorer_is_loaded` | the assertion is not vacuous |
| `test_scoring_refuses_a_tampered_freeze` | one edited selection stops scoring |
| `test_blind_index_seals_every_documented_accessor` | `.vals`, `.recs` and `team_value` are all sealed; an unsealed position is untouched |
| `test_blind_index_strict_mode_raises_on_every_route` | each route raises under `strict` |

`enforce_seal=False` exists only for in-process unit tests, whose interpreter is shared with
scoring tests and is contaminated by construction. It does not weaken the guarantee: the real
seal is the two-process driver pair, and the end-to-end test exercises exactly that.
