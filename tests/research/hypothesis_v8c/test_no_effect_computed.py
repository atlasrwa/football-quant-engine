"""REPAIR 3 (composed): the development path must not COMPUTE an effect, not merely withhold it.

The test replaces `aggregate.endpoint`, `aggregate.per_fixture_endpoints` and the estimator
with functions that RAISE. The development rehearsal must still complete through the real
entry points; the confirmatory path must still reach them.
"""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import aggregate as AG
from src.research.hypothesis_v8c import score_frozen as SFZ
from src.research.hypothesis_v8c import structural_diagnostics as SD


def _records():
    return [
        {"fixture_id": "mt_1", "arm": "S", "hypothesis_id": "s1", "status": "SCORE_OK",
         "score": 1.5},
        {"fixture_id": "mt_1", "arm": "R", "hypothesis_id": "r1", "status": "SCORE_OK",
         "score": 0.5},
        {"fixture_id": "mt_1", "arm": "H", "hypothesis_id": "h1", "status": "SCORE_OK",
         "score": 0.9},
        {"fixture_id": "mt_2", "arm": "S", "hypothesis_id": "s2", "status": "SCORE_REFUSED",
         "score": None},
        {"fixture_id": "mt_2", "arm": "R", "hypothesis_id": "r2", "status": "SCORE_OK",
         "score": 0.2},
    ]


PAIRS = {"mt_1": [{"s_id": "s1", "r_id": "r1", "tier": "EXACT", "status": "MATCHED"}],
         "mt_2": [{"s_id": "s2", "r_id": "r2", "tier": "EXACT", "status": "MATCHED"}]}
BLOCKS = {"mt_1": "block_000", "mt_2": "block_000"}


def test_diagnostics_never_touch_a_score_value(monkeypatch):
    """Effect aggregation and inference are replaced by raising stubs."""
    def boom(*a, **k):
        raise AssertionError("effect computation was reached from the development path")

    monkeypatch.setattr(AG, "endpoint", boom)
    monkeypatch.setattr(AG, "per_fixture_endpoints", boom)
    from src.research.hypothesis_v71 import estimator as EST
    monkeypatch.setattr(EST, "small_cluster_inference", boom)

    out = SD.structural_diagnostics(_records(), ["mt_1", "mt_2"], PAIRS, BLOCKS)
    assert out["reads_score_values"] is False
    assert out["arm_score_ok"] == {"S": 1, "R": 2, "H": 1}
    assert out["n_pairs_surviving_total"] == 1, "only mt_1's pair has both arms SCORE_OK"
    assert out["n_pairs_frozen_total"] == 2


def test_a_score_value_read_raises_rather_than_silently_working():
    stripped = SD.strip_scores(_records())
    val = stripped[0]["score"]
    with pytest.raises(SD.ScoreValueRead):
        float(val)
    with pytest.raises(SD.ScoreValueRead):
        _ = val - 1


def test_pair_retention_is_decided_by_status_not_by_score():
    out = SD.structural_diagnostics(_records(), ["mt_1", "mt_2"], PAIRS, BLOCKS)
    surviving = {f["fixture_id"]: f["n_pairs_surviving"] for f in out["per_fixture"]}
    assert surviving == {"mt_1": 1, "mt_2": 0}


def test_inference_eligibility_is_counts_only():
    out = SD.structural_diagnostics(_records(), ["mt_1", "mt_2"], PAIRS, BLOCKS)
    el = out["inference_eligibility"]
    assert el["min_paired_per_block"] == AG.MIN_PAIRED_PER_BLOCK
    assert el["min_qualifying_blocks"] == AG.MIN_QUALIFYING_BLOCKS
    assert "would_inference_be_available" in el
    for forbidden in ("mean", "diff", "p_value", "statistic", "direction"):
        assert not any(forbidden in k for k in el), f"{forbidden} leaked into eligibility"


def test_development_branch_returns_before_effect_aggregation():
    import inspect
    src = inspect.getsource(SFZ.score_frozen)
    assert src.index("DEVELOPMENT_DIAGNOSTICS:") < src.index("AG.per_fixture_endpoints")


def test_confirmatory_path_still_reaches_effect_aggregation():
    """The repair must not quietly disable the confirmatory endpoint."""
    import inspect
    src = inspect.getsource(SFZ.score_frozen)
    assert "AG.endpoint(" in src and "AG.per_fixture_endpoints(" in src


def test_development_mode_does_not_bypass_any_integrity_check():
    import inspect
    src = inspect.getsource(SFZ.score_frozen)
    dev = src.index("DEVELOPMENT_DIAGNOSTICS:")
    for gate in ("ANCHOR.verify_for_scoring", "load_and_verify_freeze",
                 "verify_fixture_binding", "verify_inference_blocks"):
        assert src.index(gate) < dev, f"{gate} runs after the development branch"


def test_confirmatory_definitions_unchanged():
    v = SD.version_stamp()
    assert v["confirmatory_definitions_unchanged"] is True
    assert v["shares_validation_and_scoring_machinery"] is True
