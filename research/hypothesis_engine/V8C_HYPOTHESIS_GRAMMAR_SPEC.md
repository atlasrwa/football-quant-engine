# V8C hypothesis grammar spec (`v8c_grammar_v1`)

**Written BEFORE the grammar implementation, per the repair mission.**
**Successor to V8B.1. `hypothesis_v8b1.search._candidate_shapes` is NOT modified.**
**ZERO Sonnet calls. ZERO target-outcome access. CHAMPION read-only.**

---

## 1. Why this document exists

V8C called `hypothesis_v8b1.search._candidate_shapes()` "the admissible hypothesis universe".
It is not. It is one particular, undocumented **subset**:

| dimension | what `_candidate_shapes` actually emits | what the ontology/compiler actually supports |
|---|---|---|
| window | `ALL_PRIOR` **only** (`window_choices=("ALL_PRIOR",)`) | `ALL_PRIOR`, `W5`, `W10` — all three executed by `compiler._select` |
| conditions | length 0 or 1 **only** | any conjunction; `_passes_filters` ANDs an arbitrary list |
| interactions | **none** | venue×profile, competition×profile, … all compile |

So V8B.1 and V8C measured Sonnet on a research space roughly **one tenth** of the one the
deterministic engine can actually evaluate, while describing it as the whole space. Every
"admissible universe = 19,008" statement in the V8C artifacts is a statement about that subset.
This spec defines the intended V8C grammar explicitly, so the universe is a **declared design
object** rather than a side effect of a helper function's default argument.

---

## 2. The grammar

A V8C hypothesis is the tuple:

```
( target_metric, subject, perspective, comparator, window, conditions )
```

### 2.1 `target_metric` — SINGLE, not a set

**Preserved as single-target.** The mission's default stands: multi-target hypotheses are NOT
introduced, because no concrete scientific requirement demands them and they would change the
statistical unit (a multi-metric hypothesis has no single `observed` value, so `score_fixture`
would need a new aggregation rule — a change of estimand smuggled in as a grammar change).

Drawn from the frozen `CapabilityContract`: `status ∈ {SUPPORTED, RESTRICTED}` **and** the
target fixture's own competition ∈ `admissible_competitions(metric)` (the `COMPADM` gate).
24 metrics are contract-covered; `np_xg` is excluded upstream and stays excluded.

### 2.2 `subject` ∈ { `HOME_TEAM`, `AWAY_TEAM` } — 2

### 2.3 `perspective` ∈ { `FOR`, `AGAINST` } — 2

Named `side` in the spec dict. `FOR` = the subject's own production; `AGAINST` = what the
subject concedes. Both are audited per-side semantics in the capability contract.

### 2.4 `comparator` — all 10 declared by `ontology.COMPARATOR_BINDINGS`

```
LEAGUE_ENVIRONMENT_BASELINE      OPPONENT_OVERALL_BASELINE
OPPONENT_VENUE_BASELINE          SIMILAR_OPPONENT_COHORT
SUBJECT_COMPETITION_BASELINE     SUBJECT_CONDITIONAL_VS_BASELINE
SUBJECT_OVERALL_BASELINE         SUBJECT_RECENT_VS_LONG_BASELINE
SUBJECT_VENUE_BASELINE           SUBJECT_VS_FIXTURE_OPPONENT
```

No comparator is added or removed. `compiler.compile_query` executes every one of them
(that was V7.1's own stated repair over V7).

### 2.5 `window` ∈ { `ALL_PRIOR`, `W5`, `W10` } — 3  ← **restored**

`compiler._select` implements all three (`entries[-5:]`, `entries[-10:]`). V8B.1 emitted only
`ALL_PRIOR`. Restoring W5/W10 is the single largest grammar recovery in this spec.

Note the interaction with support: a `W5` cohort can hold at most 5 observations, so it can
**never** clear `MIN_RAW_N = 20`. `W10` can never clear it either. This is not a reason to
exclude them from the grammar — they are legitimate football questions and the deterministic
engine expresses them — but it means they will be classified `PRE_T_INSUFFICIENT_RAW_N` and
will therefore be absent from `PRE_T_EVALUABLE_IR_SPACE` under the current frozen thresholds.
**That is reported, not hidden**, and it is exactly the kind of fact the pre-T classifier
exists to surface before spend rather than after.

> **Recorded as P2-GRAMMAR-WINDOW.** Whether the frozen support thresholds should have a
> window-aware form is a *scientific* question about the scorer, not an apparatus defect.
> Changing `MIN_RAW_N` here would be altering a threshold mid-mission, which the invariants
> forbid. Logged, not acted on.

### 2.6 `conditions` — 76 shapes

Built from the three dimensions `ontology.FILTER_DIMENSIONS` declares:

| dimension | declared values | notes |
|---|---|---|
| `historical_venue_conditioning` | `HOME`, `AWAY` | |
| `opponent_profile` | `HIGH`, `MID`, `LOW` × 6 axes | axes per §3 |
| `competition` | `SAME` | |

Profile axes (unchanged from `execution.PROFILE_AXES`):
`goals_for`, `goals_against`, `shots_on_target_for`, `shots_on_target_against`,
`possession_for`, `shots_against`.

**Enumerated condition shapes:**

| arity | shapes | composition |
|---|---:|---|
| 0 | 1 | unconditioned |
| 1 | 21 | 2 venue + 18 profile (6 axes × 3 bands) + 1 competition |
| 2 | 54 | **36** venue×profile (2 × 18) + **18** competition×profile (1 × 18) |
| | **76** | |

**The two-condition set is PREREGISTERED and CLOSED.** Only the two families the mission
names are included. They are the meaningful compatible interactions:

- **venue × opponent-profile** — "does the subject concede more to high-possession sides
  *specifically at home*?" Venue and opponent identity are independent nuisance axes, so their
  conjunction is a genuine football question rather than a restatement.
- **competition × opponent-profile** — the same question restricted to same-competition
  history, which controls for cross-competition sampling.

**Deliberately excluded**, and why — these are not omissions:

| excluded | reason |
|---|---|
| venue × competition | no profile axis; both are pure sampling restrictions, and their conjunction is absorbed by `SUBJECT_VENUE_BASELINE`/`SUBJECT_COMPETITION_BASELINE` comparators |
| profile × profile (two axes) | the six axes are strongly collinear (all derived from the same match rows); a two-axis conjunction thins the cohort without adding an independent question |
| any arity ≥ 3 | combinatorial explosion with no preregistered scientific motivation |

> **Recorded as P2-GRAMMAR-TARGETVENUE.** `compiler._passes_filters` also implements
> `TARGET_VENUE` and `TARGET_VENUE_OPPONENT` for `historical_venue_conditioning`, but
> `ontology.FILTER_DIMENSIONS` declares only `HOME`/`AWAY`. The V8C grammar follows the
> **ontology declaration**, since that is the grammar's source of truth and inventing values
> the ontology does not declare would be exactly the "undeclared subset" error this spec
> exists to fix. The gap between declaration and compiler capability is logged for a future
> ontology amendment, not silently closed here.

---

## 3. Opponent-profile semantic — `(team, competition, axis, T)`  ← **P1 PROFILE-COMP**

### 3.1 The defect

The inherited construction used **three different notions of competition in one predicate**:

```python
# execution.build_context / v8c.pit_context (inherited)
cache[(tid, axis)] = mean over the team's prior matches in EVERY competition   # (1) cross-comp
by_comp.setdefault(pre[-1][2], []).append(mv)   # (2) bucketed by the team's LAST competition
# compiler._passes_filters
bounds = terciles.get((entry[2], f.axis))       # (3) the PRIOR MATCH's competition
```

A team's cross-competition mean (1) is filed under whichever competition it most recently
played in (2), and then compared against the thresholds of the competition of the historical
match being filtered (3). **13.4% of teams in this corpus have prior matches in more than one
competition** (promotion, relegation, cup), so this is not hypothetical: for those teams the
band assignment is a comparison between incommensurable quantities.

### 3.2 The V8C semantic — chosen, then verified

**A profile value is `(team, competition, axis, T)`**: the team's mean on that axis over its
prior matches **in that competition**, strictly before `T`. A tercile threshold is
`(competition, axis, T)`, computed over the profile values of teams **in that competition**.
A historical match is banded using the profile keyed to **that match's own competition**.
Like is compared with like, and every term carries the same competition.

Verified structurally before adoption (outcome-blind; three probe fixtures spanning the
1000-fixture manifest's earliest / median / latest kickoff):

| target | `(team, competition)` cells clearing `≥6` priors | competitions with `≥3` qualifying teams |
|---|---|---|
| earliest | 24 / 24 (100.0%) | 1 / 1 |
| median | 150 / 152 (98.7%) | 6 / 6 |
| latest | 152 / 152 (100.0%) | 6 / 6 |

The strict semantic is **coherent and does not empty the universe** — the failure mode the
alternative was meant to avoid does not occur here. The cross-competition-mean-with-pooled-
global-terciles alternative is therefore rejected: it is coherent but strictly less
informative, and the per-competition cells are plentiful.

Floors `MIN_PRIOR_MATCHES_FOR_PROFILE = 6` and `MIN_TEAMS_FOR_TERCILES = 3` are **unchanged**
from `execution.build_context`; only the KEY changes. A `(team, competition)` cell below the
floor yields **no profile**, and a match against an unprofiled opponent is **excluded** from
the cohort — never imputed to `MID`. NULL is not ZERO, and NULL is not MID.

---

## 4. Universe size (measured, not estimated)

```
metrics 24 × subjects 2 × perspectives 2 × comparators 10 × windows 3 × conditions 76
  = 218,880 enumerated shapes                            (V8B.1 subset: 21,120)

  − 16,704  MISSING_REQUIRED_CONDITION  (IR build fails)
  −  12,360 invariant-rejected:
              10,872 BASELINE_ABSORPTION
               1,224 TAUTOLOGICAL_CONDITION
                 192 IDENTICAL_COHORT_BASELINE + SELF_COMPARISON
                  72 BASELINE_ABSORPTION + TAUTOLOGICAL_CONDITION
  = 189,816 structurally valid compile candidates per fixture
```

All 29,064 rejections are **legitimate structural invalidity** — degenerate contrasts the
compiler correctly refuses. No valid hypothesis is destroyed.

Per-fixture cost: enumeration + IR build ≈ 7.2s; compile ≈ 28.5s. The sealed-947 preflight is
therefore a multi-hour parallel run, and is budgeted as one.

`ADMISSIBLE_IR` is this 189,816 set **intersected with the COMPADM gate** (target competition
∈ the metric's admissible competitions), evaluated per fixture.

---

## 5. Reachability contract — **P1 SEARCH-REACHABILITY**

`search()` sorts by `(capability_status, n_conditions, ir_id)` and truncates at
`MAX_RESULTS_HARD_CAP = 50`. With no cursor, **everything after the 50th candidate of any
query is unreachable to S**, while R matches within tier-filtered queries and H (in V8C) ranks
over the entire evaluable set. The three arms did not share an action space.

**V8C contract:** the Sonnet-facing search is **paginated and deterministic**.

- Ordering is the frozen structural key `(capability_status_rank, n_conditions, ir_id)` — a
  total order, since `ir_id` is unique.
- A query returns a page plus an opaque `cursor` (the last `ir_id` of the page) and
  `n_remaining`. Passing the cursor returns the next page under the identical ordering.
- The page size cap stays 50 — a **presentation** limit on one tool result, never a limit on
  the reachable set.
- `unreachable_candidate_count` is **computed**, not asserted: the union of ids reachable by
  exhaustively paginating every declared query shape, differenced against the fixture's
  evaluable universe. The freeze refuses unless it is `0`.

---

## 6. What Sonnet may see — **P1 MEASSPACE**

All three arms select from `PRE_T_EVALUABLE_IR_SPACE`. The pre-T classifier uses
`raw_n` / `unique_fixtures` / `unique_opponents` / `effective_n` / `weight_concentration`
**internally** to build that space.

**Those values are NOT shown to Sonnet.** Two projections of every candidate:

| projection | contains | consumer |
|---|---|---|
| `internal` | structural fields **+** the `pre_t` support block | pre-T classifier, R matching, H ranking, freeze records |
| `llm_facing` | structural fields **only** | the search tool result, i.e. the packet Sonnet sees |

Rationale, stated so it is not mistaken for hiding inconvenient data: the endpoint must
measure **football reasoning**, not sample-size shopping. If Sonnet could read `raw_n`, a
trivially winning policy is "pick the largest cohort", which would make the experiment a test
of whether a model can sort a column. Support adequacy is already guaranteed for every
candidate in the space — every one of them is evaluable — so withholding the magnitudes
removes a confound without removing any information Sonnet needs for the football question.

Enforced by a test asserting the llm-facing projection contains none of those keys. This is
separate from `FORBIDDEN_OUTCOME_FIELDS`, which passes on these keys because they are support
statistics, not outcomes.

---

## 7. Research-family assignment — **P1 RESEARCH-FAMILY**

V8B.1 stamped every candidate `research_family = "V8B1_SEARCH"`, so the multiplicity/confounder
machinery saw one undifferentiated family. V8C assigns family by a **deterministic structural
map** from `(comparator, perspective, conditions)` — never from Sonnet prose, which must not be
able to influence confounder treatment.

| family | structural rule |
|---|---|
| `ATTACK_VOLUME` | `perspective == FOR` and metric ∈ shot/chance/entry group |
| `DEFENSIVE_CONCESSION` | `perspective == AGAINST` and metric ∈ shot/chance group |
| `SET_PIECE_GENERATION` | metric ∈ {`corner_kicks`, `accurate_crosses`} |
| `DISCIPLINE` | metric ∈ {`yellow_cards`, `red_cards`, `cards_2h`, `fouls`} |
| `POSSESSION_CONTROL` | metric ∈ {`possession`, `touches_in_penalty_area`, `ball_recoveries`} |
| `FORM_VS_BASELINE` | `comparator == SUBJECT_RECENT_VS_LONG_BASELINE` or `window != ALL_PRIOR` |
| `CROSS_ENTITY` | `comparator ∈ {SUBJECT_VS_FIXTURE_OPPONENT, OPPONENT_*}` |
| `ENVIRONMENT` | `comparator == LEAGUE_ENVIRONMENT_BASELINE` |
| `MATCHUP_SIMILARITY` | `comparator == SIMILAR_OPPONENT_COHORT` |

Rules are applied in a **fixed documented order**, first match wins, so the map is a total
function and identical inputs always yield an identical family.

---

## 8. Determinism

Same corpus + same capability matrix + same target ⟹ **byte-identical** enumeration, ordering,
evaluable set, pagination, R selection, H ranking and freeze manifest. Every iteration source
is a sorted sequence; no set iteration order escapes into output; `itertools.product` runs over
sorted inputs.
