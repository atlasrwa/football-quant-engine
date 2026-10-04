from src.research.evaluation.layer31_oof import LAYER31_OOF_VERSION,MarketEventRow,_assert_monotone,_primary_decision,ComparisonSlice


def _row(line,p):
    return MarketEventRow('f','D1',1,'c','SIDE','home',line,'dynamic_poisson',4,False,p,0.1,0.1,4,4,None)

def test_monotone_ladder_accepts_decreasing_over_probability():
    _assert_monotone([_row(2.5,.8),_row(3.5,.6),_row(4.5,.4)])


def test_monotone_ladder_rejects_increase():
    try: _assert_monotone([_row(2.5,.8),_row(3.5,.9)])
    except ValueError: pass
    else: raise AssertionError('must reject non-monotone ladder')


def test_primary_decision_requires_both_proper_scores_and_role_guard():
    good={'mean_improvement':.01,'ci_low':.001,'ci_high':.02}
    primary=ComparisonSlice('SIDE',None,None,None,100,good,good)
    role=ComparisonSlice('SIDE','home',None,None,50,good,good)
    assert _primary_decision(primary,role_slices=(role,role))=='NB2_DEVELOPMENT_CANDIDATE'
    bad_role={'mean_improvement':-.01,'ci_low':-.02,'ci_high':-.001}
    rbad=ComparisonSlice('SIDE','home',None,None,50,bad_role,good)
    assert _primary_decision(primary,role_slices=(role,rbad))!='NB2_DEVELOPMENT_CANDIDATE'


def test_compact_artifact_verifier_detects_tampering(tmp_path):
    import gzip,json
    from pathlib import Path
    from src.research.dataset.manifest import canonical_json,sha256_json
    from src.research.evaluation.layer31_oof import verify_layer31_artifact
    rows=[{'a':1},{'a':2}]
    base={'version':'x','protocol':{},'protocol_hash':'p','corpus_manifest_hash':'c','corner_config':{},'corner_config_hash':'h','source_structured_oof_hash':'s','fold_parameters':[],'primary_comparisons':[],'diagnostic_comparisons':[],'side_decision':'x','total_decision':'y'}
    full={**base,'rows':rows}; ah=sha256_json(full)
    raw=''.join(canonical_json(r)+'\n' for r in rows).encode()
    gz=gzip.compress(raw,compresslevel=9,mtime=0)
    summary={**base,'artifact_hash':ah,'row_count':2,'rows_hash':sha256_json(rows),'rows_file':'r.gz','rows_encoding':'canonical-jsonl+gzip(mtime=0)'}
    jp=tmp_path/'s.json'; rp=tmp_path/'r.gz'; jp.write_text(canonical_json(summary)+'\n'); rp.write_bytes(gz)
    assert verify_layer31_artifact(jp,rp)==ah
    rp.write_bytes(gz+b'x')
    try: verify_layer31_artifact(jp,rp)
    except Exception: pass
    else: raise AssertionError('tampered gzip must fail verification')

def test_layer31_oof_version_is_pit_successor():
    assert LAYER31_OOF_VERSION == "qfe-layer3.1-corners-multiline-oof-v2-pit-horizon"
