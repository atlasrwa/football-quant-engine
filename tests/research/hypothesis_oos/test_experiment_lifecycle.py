"""Lifecycle-aware artifact-invariant tests (`experiment_lifecycle`). ZERO SPEND.

These replace the flat "execution artifacts must not exist" guard, which was correct only
before an experiment was authorized and became historically false after V6's authorized run.
The invariant is now phase-aware:

  * NEVER_EXECUTED  -> execution artifacts MUST NOT exist (anti-premature-execution).
  * COMPLETE/STOPPED -> execution artifacts MUST exist, be complete, and hash-match.

The seven required regression cases (Phase 1) are covered explicitly below, using a temp
directory so no real artifact is touched, plus live assertions on the real V6 (COMPLETE) and
V6.1 (pre-spend) directories.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import experiment_lifecycle as LC

ROOT = "/home/ubuntu"
V6_EXEC = f"{ROOT}/research/hypothesis_oos/out/v6/execution"
V6_STATES = f"{V6_EXEC}/V6_EXECUTION_STATES.json"
V6_1_OUT = f"{ROOT}/research/hypothesis_oos/out/v6_1"


def _preserved_v6_hashes() -> dict:
    """The hashes V6's own immutable execution-state artifact preserved."""
    doc = json.load(open(V6_STATES))
    return doc["artifact_hashes"]


def _write(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh)


# ---- live assertions on the real experiments -------------------------------------------
def test_live_v6_complete_with_valid_artifacts_passes():
    """Case 1: historical completed V6 + valid immutable artifacts -> PASS."""
    phase = LC.read_phase(V6_STATES)
    assert phase == LC.PHASE_COMPLETE
    res = LC.validate_experiment(V6_EXEC, V6_STATES,
                                 preserved_hashes=_preserved_v6_hashes())
    assert res["ok"], res["problems"]


def test_live_v6_1_lifecycle_aware_execution_state():
    """Case 4 (lifecycle-aware): the assertion depends on V6.1's RECORDED phase, never on a
    hard-coded assumption that V6.1 never executed.

    Before V6.1 was authorized/executed this asserted 'execution dir absent'. After the
    authorized V6.1 run it is COMPLETE, so its execution artifacts MUST exist and validate.
    The phase is read from the immutable execution state (execution_summary.json), never
    guessed -- exactly the lifecycle-aware rule that replaced the flat V6 guard.
    """
    v6_1_exec = f"{V6_1_OUT}/execution"
    v6_1_summary = f"{v6_1_exec}/execution_summary.json"
    phase = LC.read_phase(v6_1_summary)
    if phase in (LC.PHASE_COMPLETE, LC.PHASE_STOPPED):
        # V6.1 has executed: artifacts MUST exist (scores at minimum).
        assert os.path.exists(f"{v6_1_exec}/scores.json")
        res = LC.validate_experiment(v6_1_exec, v6_1_summary)
        assert res["ok"], res["problems"]
    else:
        # never-executed: execution dir must carry no model-observation artifacts.
        assert LC.read_phase(f"{V6_1_OUT}/does_not_exist.json") == LC.PHASE_NEVER_EXECUTED
        res = LC.validate_experiment(v6_1_exec, f"{V6_1_OUT}/does_not_exist.json")
        assert res["ok"], res["problems"]
        for name in LC.MODEL_OBSERVATION_ARTIFACTS:
            assert not os.path.exists(f"{V6_1_OUT}/{name}")
            assert not os.path.exists(f"{v6_1_exec}/{name}")


# ---- synthetic regression cases (temp dir; no real artifact touched) -------------------
def test_case2_complete_but_artifacts_missing_fails(tmp_path):
    """Case 2: historical COMPLETE but execution artifacts missing -> FAIL."""
    states = tmp_path / "states.json"
    _write(states, {"execution_status": "COMPLETE",
                    "artifact_hashes": {"scores.json": "a" * 64}})
    exec_dir = tmp_path / "execution"        # deliberately not created
    res = LC.validate_experiment(str(exec_dir), str(states),
                                 preserved_hashes={"scores.json": "a" * 64})
    assert not res["ok"]
    assert any("missing" in p for p in res["problems"])


def test_case3_artifact_hash_mutated_fails(tmp_path):
    """Case 3: historical V6 artifact hash mutated -> FAIL."""
    exec_dir = tmp_path / "execution"
    exec_dir.mkdir()
    (exec_dir / "scores.json").write_text('{"scores": "tampered"}')
    states = tmp_path / "states.json"
    _write(states, {"execution_status": "COMPLETE"})
    # preserved hash is for the ORIGINAL content, not the tampered file
    res = LC.validate_experiment(str(exec_dir), str(states),
                                 preserved_hashes={"scores.json": "b" * 64})
    assert not res["ok"]
    assert any("hash mismatch" in p for p in res["problems"])


def test_case5_pre_spend_with_model_response_fails(tmp_path):
    """Case 5: pre-spend (no executed state) + a generated model response present -> FAIL."""
    exec_dir = tmp_path / "execution"
    (exec_dir / "raw").mkdir(parents=True)
    (exec_dir / "raw" / "001.json").write_text('{"response": "generated"}')
    states = tmp_path / "no_state.json"      # never executed
    assert LC.read_phase(str(states)) == LC.PHASE_NEVER_EXECUTED
    res = LC.validate_experiment(str(exec_dir), str(states))
    assert not res["ok"]
    assert any("raw" in p for p in res["problems"])


def test_case5b_pre_spend_with_scores_fails(tmp_path):
    """Case 5 variant: pre-spend + scores.json present -> FAIL."""
    exec_dir = tmp_path / "execution"
    exec_dir.mkdir()
    (exec_dir / "scores.json").write_text("[]")
    res = LC.validate_experiment(str(exec_dir), str(tmp_path / "no_state.json"))
    assert not res["ok"]


def test_case6_pre_spend_ledger_pretending_calls_fails(tmp_path):
    """Case 6: pre-spend + execution ledger pretending calls occurred -> FAIL.

    A ledger/summary is a model-observation artifact; its presence without a recorded
    executed state is a premature-execution violation regardless of its contents.
    """
    exec_dir = tmp_path / "execution"
    exec_dir.mkdir()
    (exec_dir / "execution_summary.json").write_text(
        '{"n_charged": 36, "execution_status": "COMPLETE"}')
    # note: the STATE artifact does not exist, so the phase is NEVER_EXECUTED; a summary
    # file cannot promote the phase by itself.
    res = LC.validate_experiment(str(exec_dir), str(tmp_path / "missing_states.json"))
    assert not res["ok"]
    assert any("execution_summary.json" in p for p in res["problems"])


def test_case7_state_and_filesystem_disagree_fails(tmp_path):
    """Case 7: historical state and filesystem disagree -> FAIL.

    State says COMPLETE, filesystem has an execution dir but no scores.json.
    """
    exec_dir = tmp_path / "execution"
    exec_dir.mkdir()
    (exec_dir / "EVIDENCE_CHAIN_MANIFEST.json").write_text("{}")   # some file, not scores
    states = tmp_path / "states.json"
    _write(states, {"execution_status": "COMPLETE"})
    res = LC.validate_experiment(str(exec_dir), str(states))
    assert not res["ok"]
    assert any("scores.json" in p for p in res["problems"])


def test_phase_never_promoted_by_stray_summary(tmp_path):
    """A design-phase states file (no execution_status) is NEVER_EXECUTED, not COMPLETE."""
    states = tmp_path / "design_states.json"
    _write(states, {"states_version": "x", "spend_usd": 0.0})   # no execution_status
    assert LC.read_phase(str(states)) == LC.PHASE_NEVER_EXECUTED
