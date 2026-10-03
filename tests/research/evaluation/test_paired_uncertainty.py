from src.research.evaluation.paired_uncertainty import paired_block_bootstrap,WEEK_SECONDS


def test_paired_bootstrap_detects_consistent_improvement():
    rows=[]
    for week in range(20):
        for j in range(10):
            rows.append((week*WEEK_SECONDS+j,1.0,0.9))
    r=paired_block_bootstrap(rows,metric="ll",bootstrap_replicates=500)
    assert r.mean_improvement>0
    assert r.ci_low>0
    assert r.bootstrap_probability_positive==1.0
