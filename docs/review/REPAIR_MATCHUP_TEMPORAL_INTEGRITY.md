# Repair note — simultaneous-kickoff leakage and season-boundary contamination

**Scope.** Two temporal-integrity defects in `src/research/matchup/features.py`, the feature
builders behind `matchup/design.py`. Both were reproduced before any code changed, and both are
reachable in the real 5,319-match corpus. Nothing else is repaired.

Base: `d36e029a9` (head of PR #21, unmerged — stacked on it, though the content is independent
of the freeze work). Final SHA is reported in the PR.

---

## 1. Defect A — simultaneous-kickoff leakage

`StrengthRatings.__init__` iterated `sorted(recs, key=lambda x: x.kickoff_unix)` and, for each
match, took a PIT snapshot and then immediately updated the running league/team state. For two
matches sharing an exact `kickoff_unix` — a full 15:00 league round — the first match updated
the state and every later match in that round snapshotted a state **containing a result that had
not happened yet at its own kickoff**.

The module docstring claimed "STRICTLY point-in-time: for a target fixture F they read only prior
matches (kickoff_unix < F.kickoff_unix)". That held for `prior_rows` and `LeagueEnvironment`,
both of which use a strict `<`. It did not hold for the incremental ratings.

**Reachability.** Of 5,319 corpus matches, **3,008 (56.55%) share a kickoff instant with another
match**; 781 distinct instants carry more than one match, the largest carrying 12. This was the
common case, not an edge case.

**Reproduction.** History with a flat league mean, then two fixtures at `t=200`, `SIM1` a
blow-out:

```
attack(SIM2, C)  input order [SIM1, SIM2] : 0.6785714285714286
attack(SIM2, C)  input order [SIM2, SIM1] : 0.7857142857142857
attack(SIM2, C)  with SIM1 moved to t=300 : 0.7857142857142857   <- the no-leak value
```

Two facts at once: the snapshot depended on the order the input list happened to be in, and the
simultaneous `SIM1` changed `SIM2`'s snapshot.

**Repair.** Matches are grouped by exact `kickoff_unix`. Every match in a group is snapshotted
against the same state (pass 1); only then do the group's own results become the past (pass 2).
Order within a group is irrelevant by construction.

**Effect on the corpus** (`corner_kicks`):

| | |
|---|---|
| attack snapshots changed by the fix | **4,321 of 10,638 (40.62%)** |
| unchanged | 6,049 |
| `None` in both (cold start) | 268 |
| snapshots that move when the input list is merely **shuffled** — before | **4,668** |
| the same, after | **0** |

The last two rows are the determinism result: the previous builder's output depended on input
ordering for 4,668 fixture-team snapshots. It no longer depends on it at all.

## 2. Defect B — season-boundary contamination

`HistoryIndex.current_season(team, before)` returns the season-instance of the team's most recent
match *before* `before` — the season the team **last played in**. `design.py` used it as the
season for "current-season" rolling form. For a fixture early in a new season-instance, before
that team has played in it, this returns the **previous** season, so:

* prior-season form was returned labelled as current-season form, and
* `MIN_HISTORY` cold-start was satisfied by stale prior-season matches instead of failing closed.

The docstring's "Rolling windows never span a season-instance" was technically true — the window
stayed inside one season — but it was the *wrong* season.

**Reachability.** **134 of 10,638 (fixture, team) pairs (1.26%)** have
`current_season() != season_of(fixture)`.

**Reproduction.** Team A with six S1 matches and none yet in S2, target in S2:

```
target fixture season    : L:S2
current_season() returns : L:S1
rolling "current-season" : 7.0      <- prior-season form, cold start not enforced
```

**Repair.** `HistoryIndex.target_season(rec)` returns `season_of(rec)` — the season of the
fixture being predicted, which is a property of the target and never of the history available for
it. `design.py`'s three feature builders use it. `_roll` then finds zero rows and abstains, which
is the documented cold-start behaviour.

```
target_season()   : L:S2
rolling value now : None    (fails closed)
```

**`current_season` is deliberately unchanged.** It answers a different, legitimate question —
"when did this team last play?" — and it has consumers outside this package. Changing its return
would have silently altered every one of them. Its docstring now states what it returns, why it
is not the right input for a current-season feature, and points at `target_season`.

## 3. Blast radius — what this does and does not touch

`features.HistoryIndex`, `StrengthRatings` and `LeagueEnvironment` are constructed in exactly two
places: `src/research/matchup/design.py` and `tests/research/test_matchup_leakage.py`. The
`matchup/` research harness (`run_experiments`, `run_gbt`, `gen_artifacts`,
`run_phase_f_and_forensics`, `run_count_uncertainty`) is downstream of `design.py`.

**The LLM evidence path is NOT affected.** `llm_matchup/evidence.py`, `evidence_v2.py` and
`phaseb_harness.py` use `cohorts.HistoryIndex` — a different class in a different module. Nothing
in `llm_matchup/` imports `matchup.design`. No evidence packet, packet hash or frozen generation
fingerprint changes as a result of this repair.

**But `cohorts.HistoryIndex.current_season` has the same season-boundary shape** —
`seasons[-1] if seasons else None`, the season the team last played in — and it *does* feed the
LLM evidence path. That is recorded as a **new, distinct open finding** rather than repaired
here, because changing it would alter evidence packet contents and therefore the frozen 4.5/4.6
generation fingerprints. That is a decision about regenerating frozen scientific artifacts, not a
bug fix to be slipped into this PR.

`LeagueEnvironment.env` and `prior_rows` were checked for the same shape **by test, not by
inspection**, and are correct: both use a strict `<`, and simultaneous fixtures receive identical
prior-only baselines.

## 4. Tests

`tests/research/test_matchup_leakage.py` — 14 tests, offline, no corpus or credentials needed.

| Case | Covers | |
|---|---|---|
| strength rating ignores a simultaneous match | defect A | control: moving `SIM1` strictly later must not change `SIM2` |
| strength rating independent of simultaneous input order | defect A | the ordering property |
| league env ignores a simultaneous match | regression guard | already correct — not a defect statement |
| `target_season` is the fixture's own season | defect B | asserts the stale value *was* available, then that it abstains |
| design builder abstains across a season boundary | defect B | end-to-end through the consuming builder |

The control matters: order-invariance **alone** would be satisfied by an implementation that
leaked identically in both orderings, so the "SIM1 moved later" comparison is what establishes
the absolute value is right.

```
pytest tests/research/test_matchup_leakage.py -q   ->  14 passed
```

**Mutation-checked:** against the previous builders, **4 of the 5 new cases fail**. The fifth is
the `LeagueEnvironment` guard, which correctly passes in both — it guards behaviour that was
already right.

`tests/research/test_matchup_leakage.py:6` also carried `sys.path.insert(0, "/home/ubuntu")`,
which put the deployed tree ahead of the checkout under test. Removed; the 9 pre-existing tests
pass identically before and after that removal on its own, and again after the feature changes.

## 5. Remaining limitations

* **`cohorts.HistoryIndex.current_season` carries the same season-boundary defect** and feeds the
  LLM evidence path. Open, distinct, and deliberately untouched (§3).
* **This does not re-derive any published matchup result.** Feature values change for 40.62% of
  fixture-team rating snapshots, so any artifact produced by the `matchup/` harness before this
  commit was computed under the leaking builder and would need regeneration to be comparable.
  Nothing was regenerated here.
* **Only `corner_kicks` was measured** for the corpus impact figures; other stats use the same
  code path, so the mechanism is identical, but the exact percentages are stat-specific.
* Model identity, spend enforcement, lock/preflight coverage, output-root bindings and the
  freeze-coverage findings are untouched and remain open.
