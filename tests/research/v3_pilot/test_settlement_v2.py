import json

from src.research.v3_pilot import ledger
from src.research.v3_pilot.settlement_v2 import (
    COMPLETION_BUFFER_SECONDS,
    MIN_STABLE_SPAN_SECONDS,
    cached_score_evidence,
    stable_regulation_score,
)

def _detail(home, away):
    return {
        "data": {
            "status": "finished",
            "score": {
                "home": home,
                "away": away,
                "regulation": {"home": home, "away": away},
                "went_to_extra_time": False,
                "went_to_penalties": False,
            },
        }
    }

def _write(cache, observed_at, ph, home, away):
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{int(observed_at)}_{ph}.json").write_text(
        json.dumps(_detail(home, away))
    )

def test_single_finished_zero_zero_snapshot_never_settles(tmp_path):
    kickoff = 1_000_000.0
    cache = tmp_path / "detail"
    _write(cache, kickoff + COMPLETION_BUFFER_SECONDS + 60, "bad0", 0, 0)
    evidence = cached_score_evidence(cache, kickoff_ts=kickoff)
    assert len(evidence) == 1
    assert stable_regulation_score(evidence) is None

def test_transient_zero_zero_is_excluded_and_stable_2_1_wins(tmp_path):
    kickoff = 1_000_000.0
    cache = tmp_path / "detail"
    _write(cache, kickoff + 2 * 3600, "early00", 0, 0)
    t1 = kickoff + COMPLETION_BUFFER_SECONDS + 60
    t2 = t1 + MIN_STABLE_SPAN_SECONDS + 1
    _write(cache, t1, "good21a", 2, 1)
    _write(cache, t2, "good21b", 2, 1)
    evidence = cached_score_evidence(cache, kickoff_ts=kickoff)
    assert [(x.home, x.away) for x in evidence] == [(2, 1), (2, 1)]
    stable = stable_regulation_score(evidence)
    assert stable is not None
    assert (stable[1].home, stable[1].away) == (2, 1)

def test_invalidation_removes_wrong_settlement_from_resolved_view():
    rows = [
        {"event_type": "SETTLEMENT_RECORDED", "hypothesis_id": "h1", "result": "WIN", "settled_value": 0},
        {"event_type": "SETTLEMENT_INVALIDATED", "hypothesis_id": "h1", "reason": "provider transient score"},
    ]
    assert ledger.settlements(rows) == {}

def test_corrected_settlement_after_invalidation_is_authoritative():
    rows = [
        {"event_type": "SETTLEMENT_RECORDED", "hypothesis_id": "h1", "result": "WIN", "settled_value": 0},
        {"event_type": "SETTLEMENT_INVALIDATED", "hypothesis_id": "h1"},
        {"event_type": "SETTLEMENT_RECORDED", "hypothesis_id": "h1", "result": "WIN", "settled_value": 3},
    ]
    out = ledger.settlements(rows)
    assert out["h1"]["settled_value"] == 3
