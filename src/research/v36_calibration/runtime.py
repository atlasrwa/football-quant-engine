"""Explicit retrospective research inference; never registered in production."""
from __future__ import annotations

import hashlib
import json

import numpy as np
from scipy.stats import poisson

from src.research.v35_frontier.features import goal_target_features, corner_target_features, v3_corner_rows
from src.research.v35_frontier.model import FrozenLinearCount
from src.research.v3_pilot.model import predict_corners as parent_corners
from .core import (Unsupported, HORIZON, temporal_eligibility, require_non_neutral,
                   prior_corner_rows, count_probabilities, apply_affine,
                   apply_sigmoid, coherent_blend, assert_coherent)


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def reconstructed_features(rows,fixture,family):
    if family=='goals':
        require_non_neutral(fixture)
        return goal_target_features(rows,fixture)
    if family=='corners':return corner_target_features(rows,fixture)
    raise Unsupported('unregistered family')


def predict_reconstructed(rows,fixture,artifact,*,acknowledge_retrospective=False):
    if not acknowledge_retrospective:
        raise Unsupported('Explicit RETROSPECTIVE_RECONSTRUCTION acknowledgement required')
    declared=artifact.get('artifact_sha256')
    if declared!=digest({k:v for k,v in artifact.items() if k!='artifact_sha256'}):
        raise ValueError('artifact hash mismatch')
    if digest(rows)!=artifact['evidence_content_sha256']:
        raise ValueError('research evidence content mismatch')
    ts=float(fixture['kickoff_ts'])
    reasons=temporal_eligibility(kickoff_ts=ts,fit_last_kickoff_ts=artifact['fit_last_kickoff_ts'])
    if reasons:raise Unsupported(','.join(reasons))
    family=artifact['family']; lines=artifact['lines']
    features=reconstructed_features(rows,fixture,family)
    raw=FrozenLinearCount(artifact['linear_count']).predict([features['home'],features['away']])[None,:]
    p={'raw':count_probabilities(raw,lines),
       'count_scale':count_probabilities(raw*np.asarray(artifact['count_scales']),lines),
       'count_affine':count_probabilities(apply_affine(raw,artifact['count_affine']),lines)}
    p['shared_sigmoid']=apply_sigmoid(p['count_scale'],artifact['shared_sigmoid'])
    if family=='corners':
        history=prior_corner_rows(v3_corner_rows(rows,str(fixture['competition_id'])),ts-HORIZON)
        target={'match_id':str(fixture['match_id']),'competition_id':str(fixture['competition_id']),
                'home_id':str(fixture['home_id']),'away_id':str(fixture['away_id']),'ts':ts}
        parent=parent_corners(history,history,target)
        pr=poisson.sf(np.floor(lines),parent['lambda_total'])[None,:]
        p['v3_horizon_matched']=pr
        for kind,name in [('logit','shared_logit_stack'),('pmf','pmf_mixture')]:
            if kind in artifact['shared_stack_weights']:
                p[name]=coherent_blend(pr,p['count_scale'],artifact['shared_stack_weights'][kind],kind)
    for values in p.values():assert_coherent(values)
    return {'version':'V36_CALIBRATION_RESEARCH_1','family':family,
            'availability_mode':'RETROSPECTIVE_RECONSTRUCTION','production_activation':False,
            'feature_cutoff_ts':features['cutoff_ts'],'artifact_sha256':declared,
            'probabilities':{name:{str(line):float(v[0,i]) for i,line in enumerate(lines)} for name,v in p.items()}}
