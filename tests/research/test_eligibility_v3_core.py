"""Tests for the generation-neutral V3 eligibility extraction (`eligibility_v3_core`).

The 4.5 arm had no eligibility stage while the 4.6 arm did. Rather than write 4.5-specific
decision logic -- which would let one generation be judged by a bar the other never faced --
the 4.6 implementation was extracted verbatim into a shared core and both arms became thin
wiring, exactly as `controls_v3_core` did for the control battery.

Covers:
  * the refactor reproduces the FROZEN 4.6 eligibility + mechanism-sensitivity artifacts
    exactly (the required "prove equivalence before adopting the refactor");
  * frozen 4.6 artifacts are never written by any of this;
  * 4.5/4.6 namespace + cache isolation;
  * the fail-closed gate: PENDING_SURROGATE must NOT survive a failed identity gate, and the
    pre-gate class is preserved for audit rather than silently overwritten;
  * thresholds are imported from `eligibility`, never redefined per generation;
  * eligibility makes ZERO Bedrock calls.

Run: .venv/bin/python -m pytest tests/research/test_eligibility_v3_core.py -q
"""
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import eligibility as EL
from src.research.llm_matchup.hardening import eligibility_v3_core as ECORE
from src.research.llm_matchup.hardening import eligibility_v3_sonnet45 as E45
from src.research.llm_matchup.hardening import eligibility_v3_sonnet46 as E46


def _norm(o):
    return json.loads(json.dumps(o, sort_keys=True, default=str))


def _frozen_46_hashes():
    import hashlib
    d = E46.OUT
    return {f: hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest()
            for f in sorted(os.listdir(d)) if f.endswith((".json", ".csv", ".jsonl"))}


# --------------------------------------------------------------------------------------
# 1. Equivalence: the shared core must reproduce the frozen 4.6 result exactly.
# --------------------------------------------------------------------------------------

@pytest.mark.slow
def test_core_reproduces_frozen_sonnet46_eligibility_exactly():
    if not os.path.exists(E46.ELIG_JSON):
        pytest.skip("frozen 4.6 eligibility artifact not present")
    before = _frozen_46_hashes()
    produced = E46.run(k=3, persist=False)          # persist=False: never writes frozen files
    frozen = json.load(open(E46.ELIG_JSON))
    assert _norm(produced) == _norm(frozen)
    assert _frozen_46_hashes() == before, "frozen 4.6 artifacts must not be written"


@pytest.mark.slow
def test_core_reproduces_frozen_sonnet46_mechanism_sensitivity_exactly():
    if not os.path.exists(E46.SENS_JSON):
        pytest.skip("frozen 4.6 sensitivity artifact not present")
    before = _frozen_46_hashes()
    produced = E46.per_mechanism_sensitivity(k=3, persist=False)
    assert _norm(produced) == _norm(json.load(open(E46.SENS_JSON)))
    assert _frozen_46_hashes() == before


# --------------------------------------------------------------------------------------
# 2. Namespace isolation between the two generations.
# --------------------------------------------------------------------------------------

def test_generation_namespaces_are_isolated():
    c45, c46 = E45._cfg(), E46._cfg()
    assert c45.out_dir != c46.out_dir
    assert c45.cache_dir != c46.cache_dir
    for a, b in ((c45.elig_json, c46.elig_json), (c45.elig_csv, c46.elig_csv),
                 (c45.sens_json, c46.sens_json), (c45.controls_path, c46.controls_path),
                 (c45.repeat_path, c46.repeat_path)):
        assert a != b
    assert "v3_sonnet46" not in c45.out_dir
    assert c45.gen.DEFAULT_BEDROCK_MODEL_ID != c46.gen.DEFAULT_BEDROCK_MODEL_ID


def test_sonnet45_never_writes_into_the_sonnet46_namespace():
    c45 = E45._cfg()
    for p in (c45.elig_json, c45.elig_csv, c45.sens_json, c45.out_dir):
        assert os.path.abspath(E46.OUT) not in os.path.abspath(p)


# --------------------------------------------------------------------------------------
# 3. Fail-closed gate semantics (shared, not per-generation).
# --------------------------------------------------------------------------------------

def test_pending_surrogate_cannot_survive_a_failed_identity_gate():
    """PENDING_SURROGATE means 'passed what we measured, surrogate unmeasured'. It is not one
    of the two class names the V2 gate knows about, so without the widened set it would slip
    through a FAILED generation gate and read as success."""
    assert "PENDING_SURROGATE" in ECORE.GATE_REJECTABLE_CLASSES
    rows = [{"mechanism": "m1", "eligibility": "PENDING_SURROGATE"},
            {"mechanism": "m2", "eligibility": "RESEARCH_ONLY_UNSTABLE"},
            {"mechanism": "m3", "eligibility": "INSUFFICIENT_COVERAGE"}]
    gate = {"phase_c_eligible_generation": False, "reason": "NOT_PHASE_C_ELIGIBLE: team=FAIL"}
    out = ECORE.apply_identity_gate(rows, gate)
    assert out[0]["eligibility"] == "REJECTED"
    assert out[0]["pre_gate_eligibility"] == "PENDING_SURROGATE"   # preserved for audit
    assert out[0]["reject_reason"] == gate["reason"]
    # classes that were not going to proceed anyway keep their real cause
    assert out[1]["eligibility"] == "RESEARCH_ONLY_UNSTABLE"
    assert out[2]["eligibility"] == "INSUFFICIENT_COVERAGE"


def test_passing_gate_leaves_rows_untouched():
    rows = [{"mechanism": "m1", "eligibility": "PENDING_SURROGATE"}]
    assert ECORE.apply_identity_gate(rows, {"phase_c_eligible_generation": True}) == rows


def test_thresholds_are_imported_not_redefined():
    for cfg in (E45._cfg(), E46._cfg()):
        assert ECORE.EL.MIN_COVERAGE is EL.MIN_COVERAGE
        assert ECORE.EL.MAX_IDENTITY_TRIP_RATE is EL.MAX_IDENTITY_TRIP_RATE
        assert ECORE.EL.MIN_N_FOR_IDENTITY_GATE is EL.MIN_N_FOR_IDENTITY_GATE
    assert not hasattr(ECORE, "MAX_IDENTITY_TRIP_RATE")


def test_no_v3_mechanism_can_be_phase_c_eligible_without_a_surrogate_ladder():
    """Fail-closed: the surrogate ladder was run for NEITHER V3 arm, so PHASE_C_ELIGIBLE must
    be unreachable in the V3 classifier."""
    src = open(ECORE.__file__).read()
    assert 'elig = "PHASE_C_ELIGIBLE"' not in src, "V3 classifier must never assign PHASE_C_ELIGIBLE"
    assert 'elig = "PENDING_SURROGATE"' in src
    # and prove it behaviourally, not just textually: a mechanism clearing every measured bar
    # lands on PENDING_SURROGATE, never PHASE_C_ELIGIBLE.
    cfg = E45._cfg()
    sig = {m: {"coverage": EL.MIN_COVERAGE + 1, "n_total": 10, "n_severe": 0, "n_stable": 10,
               "sensitivity_flag": "SENSITIVE_TO_EVIDENCE", "sensitivity_margin": 0.5}
           for m in ECORE.ONT.MECHANISMS}
    rows = ECORE.classify(cfg, sig)
    classes = {r["eligibility"] for r in rows}
    assert classes == {"PENDING_SURROGATE"}, classes
    assert all(r["surrogate_verdict"] == "NOT_RUN_FOR_SONNET45" for r in rows)


# --------------------------------------------------------------------------------------
# 4. Eligibility is offline.
# --------------------------------------------------------------------------------------

def test_eligibility_makes_no_bedrock_calls(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Bedrock call attempted during eligibility")
    monkeypatch.setattr(A4, "analyze_matchup_v4", boom)
    monkeypatch.setattr(ECORE.A4, "analyze_matchup_v4", boom)
    cfg = E45._cfg()
    sig = ECORE.collect_signals(cfg, None)
    rows = ECORE.classify(cfg, sig)
    gate = ECORE.identity_gate(cfg)
    ECORE.apply_identity_gate(rows, gate)


def test_sonnet45_identity_gate_reads_the_completed_frozen_controls():
    cfg = E45._cfg()
    if not os.path.exists(cfg.controls_path):
        pytest.skip("completed 4.5 controls artifact not present")
    gate = ECORE.identity_gate(cfg)
    assert gate["identity_gate_passed"] is False
    assert gate["phase_c_eligible_generation"] is False
    assert set(gate["failed_controls"]) == {"team_token_control", "competition_token_control",
                                            "formation_token_control"}
