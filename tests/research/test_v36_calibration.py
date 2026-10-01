"""Synthetic boundary tests, not empirical model-performance evidence."""
import numpy as np
import pytest
from scipy.stats import poisson

from src.research.v35_frontier.model import blend_probability
from src.research.v36_calibration.core import (
    Unsupported, temporal_eligibility, split_stages, prior_corner_rows,
    require_non_neutral, select_quote, coherent_blend, assert_coherent,
    fit_sigmoid, apply_sigmoid, fit_market, apply_market, paired_interval,
    count_probabilities, fit_affine, apply_affine,
)
from src.research.v36_calibration.runtime import reconstructed_features, predict_reconstructed


def test_label_availability_and_exact_equality_rejected():
    assert temporal_eligibility(kickoff_ts=200000,fit_last_kickoff_ts=99200)
    assert not temporal_eligibility(kickoff_ts=200000,fit_last_kickoff_ts=99199)
    reasons=temporal_eligibility(kickoff_ts=200000,fit_last_kickoff_ts=90000,point_in_time=True)
    assert len(reasons)==2


def test_artifact_and_fixture_must_precede_forecast_not_kickoff():
    reasons=temporal_eligibility(kickoff_ts=200000,fit_last_kickoff_ts=90000,
        artifact_created_at=113600,fixture_observed_at=113599,point_in_time=True)
    assert reasons==['ARTIFACT_NOT_AVAILABLE_BEFORE_FORECAST']


def test_grouped_splits_purge_every_stage():
    panel=[{'match_id':str(i),'kickoff_ts':t,'cutoff_ts':t-86400} for i,t in enumerate([100000,200000,200000,300000,400000,500000,600000,700000])]
    stages=split_stages(panel,[200000,400000,600000,700000])
    assert [r['match_id'] for r in stages[0]]==['0']
    for i in range(3):
        assert all(r['kickoff_ts']+14400 < min(s['cutoff_ts'] for later in stages[i+1:] for s in later) for r in stages[i])
    assert len({r['match_id'] for s in stages for r in s})==sum(map(len,stages))


@pytest.mark.parametrize('neutral',[True,None,0,'false'])
def test_neutral_unknown_and_non_boolean_rejected_before_feature_build(neutral):
    with pytest.raises(Unsupported,match='non-neutral'):
        reconstructed_features([],{'is_neutral':neutral},'goals')


def test_explicit_non_neutral_allowed():require_non_neutral({'is_neutral':False})


def test_corner_parent_uses_same_completion_cutoff():
    rows=[{'ts':t} for t in [85599,85600,85601,99999]]
    assert prior_corner_rows(rows,100000)==[{'ts':85599}]


def test_line_specific_legacy_counterexample_and_coherent_successors():
    a=poisson.sf([8,9,10],14); b=poisson.sf([8,9,10],5)
    old=np.array([[blend_probability(x,y,w) for x,y,w in zip(a,b,[.6343054397589274,.46001263002041254,.40766230561853356])]])
    with pytest.raises(ValueError,match='non-monotone'):assert_coherent(old)
    for kind in ['pmf','logit']:
        for w in [0,.25,.5,.75,1]:assert_coherent(coherent_blend(a,b,w,kind)[None,:])


def test_quotes_cannot_use_future_stale_or_opening_prices():
    def snap(t,field='last_seen'):
        return {'observed_at':t,'markets':{'total_goals':{'2.5':{'over':{field:2},'under':{field:2}}}}}
    assert select_quote([snap(100),snap(101),snap(-3501)],100,'goals',2.5) is None
    assert select_quote([snap(99,'opening')],100,'goals',2.5) is None
    assert select_quote([snap(90),snap(99)],100,'goals',2.5)['observed_at']==99


def test_calibration_slope_preserves_line_order():
    p=np.array([[.8,.6,.3],[.6,.4,.2],[.4,.2,.1],[.9,.8,.5]])
    y=np.array([[1,1,0],[1,0,0],[0,0,0],[1,1,1]])
    theta=fit_sigmoid(p,y)
    assert_coherent(apply_sigmoid(p,theta))


def test_count_calibration_preserves_distribution():
    means=np.array([[1.,2.],[2.,1.],[3.,1.],[1.,1.]])
    theta=fit_affine(means,np.array([[1,1],[2,2],[3,0],[0,1]]))
    assert_coherent(count_probabilities(apply_affine(means,theta),[2.5,3.5]))


def test_market_anchor_and_nonnegative_weights():
    q=np.array([.2,.4,.6,.8]); p=np.array([.3,.5,.5,.7]); y=np.array([0,0,1,1])
    assert np.allclose(apply_market(q,p,[0,1,0]),q)
    t=fit_market(q,p,y)
    assert 0 <= t[2] <= t[1]+1e-8


def test_uncertainty_keeps_fixture_lines_together():
    rows=[{'match_id':'a','kickoff_ts':1700000000,'y':1,'p':{'r':.5,'c':.6}},
          {'match_id':'a','kickoff_ts':1700000000,'y':0,'p':{'r':.5,'c':.4}}]
    result=paired_interval(rows,'r','c')
    assert result['n_fixtures']==1 and result['week_blocks']==1 and result['interval'] is None


def test_runtime_requires_explicit_retrospective_acknowledgement():
    with pytest.raises(Unsupported,match='acknowledgement'):predict_reconstructed([],{}, {})


def test_runtime_rejects_unbound_artifact():
    with pytest.raises(ValueError,match='hash'):predict_reconstructed([],{}, {},acknowledge_retrospective=True)
