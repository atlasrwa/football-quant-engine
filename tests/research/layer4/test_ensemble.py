from src.research.layer4.ensemble import _corner_weight_eval, _corner_fixture_map


def _rows():
    out=[]
    for role in ('home','away'):
        for line in (2.5,3.5,4.5,5.5,6.5,7.5):
            for cand,p in (('dynamic_poisson',0.4),('dynamic_side_nb2',0.5)):
                out.append({'fixture_key':'f1','kickoff_ts':100,'market_scope':'SIDE','role':role,'line':line,'candidate':cand,'probability_over':p,'outcome_over':True})
    for line in (7.5,8.5,9.5,10.5,11.5,12.5):
        for cand,p in (('dynamic_poisson',0.4),('dynamic_side_nb2',0.5)):
            out.append({'fixture_key':'f1','kickoff_ts':100,'market_scope':'TOTAL','role':None,'line':line,'candidate':cand,'probability_over':p,'outcome_over':True})
    return out


def test_corner_convex_mixture_is_fixture_coherent():
    protocol={'corners':{'side_lines':[2.5,3.5,4.5,5.5,6.5,7.5],'total_lines':[7.5,8.5,9.5,10.5,11.5,12.5]}}
    m=_corner_fixture_map(_rows())
    anchor=_corner_weight_eval(m,0.0,protocol)[0]
    mixed=_corner_weight_eval(m,0.5,protocol)[0]
    nb2=_corner_weight_eval(m,1.0,protocol)[0]
    assert mixed[1] < anchor[1]
    assert nb2[1] < mixed[1]


def test_fixture_map_rejects_outcome_mismatch():
    rows=_rows(); rows[1]['outcome_over']=False
    m=_corner_fixture_map(rows)
    protocol={'corners':{'side_lines':[2.5,3.5,4.5,5.5,6.5,7.5],'total_lines':[7.5,8.5,9.5,10.5,11.5,12.5]}}
    try:
        _corner_weight_eval(m,0.5,protocol)
    except ValueError as e:
        assert 'outcome mismatch' in str(e)
    else:
        raise AssertionError('mismatch must fail')
