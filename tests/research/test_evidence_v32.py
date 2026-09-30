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
