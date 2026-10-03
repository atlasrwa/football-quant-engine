from src.research.layer4.calibrators import *

P=[.1,.2,.3,.4,.6,.7,.8,.9]*20
Y=[False,False,False,False,True,True,True,True]*20
W=[1.0]*len(P)


def _mono(cal):
    vals=[cal.transform(x,role='HOME',competition_ref='c1') for x in [0.05,.1,.2,.4,.6,.8,.95]]
    assert vals==sorted(vals)


def test_global_calibrators_are_monotone():
    for cal in (PlattGlobal.fit(P,Y,W,1e-6),BetaGlobal.fit(P,Y,W,1e-6),WeightedIsotonic.fit(P,Y,W)):
        _mono(cal)


def test_ridge_context_calibrator_monotone_within_context():
    roles=['HOME' if i%2==0 else 'AWAY' for i in range(len(P))]
    comps=['c1' if i%3 else 'c2' for i in range(len(P))]
    cal=RidgeContextPlatt.fit(P,Y,W,roles,comps,10.0,1e-6,True)
    _mono(cal)
    assert cal.slope>0


def test_roundtrip_specs_preserve_predictions():
    cals=[IdentityCalibrator(),PlattGlobal.fit(P,Y,W,1e-6),BetaGlobal.fit(P,Y,W,1e-6),WeightedIsotonic.fit(P,Y,W),RidgeContextPlatt.fit(P,Y,W,['HOME']*len(P),['c1']*len(P),10,1e-6,True)]
    for cal in cals:
        clone=calibrator_from_spec(cal.to_spec())
        assert abs(cal.transform(.37,role='HOME',competition_ref='c1')-clone.transform(.37,role='HOME',competition_ref='c1'))<1e-12


def test_weighted_metrics():
    assert weighted_log_loss([.5,.5],[0,1],[1,1])>0
    assert weighted_brier([0,1],[0,1],[1,1])==0
