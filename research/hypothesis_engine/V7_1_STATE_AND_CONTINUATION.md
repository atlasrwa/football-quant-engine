# V7.1 — execution-closure state and continuation

**Branch:** `feat/v7-1-hardening` (pushed to origin).

**Commit identification.** This document is itself committed *after* the apparatus it
describes. To avoid a self-referential head statement, two commits are named separately:

- **apparatus commit** — the commit that freezes the execution path and refreezes V7.1. Its
  hash is recorded in `V7_1_FREEZE_MANIFEST.json` provenance and in the final mission report;
  it is the commit to check out to reproduce the freeze.
- **documentation commit** — the commit that adds/updates this file and the report. It is the
  branch head and is strictly later than the apparatus commit.

The previous pre-OOS apparatus state is preserved at commit **`f9a3179dd`** (freeze
`v71_freeze_v1`) and is not overwritten; the new freeze is `v71_freeze_v2` and records
`f9a3179dd` as its predecessor under `supersedes`.

## Terminal state

```
V7_1_EXECUTION_PATH_FROZEN_READY_FOR_AUTHORIZATION
CONFIRMATORY_OOS_COMPUTED       = false
CONFIRMATORY_OOS_VIEWED         = false
CANDIDATE_FEATURE_PROMOTION     = false
BEDROCK_CHANGE_REQUIRED         = false     KIRO_HANDOFF_REQUIRED = false
CHAMPION 0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9 — unchanged
```

The previous terminal state `V7_1_READY_FOR_CONFIRMATORY_OOS` was **downgraded**: an
experiment whose authorized execution branch was intentionally unimplemented was not in fact
execution-ready. This mission implemented, tested, hardened and froze that branch.

## What the execution-closure mission changed

**The real confirmatory execution path exists and is frozen** — `src/research/hypothesis_v71/
execution.py`, decomposed into `prepare_execution` → `evaluate_family_evidence` →
`aggregate_endpoints` → `persist_evidence` → `finalize_result`. The scientific functions are
callable on synthetic and development folds and are fully exercised there; the future
authorized run calls exactly these with the fresh fold positions and no code change. There is
no separate real-run-only aggregation.

**A hard one-way authorization gate** — the confirmatory run requires BOTH `--authorize` AND a
valid `V7_1_CONFIRMATORY_AUTHORIZATION.json` token whose bound hashes match the live freeze,
executable source graph, upstream V7 inputs and fresh content. That token does not exist and
was deliberately not created. Opening the door later requires no code change.

**Four integrity commitments, recomputed at preflight:**

- executable **source graph** — the transitive first-party import closure of the driver and
  the execution module is hashed; a byte change refuses even without a version bump;
- **upstream V7 inputs** — every consumed V7 artifact is re-hashed from the referenced file,
  so an unchanged proof cannot mask a changed input;
- **fresh content** — every consumable provider field with nulls preserved, not only fixture
  ids; the same 317 ids with different values is refused;
- **historical PIT snapshot** — a content commitment over the development corpus.

**Two scientific fixes, pre-OOS:**

- **D15 (P0)** — a missing point-in-time confounder was coerced to `0.0`
  (`pit_mean(...)[0] or 0.0`). NULL is not ZERO: only required confounders are constructed, a
  missing one is `None`, and a row missing a required confounder is excluded under a named
  reason rather than imputed. A genuine measured zero is preserved.
- **small-cluster inference** for Endpoint B (~8 clusters) is frozen as an EXACT enumerated
  cluster sign-flip test; the anti-conservative normal-approximation p-value is not the
  primary. Point estimate stays the frozen matched-treated estimand; raw control-pool N cannot
  drive precision; impossible values fail closed.

**Refreeze** — `v71_freeze_v2`, all module version stamps + source graph + upstream + fresh
content bound, reproduced deterministically, `problems: []`.

## Honest limitations (unchanged from the prior state)

1. The fresh window is five weeks and supports only three folds.
2. V7's own confirmatory window is part of V7.1's development data — history is shared;
   outcomes are not.
3. Structural family counts (16 / 51 / 132) were seen before the coverage threshold was fixed.
4. The 5 unmatched families are the tail of exact stratification, not a systematic hole.

## To resume

```bash
cd /home/ubuntu && git checkout feat/v7-1-hardening
/home/ubuntu/.venv/bin/python -m pytest tests/research/hypothesis_v71/ -q      # all green
/home/ubuntu/.venv/bin/python research/hypothesis_engine/_v71_execute.py       # dry run, computes nothing
```

Drivers: `research/hypothesis_engine/_v71_*.py` — `trace`, `diagnostic_replay`,
`fetch_fresh_oos`, `freeze`, `blast_radius`, `reproducibility`, `synthetic_execution`,
`execute`. Artifacts: `research/hypothesis_oos/out/v7_1/` (`V7_1_FREEZE_MANIFEST.json` is the
index).

**The one thing not to do casually.** `_v71_execute.py --authorize` is the confirmatory run. It
now refuses because the authorization token is absent — not because the path is unimplemented.
Once the token is minted (a separate, deliberate one-way-door act) and the run computes a
confirmatory outcome, V7.1 becomes live and immutable and no further tuning is legitimate.
Everything else in this repository can be re-run freely because none of it touches the fresh
outcomes.
