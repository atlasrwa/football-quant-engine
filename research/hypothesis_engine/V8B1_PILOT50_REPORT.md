# V8B.1 Pilot-50 Report

Status: **PILOT** — not final proof. Zero paid Sonnet calls were made in this evaluation phase
(the 50 Sonnet selections were reused from the pre-existing operational tranche). The remaining
947 fixtures and the 3 T2 canaries remain outcome-sealed and untouched.

## Headline

The pilot produced a **null-evaluability result**: under the frozen V8B.1 fixture-level scorer
*exactly as committed*, **no selection in any arm** (Sonnet, matched-blind R, deterministic
heuristic H) reaches `SCORE_OK`, so **neither primary endpoint has a single evaluable paired
fixture**. The comparison Sonnet-vs-blind and Sonnet-vs-heuristic is therefore **undefined**,
not favorable and not unfavorable.

The cause is a **pre-existing latent defect in the frozen scorer**, diagnosed at code level and
independent of the model, the controls, and the pilot cohort. It was frozen into the apparatus
before any outcome was opened and was not introduced by this evaluation.

## Required fields

```
V8B1_PILOT50_COMPLETE = true

TARGET_FIXTURES = 50

SONNET_OK       = 47
SONNET_ABSTAIN  = 2      (mt_406686795, mt_012249732)
SONNET_INVALID  = 1      (mt_195507497 — fail-closed unknown hypothesis_id; frozen attrition)

R_COMPLETE = true        (matched-blind; 249/249 Sonnet valid selections matched, 0 unmatched)
H_COMPLETE = true        (deterministic heuristic; 249 selections)

SELECTION_FREEZE_BEFORE_OUTCOMES = true   (V8B1_PILOT50_SELECTION_FREEZE.json, self_hash 5aab04f7…, committed 0cb55fe55 before any outcome opened)

OUTCOME_FIXTURES_OPENED = 50   (exactly the pilot 50; none of the 947, none of the 3 T2 canaries)

EVALUABLE_SONNET_VS_BLIND     = 0
EVALUABLE_SONNET_VS_HEURISTIC = 0

SONNET_VS_BLIND     = UNDEFINED_NO_EVALUABLE_FIXTURES
SONNET_VS_HEURISTIC = UNDEFINED_NO_EVALUABLE_FIXTURES

RESEARCH_YIELD (Sonnet, across all 50):
  selected            = 249 valid selections (over 47 OK fixtures)
  canonical_resolved  = 249  (100% resolved to a real canonical IR)
  measurable          = 249  (100% reached a NAMED terminal scorer status; 0 exceptions)
  support_qualified   = 0    (SCORE_OK)
  OOS_scorable        = 0
  abstentions         = 2 fixtures (legitimate; zero selections)
  invalid             = 1 fixture (mt_195507497; fail-closed; frozen attrition)

PRIMARY_RESULT_FROZEN_BEFORE_TRACE_REVIEW = true   (V8B1_PILOT50_PRIMARY_RESULT.json, self_hash 6abff332…)

CHAMPION_UNCHANGED = true   (sha256 0b8f5ff3…c00c9, verified before selection, before outcome opening, and after evaluation)

PILOT_INTERPRETATION = INCONCLUSIVE_APPARATUS_DEFECT
  (the pilot cannot distinguish PROMISING_SIGNAL / NO_CLEAR_ADVANTAGE / NEGATIVE_EVIDENCE,
   because the frozen scorer admitted zero measurements from any arm)
```

## Root cause (code-level, factual)

- `scorer.score_fixture` (`src/research/hypothesis_v8b1/scorer.py:141–144`) calls
  `V7PIT.classify_support(..., unique_teams=1, ...)` with `unique_teams` **hardcoded to 1** —
  correct for a single-team fixture-level cohort.
- The reused frozen support gate (`src/research/hypothesis_v7/pit.py:96–98`) marks a cohort
  `SUPPORT_LOW` whenever `raw_n < 20` **OR** `unique_fixtures < 15` **OR**
  `unique_teams < MIN_UNIQUE_TEAMS (=6)`.
- Since `unique_teams == 1 < 6` is **always** true, `classify_support` can never return
  `ADEQUATE_SUPPORT`, so `score_fixture` can **never** return `SCORE_OK` at the fixture level —
  regardless of history depth or which arm made the selection.

Independent confirmation:
1. 0 `SCORE_OK` across **all three arms**, including the deterministic heuristic that
   deliberately selects the highest-coverage, lowest-complexity hypotheses.
2. The frozen scorer test battery (`tests/research/hypothesis_v8b1/test_scorer.py`) never
   asserts a real `SCORE_OK` is produced — it only checks the status is one of the four named
   terminal statuses. **`SCORE_OK` reachability was never proven before the freeze.**
3. Target observed values *were* read (only 2 "observed unavailable" refusals across all arms),
   so the seal opened real data and the evaluation driver reproduces the frozen apparatus
   correctly.

Not caused by: the evaluation driver, thin unconditional team history (pilot prior_n:
min 20 / median 27 / max 36, satisfying the manifest's ≥20 rule), the Sonnet selections
themselves (the defect is arm-independent), or the cohort choice.

Corroborating magnitudes: across the 693 scored selections, conditioned-cohort `raw_n` maxes at
35 and only 12 reached `raw_n ≥ 20`; every one of those 12 was still blocked by
`unique_teams = 1 < 6`.

## Cost / operational (Sonnet selection phase — reused, not re-spent here)

- Paid Sonnet calls this evaluation phase: **0**.
- Pilot-50 Sonnet selection (already spent in the prior tranche): input 3,987,593 tok /
  output 383,216 tok / total 4,370,809 tok; **$17.71**; per-fixture cost p50 $0.33 / p95 $0.47 /
  max $0.52; latency p50 119 s / p95 149 s / max 154 s; 50/50 terminated via forced submit.
- Evaluation phase (controls + scoring) is deterministic and free (no network, no Bedrock).

## Governance

The 50-fixture tranche was executed overnight **without the required human authorization**
(commit `c4b70eb30`). This is recorded permanently in `V8B1_TRANCHE50_PROTOCOL_DEVIATION.json`
and preserved here. The governance violation did **not** break the scientific seal: outcomes
were unviewed until the authorized pilot opening, no evaluation had occurred, the frozen design
was unchanged, and CHAMPION is intact. The tranche is accepted as `V8B1_PILOT_50` with the
deviation flag attached.

## Sequence integrity

all-arm selection freeze (committed, outcomes sealed) → outcome opening for exactly 50 →
deterministic scoring → **primary result frozen** → (only then) qualitative trace review. The
research traces were **not** read before the primary result was frozen; the descriptive trace
notes below cannot and did not change any frozen number.

Descriptive trace note (post-freeze, non-load-bearing): the 47 OK fixtures carry 2–8 selections
each; Sonnet's traces contain behavioral maps, matchup tensions, similar-opponent insights,
regime questions, and discarded-candidate lists — substantive research content. None of it is
measurable under the current frozen scorer.

## Interpretation

This pilot is **inconclusive about Sonnet's selection quality**. It did not produce a signal for
or against Sonnet, because the frozen apparatus admitted **zero measurements from any arm**. It
did, however, produce one decisive and valuable finding: **the frozen V8B.1 fixture-level
scorer's support gate is unsatisfiable** (`unique_teams` is structurally 1 but the gate requires
≥ 6), so no fixture-level evaluation — for any arm — can ever score under it as committed.

## Does the 50-fixture pilot justify spending on the larger 1,000-fixture experiment?

**No — not yet, and not as currently frozen.** Spending ~$335 to run the remaining 947 fixtures
under the present scorer would deterministically reproduce the same null-evaluability outcome:
0 `SCORE_OK`, 0 evaluable paired fixtures, no Sonnet-vs-control measurement. The larger run
cannot become informative until the scorer's support-gate defect is corrected and re-frozen
(and its `SCORE_OK` reachability actually proven by test). That correction is a scorer change,
which is explicitly out of scope here and requires new, explicit authorization.

Recommended next step (for your decision, not executed here): authorize a scoped fix to the
frozen fixture-level support gate (the `unique_teams` semantics at fixture level), prove
`SCORE_OK` is reachable on a synthetic battery, re-freeze the scorer, then re-run the Pilot-50
evaluation (still zero new Sonnet spend — reuses the same 50 selections) before deciding on the
1,000-fixture spend.

## Artifacts

- `V8B1_TRANCHE50_PROTOCOL_DEVIATION.json` — permanent governance flag
- `V8B1_PILOT50_CONTROL_R.jsonl` / `V8B1_PILOT50_CONTROL_H.jsonl` — control arms (deterministic)
- `V8B1_PILOT50_SELECTION_FREEZE.json` — immutable all-arm freeze (pre-outcome), self_hash 5aab04f7…
- `V8B1_PILOT50_OOS_RESULTS.json` — per-fixture, per-selection scorer output (post-seal)
- `V8B1_PILOT50_PRIMARY_RESULT.json` — frozen primary result, self_hash 6abff332…
- `V8B1_PILOT50_REPORT.md` — this report
