# V8B.2 Report — fixture-level support-gate fix

Narrowly-scoped successor to the frozen V8B.1 scorer. Fixes the P1 evaluation-semantic defect
that made `SCORE_OK` structurally unreachable at the fixture level. Deterministic/free work
only: **zero paid Sonnet calls**, no LLM-layer change, CHAMPION untouched, the 947 reserve
fixtures never opened.

## Root cause (confirmed)

The experimental unit changed between V7.1 and V8B.1. V7.1's pooled/fold cohort spanned many
SUBJECT teams, so `MIN_UNIQUE_TEAMS = 6` (documented at `src/research/hypothesis_v7/pit.py:23`
as "distinct teams/opponents contributing") was a meaningful diversity floor. V8B.1's
fixture-level cohort is one subject team's own prior matches, so `unique_teams == 1`
structurally — and the reused gate required `>= 6`, making `SCORE_OK` unreachable for every arm.

## The fix

- New package `src/research/hypothesis_v8b2/` (the frozen V8B.1 scorer is NOT modified).
- `support.py::classify_fixture_support(raw_n, unique_fixtures, unique_opponents, effective_n,
  max_weight_share)` — version `v8b2_fixture_support_v1`. The diversity unit is explicitly
  `unique_opponents`; there is deliberately **no `unique_teams` field anywhere**.
- `scorer.py::score_fixture(...)` — version `v8b2_scorer_v1`. Identical to the frozen V8B.1
  scorer in every respect (baseline, conditional, scale, orientation, NULL/degeneracy handling,
  recency-family averaging, formula) **except** the support gate, which now uses
  `unique_opponents` computed PIT-safely from the cohort's contributing rows (canonical opponent
  id relative to the cohort entity, both home and away directions, entity itself excluded,
  distinct only).
- Failure reporting now lists **only the predicates that actually failed** (each an explicit
  `{field, have, need|limit}`), fixing the old disjunctive `raw_n=22(<20)`-style nonsense.

### Threshold justification (effect-blind)

`MIN_UNIQUE_OPPONENTS = 6` is the **direct semantic translation** of V7.1's
`MIN_UNIQUE_TEAMS = 6`. Traced from code/spec: the "6" was a diversity floor guarding against a
cohort dominated by too few counterpart identities (the V7.1 comment names "teams/opponents"
interchangeably; the pooled cohort counted distinct subject teams). At the fixture level the
counterpart identity that varies is the opponent, so the floor transfers as-is. The number was
**not** chosen from any Sonnet score, Sonnet-vs-control difference, or Pilot-50 endpoint. All
other thresholds (`MIN_RAW_N=20`, `MIN_UNIQUE_FIXTURES=15`, `MIN_EFFECTIVE_N=10.0`,
`MAX_WEIGHT_CONCENTRATION=0.25`) are retained unchanged, imported from the frozen V7.1 pit.

## Required final fields

```
V8B2_FIXTURE_SUPPORT_VERSION = v8b2_fixture_support_v1   (scorer: v8b2_scorer_v1)

OLD_STRUCTURAL_DEFECT_CONFIRMED = true
OLD_SCORE_OK_REACHABLE          = false   (unique_teams=1 < MIN_UNIQUE_TEAMS=6, always)

NEW_SCORE_OK_SYNTHETIC_REACHABLE   = true  (test_score_ok_is_reachable_end_to_end, UNCONDITIONAL)
NEW_SCORE_OK_REAL_CORPUS_REACHABLE = true  (12 SCORE_OK across arms on the exposed 50)

UNIQUE_OPPONENT_THRESHOLD = 6
THRESHOLD_JUSTIFICATION   = direct effect-blind translation of V7.1 MIN_UNIQUE_TEAMS=6
                            (diversity floor: distinct counterpart identities in the cohort)

EXPOSED50_S_SCORE_OK = 5 / 249  (2.01%)
EXPOSED50_R_SCORE_OK = 7 / 249  (2.81%)
EXPOSED50_H_SCORE_OK = 0 / 249  (0.00%)

FAILURE_REASON_COUNTS (Sonnet arm, accurate/only-actual):
  raw_n=208, unique_fixtures=201, effective_n=133, unique_opponents=57, weight_concentration=16
  (the old universal unique_teams block is GONE; remaining attrition is genuine thin-cohort,
   early-season data — see distributions below)

PIT_TESTS         = pass  (null vs true-zero observed, degenerate scale, future-row exclusion,
                           subject/opponent inversion, home/away opponent identity)
DETERMINISM_TESTS = pass
MUTATION_TESTS    = pass  (raw_n / unique_fixtures / unique_opponents / effective_n /
                           weight_concentration each fail in isolation; return-to-valid restores ADEQUATE)

SCIENTIFIC_PARAMETERS_CHANGED = support-gate diversity unit ONLY (unique_teams -> unique_opponents);
                                no other threshold, no LLM/prompt/packet/search/control change
LLM_LAYER_CHANGED = false

SEALED_947_OUTCOMES_VIEWED = false

CHAMPION_UNCHANGED = true   (0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9,
                             hashed before and after; git-clean)

V8B2_FREEZE_HASH = 00d9ac6cd55765ef27c7e70c90e47f208b8b3d082e077b51c03d4d44bcdebee5
```

## Real-corpus support distributions (exposed-50, Sonnet arm; apparatus diagnostic only)

```
raw_n                p50=8   p95=15  max=29   (MIN_RAW_N=20)
unique_fixtures      p50=8   p95=15  max=29   (MIN_UNIQUE_FIXTURES=15)
unique_opponents     p50=7   p95=13  max=23   (MIN_UNIQUE_OPPONENTS=6)
effective_n          p50=8   p95=15  max=29   (MIN_EFFECTIVE_N=10)
weight_concentration p50=0.125 p95=0.333 max=0.5 (MAX=0.25)
```

Interpretation: `SCORE_OK` is now reachable on real data (12 across arms), and attrition is no
longer universal. The remaining low SCORE_OK rate is a genuine property of these 50
chronologically-earliest (early-season) fixtures — the conditioned cohorts are simply thin
(raw_n median 8, well below the retained MIN_RAW_N=20). Notably `unique_opponents` is now a
*minority* failure (57), confirming the old gate — not the data — was the P1 blocker. This is a
diagnostic, not a scientific result; no threshold was tuned on any outcome difference.

## Systemic upgrade (prevent the class of bug)

- `tests/research/test_evaluator_contract.py`: any evaluator with a `SCORE_OK` terminal state
  must ship an **unconditional** reachability test; the anti-pattern of a conditional
  `if status == SCORE_OK:` check (which V8B.1 had) is explicitly rejected. The frozen V8B.1
  scorer is registered as `SUPERSEDED_UNREACHABLE` and may never be registered as reachable.
- `research/hypothesis_engine/_build_v8b2_freeze.py` **fails closed** (verified: refuses with
  `SCORE_OK_REAL_CORPUS_REACHABLE` when the reachability evidence is absent, and does not
  overwrite the manifest). Freeze gates: synthetic reachability, mutation, PIT+determinism,
  evaluator contract, real-corpus reachability, champion unchanged.

## Governance correction (additive)

`V8B1_TRANCHE50_GOVERNANCE_CORRECTION.json` records `V8B1_TRANCHE50_AUTHORIZED=true`,
`PROTOCOL_DEVIATION=false`. The prior immutable `V8B1_TRANCHE50_PROTOCOL_DEVIATION.json` is left
byte-unchanged; the correction is additive.

## Not done (awaiting your authorization)

The next intended experiment — fresh Sonnet selection on the **next 50 sealed non-T2 fixtures**
from the 947 reserve, then evaluated under this fixed V8B.2 scorer — is **not launched**. That
is the only step that would spend Sonnet (~one Pilot-50's cost), and it requires your explicit
go-ahead. The 947 remain outcome-sealed and untouched.

## Artifacts

- `src/research/hypothesis_v8b2/support.py`, `scorer.py`, `__init__.py`
- `tests/research/hypothesis_v8b2/test_support.py`, `test_scorer.py`
- `tests/research/test_evaluator_contract.py`
- `research/hypothesis_engine/_run_v8b2_exposed50_regression.py` + `V8B2_EXPOSED50_SCORER_REGRESSION.json`
- `research/hypothesis_engine/_build_v8b2_freeze.py` + `V8B2_FREEZE_MANIFEST.json` (self_hash `00d9ac6c…`)
- `research/hypothesis_engine/V8B1_TRANCHE50_GOVERNANCE_CORRECTION.json`
- `research/hypothesis_engine/V8B2_REPORT.md` (this file)
