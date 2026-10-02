from __future__ import annotations
import hashlib,json
import numpy as np
from src.research.v37_future50.model import predict_fixture as predict_v37
from src.research.v37_future50.model import _rows as evidence_rows, freeze as v37_freeze
from src.research.v35_frontier.features import corner_target_features,v3_corner_rows
from src.research.v35_frontier.model import FrozenLinearCount
from src.research.v3_pilot.model import predict_corners as predict_v3_corners
from src.research.v36_calibration.core import prior_corner_rows
from src.research.v38_paired50.model import challenger_probs,LINES
from .config import MODEL_FREEZE

_V38=None
def _digest(o): return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def v38_freeze():
    global _V38
    if _V38 is None:
        o=json.loads(MODEL_FREEZE.read_text()); h=_digest({k:v for k,v in o.items() if k!='freeze_sha256'})
        if h!=o['freeze_sha256']: raise RuntimeError('V38 freeze hash mismatch')
        _V38=o
    return _V38

def predict_pair(fixture):
    control=predict_v37(fixture)
    ch={'goals':control.get('goals'),'corners':None,'abstentions':list(control.get('abstentions') or []),'model_freeze_sha256':v38_freeze()['freeze_sha256']}
    if control.get('corners') is None: return {'control':control,'challenger':ch}
    rows=evidence_rows(); vf=v37_freeze(); art=vf['corners_artifact']; f=v38_freeze()
    feat=corner_target_features(rows,fixture)
    model=FrozenLinearCount(art['linear_count']); means=model.predict([feat['home'],feat['away']])*np.asarray(art['count_scales'],float)
    mu_pressure=float(means.sum())
    comp=v3_corner_rows(rows,str(fixture['competition_id'])); hist=prior_corner_rows(comp,feat['cutoff_ts'])
    target={'match_id':str(fixture['match_id']),'competition_id':str(fixture['competition_id']),'ts':float(fixture['kickoff_ts']),'home_id':str(fixture['home_id']),'away_id':str(fixture['away_id'])}
    mu_v3=float(predict_v3_corners(hist,hist,target)['lambda_total'])
    probs,meta=challenger_probs(mu_v3,mu_pressure,f['alpha_v3'],f['alpha_pressure'],f['pressure_weight'],f['disagreement_k'])
    ch['corners']={'version':'V38_CORNERS_NB_DISAGREEMENT_SHRINK','probabilities':{str(line):{'p_over':float(probs[i])} for i,line in enumerate(LINES)},'mu_v3':mu_v3,'mu_pressure':mu_pressure,'alpha_v3':f['alpha_v3'],'alpha_pressure':f['alpha_pressure'],'disagreement_k':f['disagreement_k'],'mean_disagreement':meta['mean_disagreement'],'source_freeze_sha256':f['freeze_sha256']}
    return {'control':control,'challenger':ch}
