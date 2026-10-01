import json
from src.research.v37_future50.market import evaluate
from src.research.v37_future50.model import freeze

def test_thresholds_remain_frozen():
    assert evaluate(.61,2.0,2.0)['qualifies'] is True
    assert evaluate(.59,2.0,2.0)['qualifies'] is False

def test_v37_uses_v36_fold1_artifacts_without_refit():
    f=freeze(); assert f['goals_artifact']['fold']==1 and f['corners_artifact']['fold']==1
    assert f['refit_during_pilot'] is False
    assert abs(f['corner_shared_pressure_weight']-0.17504026385592653)<1e-15
