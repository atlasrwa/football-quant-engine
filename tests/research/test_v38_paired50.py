import numpy as np
from src.research.v38_paired50.model import challenger_probs, nb_over_scalar

def test_negative_binomial_over_probabilities_are_coherent():
    p=nb_over_scalar(9.5,0.2)
    assert p.shape==(3,)
    assert np.all(np.diff(p)<=1e-12)

def test_parent_disagreement_shrink_moves_toward_half_without_crossing_lines():
    base,_=challenger_probs(11.5,8.0,.2,.25,.175,0.0)
    shrunk,_=challenger_probs(11.5,8.0,.2,.25,.175,1.5)
    assert np.all(np.abs(shrunk-.5) <= np.abs(base-.5)+1e-12)
    assert np.all(np.diff(shrunk)<=1e-12)

def test_zero_disagreement_makes_k_irrelevant():
    a,_=challenger_probs(9.0,9.0,.2,.3,.175,0.0)
    b,_=challenger_probs(9.0,9.0,.2,.3,.175,3.0)
    assert np.allclose(a,b)
