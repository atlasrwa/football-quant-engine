from src.research.layer4.calibration_run import _bin_index


def test_probability_bin_edges_are_deterministic():
    bins=[0,.1,.2,.3,1.0]
    assert _bin_index(0,bins)==0
    assert _bin_index(.1,bins)==1
    assert _bin_index(1.0,bins)==3
