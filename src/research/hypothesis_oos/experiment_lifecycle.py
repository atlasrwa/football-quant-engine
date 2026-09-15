"""Lifecycle-aware artifact invariants for experiment directories (`experiment_lifecycle_v1`).

WHY THIS MODULE EXISTS
----------------------
The original V6 pre-spend guard asserted, flatly, "execution artifacts must not exist". That
was a CORRECT invariant for an experiment that had never been authorized, and a WRONG
invariant for one that has completed an authorized run. After V6 was authorized and executed,
the flat assertion became historically false and three tests went red -- not because anything
regressed, but because the invariant did not know the experiment's lifecycle phase.

This module replaces the flat rule with a lifecycle-aware one. The lifecycle PHASE is read
from the experiment's own immutable execution-state artifact, never guessed:

  * NEVER_EXECUTED  -- no execution-state artifact, or one that does not say a run occurred.
                       Execution artifacts (raw responses, scores, ledger) MUST NOT exist.
                       This preserves the original anti-premature-execution protection for
                       every future/unexecuted experiment (e.g. V6.1 before authorization).

  * COMPLETE / STOPPED -- the immutable execution-state artifact records a finished run.
                       Execution artifacts MUST exist, the expected set MUST be complete, and
                       every preserved hash MUST match. A COMPLETE experiment whose artifacts
                       vanished or whose hashes drifted is a CORRUPTED history, which FAILS.

The scientific/frozen artifacts (evaluator, preregistration, packets) are never mutated by
this check; it only validates the RELATIONSHIP between the recorded phase and the filesystem.

ZERO SPEND. Pure filesystem + hashing. No network, no model.
"""
from __future__ import annotations

import hashlib
import json
import os

LIFECYCLE_VERSION = "experiment_lifecycle_v1"

# Lifecycle phases. Only these are recognised; anything else is treated as NEVER_EXECUTED
# for the purpose of the artifact invariant (a run that never reached a terminal recorded
# state has, by definition, no legitimate execution artifacts).
PHASE_NEVER_EXECUTED = "NEVER_EXECUTED"
PHASE_COMPLETE = "COMPLETE"
PHASE_STOPPED = "STOPPED"
_EXECUTED_PHASES = (PHASE_COMPLETE, PHASE_STOPPED)

# Artifacts that only a real authorized run produces. Their presence before execution is a
# premature-execution violation; their absence after a recorded run is a corrupted history.
MODEL_OBSERVATION_ARTIFACTS = ("scores.json", "raw", "execution_summary.json",
                               "execution_log.jsonl")


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def read_phase(execution_states_path: str) -> str:
    """The recorded lifecycle phase, read from the experiment's immutable state artifact.

    Returns NEVER_EXECUTED when the artifact is absent or does not record a finished run.
    Never infers a phase from the filesystem -- the filesystem is what we are validating.
    """
    if not os.path.exists(execution_states_path):
        return PHASE_NEVER_EXECUTED
    try:
        doc = json.load(open(execution_states_path))
    except (ValueError, OSError):
        return PHASE_NEVER_EXECUTED
    status = doc.get("execution_status")
    if status in _EXECUTED_PHASES:
        return status
    # A state file that exists but records neither COMPLETE nor STOPPED (e.g. a design-phase
    # states file with no execution_status) is NOT an executed run.
    return PHASE_NEVER_EXECUTED


def validate_artifacts(exec_dir: str, *, phase: str,
                       preserved_hashes: dict | None = None) -> dict:
    """Validate the execution directory against the recorded lifecycle phase.

    Returns {"ok": bool, "problems": [...], "phase": phase}. Pure; raises nothing on a
    normal filesystem. `preserved_hashes` maps artifact basename -> expected SHA-256 and is
    checked only for executed phases.
    """
    problems = []
    exec_exists = os.path.isdir(exec_dir)

    if phase == PHASE_NEVER_EXECUTED:
        # nothing an authorized run would produce may exist.
        if exec_exists:
            for name in MODEL_OBSERVATION_ARTIFACTS:
                p = os.path.join(exec_dir, name)
                if os.path.exists(p):
                    problems.append(f"NEVER_EXECUTED but model-observation artifact exists: "
                                    f"{name}")
        return {"ok": not problems, "problems": problems, "phase": phase,
                "exec_dir_exists": exec_exists}

    # executed phase: the artifacts MUST exist and be complete + hash-correct.
    if not exec_exists:
        problems.append(f"{phase} but execution directory missing: {exec_dir}")
        return {"ok": False, "problems": problems, "phase": phase, "exec_dir_exists": False}

    for name in ("scores.json",):     # the minimum a finished run must have produced
        if not os.path.exists(os.path.join(exec_dir, name)):
            problems.append(f"{phase} but required artifact missing: {name}")

    for name, want in (preserved_hashes or {}).items():
        p = os.path.join(exec_dir, name)
        if not os.path.exists(p):
            problems.append(f"{phase} but preserved artifact missing: {name}")
            continue
        got = _sha_file(p)
        if got != want:
            problems.append(f"{phase} artifact hash mismatch for {name}: "
                            f"{got[:12]} != preserved {want[:12]}")
    return {"ok": not problems, "problems": problems, "phase": phase,
            "exec_dir_exists": True}


def validate_experiment(exec_dir: str, execution_states_path: str, *,
                        preserved_hashes: dict | None = None) -> dict:
    """Convenience: read the phase, then validate the artifacts against it."""
    phase = read_phase(execution_states_path)
    return validate_artifacts(exec_dir, phase=phase, preserved_hashes=preserved_hashes)


def version_stamp() -> dict:
    return {"lifecycle_version": LIFECYCLE_VERSION,
            "phases": [PHASE_NEVER_EXECUTED, PHASE_COMPLETE, PHASE_STOPPED],
            "model_observation_artifacts": list(MODEL_OBSERVATION_ARTIFACTS),
            "phase_read_from": "immutable execution-state artifact, never the filesystem"}
