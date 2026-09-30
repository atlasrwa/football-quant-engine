from pathlib import Path

from research.evidence_v32.market_audit_v322 import (
    choose_snapshot, parse_observed, quote_for,
)

def test_filename_timestamp_is_explicit_utc():
    path=Path("research_odds_mt_1_bet365_20260909T070059908653Z-123.json")
    ts=parse_observed(path)
    assert ts is not None

def test_no_vig_goal_quote_uses_both_sides():
    snap={"markets":{"total_goals":{"2.5":{
        "over":{"last_seen":"2.000"},
        "under":{"last_seen":"2.000"},
    }}}}
    quote=quote_for(snap,"total>2.5")
    assert quote is not None
    assert abs(quote["p_market"]-.5)<1e-12

def test_latest_eligible_snapshot_is_selected():
    kickoff=100_000.0
    rows=[
        {"observed_at":kickoff-20*3600,"markets":{
            "btts":{"yes":{"last_seen":"2.0"},"no":{"last_seen":"2.0"}}}},
        {"observed_at":kickoff-17*3600,"markets":{
            "btts":{"yes":{"last_seen":"1.8"},"no":{"last_seen":"2.2"}}}},
    ]
    window={"seconds_before_kickoff_min":16*3600,
            "seconds_before_kickoff_max":24*3600}
    chosen=choose_snapshot(rows,kickoff,window,"BTTS")
    assert chosen is not None
    assert chosen[0]["observed_at"]==kickoff-17*3600
