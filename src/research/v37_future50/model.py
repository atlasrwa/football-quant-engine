from __future__ import annotations
import json, hashlib
from pathlib import Path
from src.research.v36_calibration.runtime import predict_reconstructed
from src.research.v3_pilot.model import canonical_hash
from .config import MODEL_FREEZE,EVIDENCE

_ROWS=None; _FREEZE=None

def _rows():
    global _ROWS
    if _ROWS is None: _ROWS=[json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]
    return _ROWS

def freeze():
    global _FREEZE
    if _FREEZE is None:
        o=json.loads(MODEL_FREEZE.read_text()); raw={k:v for k,v in o.items() if k!='freeze_sha256'}
        h=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if h!=o['freeze_sha256']: raise RuntimeError('model freeze hash mismatch')
        _FREEZE=o
    return _FREEZE

def predict_fixture(fixture:dict)->dict:
    f=freeze(); rows=_rows(); out={'goals':None,'corners':None,'abstentions':[],'model_freeze_sha256':f['freeze_sha256']}
    for family,arm,key in [('goals','count_scale','goals_artifact'),('corners','shared_logit_stack','corners_artifact')]:
        try:
            r=predict_reconstructed(rows,fixture,f[key],acknowledge_retrospective=True)
            probs={line:{'p_over':p} for line,p in r['probabilities'][arm].items()}
            if family=='corners':
                w=float(f[key]['shared_stack_weights']['logit'])
                for line,node in probs.items():
                    node['p_over_v3']=float(r['probabilities']['v3_horizon_matched'][line])
                    node['p_over_pressure']=float(r['probabilities']['count_scale'][line])
                    node['pressure_weight']=w
            d={'version':f'V37_{family.upper()}_{arm.upper()}','probabilities':probs,'source_artifact_sha256':f[key]['artifact_sha256']}
            d['distribution_hash']=canonical_hash(d); out[family]=d
        except Exception as exc:
            out['abstentions'].append({'family':family,'reason':f'{type(exc).__name__}:{str(exc)[:200]}'})
    return out
