from types import SimpleNamespace
import numpy as np
from src.research.target_aware_market_panel import predictive_v123 as V

def test_strong_control_counts_are_fixed():
    assert len(V.strong_specs("GOALS")) == 144
    assert len(V.strong_specs("CORNERS")) == 120
    assert len(V.strong_specs("TEAM_TOTALS")) == 156
    assert len(V.strong_specs("BOOKINGS")) == 132

class R:
    def __init__(self,v,venue="HOME"): self.v=v; self.venue=venue
    def get(self,m,p,period): return self.v

class H:
    def __init__(self,vals): self.rows=[R(v) for v in vals]
    def prior(self,team,before,venue=None):
        return [r for r in self.rows if venue is None or r.venue==venue]

def test_multiseason_w20_and_ewma_use_prior_rows():
    h=H(list(range(1,21)))
    fx={"home_team_id":"h","away_team_id":"a","kickoff":100}
    s={"side":"HOME","metric":"goals","perspective":"FOR","period":"FULL_MATCH","window":"MS_W20"}
    assert V.strong_value(h,fx,s) == 10.5
    s=dict(s,window="MS_EWMA_H10")
    got=V.strong_value(h,fx,s)
    assert np.isfinite(got) and got > 10.5

def test_strong_windows_are_outcome_blind_constants():
    assert V.MULTISEASON_WINDOWS == ("MS_W20","MS_VENUE_W10","MS_EWMA_H10")
    assert V.EWMA_HALF_LIFE_MATCHES == 10.0
    assert V.MIN_MS_OBS == 10
