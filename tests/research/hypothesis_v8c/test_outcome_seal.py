"""P0 OUTCOME-SEAL + P1 BLIND-SEAL. The hardest invariants in V8C.

No conditional assertions anywhere: a known-good case asserts the exact expected state.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from src.research.hypothesis_v8b2 import scorer as V8B2SC
from src.research.hypothesis_v8c import blind_index as BI
from src.research.hypothesis_v8c import cohort_stats as CS
from src.research.hypothesis_v8c import select_freeze as SF

from .conftest import GRAMMAR_KW


# ---- the process seal ---------------------------------------------------------------------
def test_pre_t_import_set_loads_no_scorer():
    """PROCESS 1's entire import set must not pull in any scoring module.

    Run in a SUBPROCESS: the pytest interpreter has scorers loaded from other tests, so an
    in-process check would be meaningless.
    """
    code = (
        "import sys;"
        "from src.research.hypothesis_v8c import select_freeze, universe, controls, pre_t,"
        " grammar, pit_context, blind_index, cohort_stats;"
        "bad=sorted(m for m in sys.modules if 'scorer' in m);"
        "print(repr(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd="/home/ubuntu",
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]", (
        f"PRE-T import set loaded scoring modules: {out.stdout.strip()}")


def test_seal_assertion_raises_when_a_scorer_is_loaded():
    from src.research.hypothesis_v8c import scorer  # noqa: F401 -- deliberately loaded
    with pytest.raises(SF.OutcomeSealViolation):
        SF.assert_no_scorer_loaded()


def test_zero_variance_floor_matches_frozen_scorer():
    """cohort_stats states the floor literally to keep the scorer out of the pre-T process;
    this test is what stops that literal from drifting."""
    assert CS.ZERO_VARIANCE_FLOOR == V8B2SC.ZERO_VARIANCE_FLOOR


def test_two_process_seal_end_to_end(tmp_path):
    """THE P0 TEST: spawn process 1, let it EXIT, then spawn process 2.

    This is the real guarantee -- an operating-system fact, not a code-review claim. Process 1
    selects the whole cohort and terminates; only then does process 2 open any outcome.
    """
    freeze = tmp_path / "freeze.json"
    results = tmp_path / "results.json"
    p1 = subprocess.run([sys.executable, "research/hypothesis_engine/_run_v8c_select.py",
                         str(freeze), "golden"], cwd="/home/ubuntu",
                        capture_output=True, text=True)
    assert p1.returncode == 0, p1.stderr
    assert "TARGET_OUTCOMES_VIEWED=False" in p1.stdout
    assert "SCORER_LOADED=False" in p1.stdout
    assert freeze.exists(), "process 1 must leave a durable freeze"

    # BETWEEN the two processes: anchor the freeze externally and commit it. Process 2 will
    # not start without a pinned ANCHOR_COMMIT, which is the point of the anchor.
    from ._anchor_support import anchor_freeze
    akw = anchor_freeze(tmp_path, str(freeze))

    p2 = subprocess.run([sys.executable, "research/hypothesis_engine/_run_v8c_score.py",
                         str(freeze), str(results), "golden",
                         akw["anchor_commit"], akw["anchor_repo_relpath"], akw["repo_root"]],
                        cwd="/home/ubuntu", capture_output=True, text=True)
    assert p2.returncode == 0, p2.stderr
    assert "FREEZE_HASH_VERIFIED=" in p2.stdout
    assert "ANCHOR_VERIFIED=True" in p2.stdout
    assert "EXECUTING_CODE_VERIFIED=True" in p2.stdout
    assert "BLOCKS_VALIDATED_BEFORE_TARGET_READ=True" in p2.stdout
    frozen_hash = [l for l in p1.stdout.splitlines() if l.startswith("FREEZE_HASH=")][0]
    assert frozen_hash.split("=", 1)[1] in p2.stdout


def test_freeze_is_written_before_any_scoring_and_hash_verifies(golden_env, tmp_path):
    payload = SF.select_cohort(golden_env.index, [golden_env.target_pos],
                               capability=golden_env.capability, k=3,
                               fixture_ids=[golden_env.target_fixture_id],
                               grammar_kwargs=GRAMMAR_KW, enforce_seal=False)
    assert payload["reads_target_outcome"] is False
    assert payload["totals"]["target_outcomes_viewed"] is False
    p = tmp_path / "freeze.json"
    SF.write_freeze(payload, str(p))
    from src.research.hypothesis_v8c import score_frozen as SFZ
    from ._anchor_support import anchor_freeze
    akw = anchor_freeze(tmp_path, str(p), fixture_ids=payload["fixture_ids_ordered"])
    verified = SFZ.load_and_verify_freeze(str(p), receipt_path=akw["receipt_path"])
    assert verified["freeze_hash"] == payload["freeze_hash"]


def test_scoring_refuses_a_tampered_freeze(golden_env, tmp_path):
    """Changing ONE selection after the freeze must stop scoring dead."""
    payload = SF.select_cohort(golden_env.index, [golden_env.target_pos],
                               capability=golden_env.capability, k=3,
                               fixture_ids=[golden_env.target_fixture_id],
                               grammar_kwargs=GRAMMAR_KW, enforce_seal=False)
    p = tmp_path / "freeze.json"
    SF.write_freeze(payload, str(p))
    tampered = json.load(open(p))
    tampered["selections"][0]["S"] = ["mt_TAMPERED_ID"]
    json.dump(tampered, open(p, "w"), indent=1, default=str, sort_keys=True)

    from src.research.hypothesis_v8c import score_frozen as SFZ
    from src.research.hypothesis_v8c import receipt as RCPT
    from ._anchor_support import anchor_freeze
    # The receipt is built over the TAMPERED bytes on purpose: the point is that the freeze's
    # own self-hash no longer matches its payload, which `load_and_verify_freeze` must catch.
    akw = anchor_freeze(tmp_path, str(p), fixture_ids=tampered["fixture_ids_ordered"])
    with pytest.raises((SFZ.FreezeIntegrityError, RCPT.ReceiptError)):
        SFZ.load_and_verify_freeze(str(p), receipt_path=akw["receipt_path"])


# ---- the blind index ----------------------------------------------------------------------
def test_blind_index_seals_every_documented_accessor(golden_env):
    """The V1 hole: .vals and .recs were passthroughs that handed over the outcome."""
    tp = golden_env.target_pos
    b = BI.TargetBlindIndex(golden_env.index, [tp])

    assert b.team_value(tp, "tm_subject", "goals", "FOR") is None
    assert b.vals["goals"][tp] is None
    rec = b.recs[tp]
    assert rec.base == {} and rec.rich == {} and rec.extra == {}
    assert rec.sealed is True
    # metadata the compiler legitimately needs survives
    assert rec.competition and rec.kickoff_unix and rec.home_id and rec.away_id
    # and an UNSEALED position is untouched
    assert golden_env.index.vals["goals"][0] is not None
    assert b.vals["goals"][0] == golden_env.index.vals["goals"][0]
    assert b.audit_report()["target_outcomes_viewed"] is False


def test_blind_index_strict_mode_raises_on_every_route(golden_env):
    tp = golden_env.target_pos
    b = BI.TargetBlindIndex(golden_env.index, [tp], strict=True)
    with pytest.raises(BI.TargetOutcomeReadAttempt):
        b.team_value(tp, "tm_subject", "goals", "FOR")
    with pytest.raises(BI.TargetOutcomeReadAttempt):
        _ = b.vals["goals"][tp]
    with pytest.raises(BI.TargetOutcomeReadAttempt):
        _ = b.recs[tp]
