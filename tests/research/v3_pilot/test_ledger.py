import json
from pathlib import Path

from src.research.v3_pilot import ledger

def _write_legacy(path: Path):
    rows = []
    for i in range(1, 21):
        row = {
            "event_type": "HYPOTHESIS_DECLARED",
            "hypothesis_id": f"legacy-{i}",
            "test_number": i,
        }
        if i >= 12:
            row["counts_toward_40"] = True
        rows.append(row)
    for i in range(1, 12):
        rows.append({
            "event_type": "SETTLEMENT_RECORDED",
            "hypothesis_id": f"legacy-{i}",
            "result": "WIN" if i <= 7 else "LOSS",
        })
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

def test_bridge_preserves_legacy_twenty_and_appends_21(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    led = repo / "research/lean_hypothesis_ledger/ledger_v1.jsonl"
    evdir = repo / "research/lean_hypothesis_ledger/v3_evidence"
    led.parent.mkdir(parents=True)
    _write_legacy(led)
    monkeypatch.setattr(ledger, "LEAN_LEDGER_REPO", repo)
    monkeypatch.setattr(ledger, "LEAN_LEDGER", led)
    monkeypatch.setattr(ledger, "EVIDENCE_DIR", evdir)

    status = ledger.pilot_status()
    assert status == {
        "declared": 20, "wins": 7, "losses": 4,
        "pushes": 0, "pending": 9, "remaining": 20,
    }

    signal = {
        "hypothesis_id": "v3-test",
        "fixture": "A vs B",
        "fixture_id": "mt_1",
        "market_family": "goals",
        "market": "Bet365_total_goals",
        "side": "OVER",
        "line": 2.5,
        "price_decimal": 2.0,
        "opposite_price_decimal": 1.8,
        "kickoff_utc": "2026-10-01T12:00:00Z",
        "prediction_observed_at_utc": "2026-09-30T12:00:00Z",
        "market_observed_at_utc": "2026-09-30T12:01:00Z",
        "cluster_id": "mt_1:goals",
        "model": {"version": "v", "distribution_hash": "h", "p_selected": .65, "p_over": .65},
        "market_benchmark": {
            "no_vig_selected": .52,
            "model_minus_no_vig": .13,
            "raw_break_even_selected": .5,
        },
    }
    event = ledger.append_declaration(signal, {"x": 1})
    assert event is not None
    assert event["test_number"] == 21
    assert event["v3_prev_hash"] is not None
    assert len(event["v3_event_hash"]) == 64
    assert ledger.pilot_status()["declared"] == 21
    evidence = evdir / "v3-test.json"
    assert evidence.exists()
