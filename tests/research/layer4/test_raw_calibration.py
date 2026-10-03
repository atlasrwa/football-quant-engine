import numpy as np
from src.research.layer4.raw_calibration import _percentile,_reference_thresholds


def test_percentile_is_monotone_and_bounded():
    x=np.asarray([1.,2.,3.,4.])
    vals=[_percentile(x,v) for v in (0.,1.,2.5,4.,5.)]
    assert vals==sorted(vals)
    assert all(0<=v<=1 for v in vals)


def test_reference_thresholds_are_ordered():
    t=_reference_thresholds(list(range(1000)))
    assert t['low']<t['high']
