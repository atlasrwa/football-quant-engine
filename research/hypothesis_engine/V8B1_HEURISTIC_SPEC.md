# V8B.1 — control arm H: deterministic heuristic selection (`v8b1_heuristic_v1`)

**Status: frozen design, pending implementation + tests. No target outcome, no historical OOS
survival, no p-value, no hypothesis quality signal, no future information anywhere in this
arm's logic — enforced by the same structural denylist `search.py` already provides.**

## 1. Purpose (§39 of the V8B instructions, carried into V8B.1)

Represents "what a competent deterministic system could prioritize without an LLM." Not a
strawman: a genuinely reasonable, transparent, simple rule over information legitimately
available before any outcome — coverage, support, descriptive salience, opponent relevance,
complexity penalty. Not tuned to lose to Sonnet (§39's own explicit rule) and not tuned to beat
it either — frozen once, from first principles, before any comparison is run.

## 2. The rule, stated in full

For fixture T, call `search.search()` with no filters (the full admissible universe for T),
then score each candidate `c` by a single, fixed, transparent formula:

```
heuristic_score(c) =
      2.0  if c.capability_status == "SUPPORTED" else 1.0      # coverage term
    + min(c.complexity.n_conditions, 1) * 1.0                  # descriptive-salience term:
                                                                 # reward ONE condition (a
                                                                 # non-trivial cohort exists)
                                                                 # but do not keep rewarding more
    - max(c.complexity.n_conditions - 1, 0) * 0.5               # complexity PENALTY beyond one
                                                                 # condition (§39: "complexity
                                                                 # penalty" is an ALLOWED input)
    + (0.5 if c.complexity.uses_similarity else 0.0)            # opponent-relevance term:
                                                                 # a same-fixture-opponent-aware
                                                                 # cohort is a legitimate,
                                                                 # outcome-blind proxy for
                                                                 # "relevant to this matchup"
```

Take the top `K_valid(T)` candidates by `heuristic_score`, descending; ties broken by
`hypothesis_id` (SHA-256 order, same discipline as everywhere else in this codebase).

**Why these four terms and no others, stated so the choice is auditable:**
- **Coverage** (`SUPPORTED` > `RESTRICTED`): a metric admissible everywhere is more broadly
  applicable than one admissible only on a competition subset — a property of the corpus/
  provider, never of any effect.
- **Descriptive salience via `n_conditions >= 1`**: an unconditional `SUBJECT_OVERALL_BASELINE`
  question is the least "researched" thing a system could propose; rewarding exactly one
  condition captures "this is doing SOME cohort-defining work" without rewarding arbitrarily
  deep conditioning, which the complexity penalty term then explicitly discourages.
- **Complexity penalty beyond one condition**: directly named as an allowed input by §39;
  encodes the same principle the audited prompt (`hypothesis_engine/prompt_v2.py`) already
  states to Sonnet ("every extra condition shrinks the sample it will be measured on").
- **Opponent relevance via `uses_similarity`**: a `SIMILAR_OPPONENT_COHORT` question is
  structurally "aware" of the specific fixture opponent in a way a `SUBJECT_OVERALL_BASELINE`
  question is not — again a structural property (does the comparator's own binding read the
  fixture opponent's identity), never a measured effect.

**What is explicitly NOT in the formula, per §39's disallowed-inputs list:** target outcome,
historical OOS survival, hypothesis quality, p-values, future information. None of these are
readable from anything `search.py` returns (its own denylist test already guarantees this), so
the heuristic cannot accidentally use them even if someone tried to add a term that did.

## 3. Determinism

Given the fixture manifest and `K_valid(T)` per fixture (fixed once Sonnet's own selections are
frozen), arm H's selections are a pure, parameter-free function of `search.py`'s deterministic
output. No randomness, no tunable weight adjusted after seeing any result.

## 4. Frozen BEFORE any comparison, immutable after

The four coefficients above (`2.0`, `1.0`, `-0.5`, `0.5`) and the tie-break rule are fixed by
this document, before Sonnet's selections are even generated, and are never adjusted after
seeing Endpoint 3's result (§39: "Do not tune it to lose to Sonnet" — symmetrically, this audit
does not tune it to beat Sonnet either; it is derived once, from principle, and left alone).

## 5. Required tests

1. **Determinism**: same fixture, same `K_valid(T)` → byte-identical top-K selection across
   two independent runs.
2. **Formula correctness**: constructed candidate sets with known expected orderings (e.g. a
   `SUPPORTED`+1-condition+similarity candidate must outrank a `RESTRICTED`+0-condition
   candidate) confirm the scoring formula is implemented exactly as specified, not
   approximately.
3. **No outcome-shaped input**: a structural test confirming the heuristic function's body
   only ever reads fields already proven absent-of-outcomes by `search.py`'s own denylist test
   — i.e., it cannot even syntactically reference a forbidden field, since none exists on the
   candidate dict it consumes.
4. **Size match**: exactly `min(K_valid(T), len(candidates))` selections returned per fixture.
5. **Tie-break determinism**: candidates with identical `heuristic_score` are ordered
   consistently by `hypothesis_id` across repeated runs.
