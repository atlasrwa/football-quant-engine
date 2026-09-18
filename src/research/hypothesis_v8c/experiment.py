"""SUPERSEDED -- this module contained the P0 OUTCOME-SEAL defect and must not be used.

`run_experiment` selected AND scored one fixture before the remaining cohort had been selected:

    for pos in fixture_positions:
        build universe -> S select -> R select -> H select -> SCORE THE TARGET

so every selection after the first was made inside a process that had already read real target
outcomes. That is a rolling disclosure, not a freeze, and no wrapper discipline inside a single
process can repair it.

REPLACED BY TWO PHYSICALLY SEPARATE PROCESSES:

    src/research/hypothesis_v8c/select_freeze.py   PROCESS 1 -- selects the whole cohort,
                                                   writes a durable hashed freeze, EXITS,
                                                   and never imports a scorer
    src/research/hypothesis_v8c/score_frozen.py    PROCESS 2 -- verifies that hash, then scores

    research/hypothesis_engine/_run_v8c_select.py  driver for process 1
    research/hypothesis_engine/_run_v8c_score.py   driver for process 2

See V8C_OUTCOME_SEAL_SPEC.md.

The body is deliberately removed rather than left importable. Keeping a working single-process
path around is how a sealed experiment quietly gets run through the unsealed one; the import
error is the point.
"""
from __future__ import annotations

EXPERIMENT_VERSION = "v8c_experiment_SUPERSEDED"

SUPERSEDED_BY = ("src.research.hypothesis_v8c.select_freeze",
                 "src.research.hypothesis_v8c.score_frozen")


class SupersededByProcessSplit(RuntimeError):
    """Raised on any attempt to use the single-process experiment path."""


def _refuse(*_a, **_kw):
    raise SupersededByProcessSplit(
        "hypothesis_v8c.experiment is SUPERSEDED: it selected and scored within one process, "
        "which is the P0 outcome-seal defect. Use select_freeze.select_cohort (process 1) "
        "then score_frozen.score_frozen (process 2). See V8C_OUTCOME_SEAL_SPEC.md.")


run_experiment = _refuse
compute_reachability = _refuse
gate_verdict = _refuse
default_s_selector = _refuse


def version_stamp() -> dict:
    return {"experiment_version": EXPERIMENT_VERSION,
            "status": "SUPERSEDED",
            "defect": "P0-OUTCOME-SEAL: selected and scored within one process",
            "superseded_by": list(SUPERSEDED_BY),
            "callable": False}
