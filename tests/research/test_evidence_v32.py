from pathlib import Path

import numpy as np
import pytest

from src.research.evidence_v32.modeling import (
    CountRegressor, UnsupportedFeatures, joint_distribution, event_probabilities,
)
from src.research.evidence_v32.settlement import (
    ScoreEvidence, cached_score_evidence, settle_binary, stable_regulation_score,
)

def test_settlement_requires_stable_post_buffer_score(tmp_path: Path):
    kickoff=1_000_000.0
    # Pre-buffer evidence is never eligible.
    assert cached_score_evidence(tmp_path,kickoff_ts=kickoff)==[]
    rows=[
        ScoreEvidence(0,0,kickoff+4*3600+10,"a"),
        ScoreEvidence(2,2,kickoff+4*3600+400,"b"),
    ]
    assert stable_regulation_score(rows) is None
    rows.append(ScoreEvidence(2,2,kickoff+4*3600+800,"c"))
    stable=stable_regulation_score(rows)
    assert stable is not None and (stable.home,stable.away)==(2,2)

def test_under_35_two_two_is_loss():
    result,value,unit=settle_binary(
        market_family="goals",market="Bet365_total_goals",side="UNDER",
        line=3.5,home=2,away=2)
    assert (result,value,unit)==("LOSS",4,"total_goals")
def test_team_goal_settlement_is_target_specific():
    assert settle_binary(
        market_family="goals",market="home_team_goals",side="OVER",
        line=1.5,home=2,away=0)[0]=="WIN"
    assert settle_binary(
        market_family="goals",market="away_team_goals",side="OVER",
        line=1.5,home=2,away=0)[0]=="LOSS"

def test_all_missing_feature_column_rejected():
    x=np.array([[1.0,np.nan],[2.0,np.nan],[3.0,np.nan]])
    with pytest.raises(UnsupportedFeatures,match="all-missing"):
        CountRegressor(x,[0,1,2])

def test_joint_probabilities_are_coherent():
    joint=joint_distribution(1.4,1.1,"poisson",max_count=20)
    assert abs(float(joint.sum())-1.0)<1e-10
    p=event_probabilities(joint,"goals")
    assert 0<p["BTTS"]<1
    assert p["total>3.5"]<=p["total>2.5"]

from src.research.evidence_v32.modeling import (
    STAT_PATHS, _apply_elo_events, _venue, _vector, paired_gain,
)

def test_venue_is_explicit_and_unknown_stays_missing():
    assert _venue({"context":{"is_neutral":False}},"home")==1.0
    assert _venue({"context":{"is_neutral":False}},"away")==-1.0
    assert _venue({"context":{"is_neutral":True}},"home")==0.0
    assert _venue({"context":{"is_neutral":None}},"home") is None
    p={"own_goals":1.0,"opp_goals":1.1}
    q={"own_goals":1.2,"opp_goals":1.3}
    vector=_vector(p,q,"goals",(),0.25,1.0,False)
    assert vector[-2:]==[0.25,1.0]

def test_elo_result_waits_for_completion_buffer():
    ratings={}
    pending=[{"ts":1000.0,"home_id":"h","away_id":"a",
              "home_goals":2,"away_goals":0,"is_neutral":False}]
    _apply_elo_events(ratings,pending,1000.0+4*3600)
    assert ratings=={} and len(pending)==1
    _apply_elo_events(ratings,pending,1000.0+4*3600+1)
    assert "h" in ratings and "a" in ratings and not pending

def test_week_block_uncertainty_is_registered_and_deterministic():
    base=[]; candidate=[]
    for i,(date,b,c) in enumerate([
        ("2026-01-05",0.70,0.60),("2026-01-06",0.80,0.70),
        ("2026-01-13",0.50,0.55),("2026-01-14",0.60,0.50),
    ]):
        common={"match_id":str(i),"target":"BTTS","fold":"F","date":date}
        base.append({**common,"loss":b})
        candidate.append({**common,"loss":c})
    first=paired_gain(base,candidate)
    second=paired_gain(base,candidate)
    assert first==second
    assert first["week_blocks"]==2
    assert len(first["descriptive_week_block_95_interval"])==2

def test_xg_is_bound_to_exact_provider_path():
    assert STAT_PATHS["xg"]=="overview.expected_goals"
