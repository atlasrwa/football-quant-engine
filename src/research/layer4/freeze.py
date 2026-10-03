"""Freeze the standalone odds-blind QFE V2 Layer 4 p_model stack."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.research.dataset.manifest import canonical_json,sha256_json

MODEL_FREEZE_VERSION='qfe-v2-layer4-standalone-pmodel-v1'


def _read(path):
    d=json.loads(Path(path).read_text())
    if not isinstance(d,dict): raise ValueError(path)
    return d

def _sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_model_freeze(repo_root:Path)->dict[str,Any]:
    repo_root=Path(repo_root)
    protocol=_read(repo_root/'evidence/layer4/QFE_LAYER4_PROTOCOL_V1.json')
    audit=_read(repo_root/'evidence/layer4/QFE_LAYER4_PROTOCOL_AUDIT_V1.json')
    ensemble=_read(repo_root/'evidence/layer4/QFE_LAYER4_ENSEMBLE_SELECTION_V1.json')
    contract=_read(repo_root/'evidence/layer4/QFE_LAYER4_EXECUTION_CONTRACT_V1.json')
    raw=_read(repo_root/'evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_V1.json')
    cal=_read(repo_root/'evidence/layer4/QFE_LAYER4_CALIBRATION_V1.json')
    if not (protocol and audit['protocol_hash']==ensemble['protocol_hash']==contract['protocol_hash']==raw['protocol_hash']==cal['protocol_hash']): raise ValueError('protocol chain mismatch')
    if cal['protected_rows_scored']!=0 or cal['market_odds_used'] is not False or raw['protected_rows']!=0 or raw['market_odds_used'] is not False: raise ValueError('scientific boundary violated')
    groups={g['group']:g for g in cal['group_results']}
    diagnostics=cal['diagnostics']
    unsupported={}
    for group,d in diagnostics.items():
        unsupported[group]=[
            {'raw_probability_low':b['raw_probability_low'],'raw_probability_high':b['raw_probability_high'],'unique_fixtures':b['unique_fixtures']}
            for b in d['support_bins'] if not b['supported']
        ]
    code_files=[
        'src/research/layer4/protocol.py','src/research/layer4/ensemble.py','src/research/layer4/raw_calibration.py',
        'src/research/layer4/calibrators.py','src/research/layer4/calibration_run.py','src/research/layer4/freeze.py',
    ]
    d={
        'version':MODEL_FREEZE_VERSION,
        'scientific_status':'STANDALONE_PMODEL_FROZEN_PROTECTED_UNOPENED_NO_MARKET',
        'bindings':{
            'protocol_hash':audit['protocol_hash'],'protocol_audit_hash':audit['audit_hash'],'ensemble_selection_hash':ensemble['selection_hash'],
            'execution_contract_hash':contract['contract_hash'],'raw_calibration_hash':raw['raw_calibration_hash'],'calibration_run_hash':cal['calibration_run_hash'],
            'corpus_manifest_hash':raw['corpus_manifest_hash'],
        },
        'goals_total_2_5':{
            'dynamic_config_hash':raw['goal_dynamic_config_hash'],'similar_context_config_hash':raw['similar_config_hash'],
            'similar_context_weight':raw['goals_similar_weight'],'raw_distribution':'Poisson at blended expected total',
            'calibrator_candidate':groups['GOALS_TOTAL']['selected_candidate'],'calibrator_spec':groups['GOALS_TOTAL']['final_refit_spec'],
            'registered_lines':[2.5],
        },
        'corners':{
            'dynamic_config_hash':raw['corner_dynamic_config_hash'],'common_nb2_alpha':raw['corners_common_alpha'],'common_nb2_alpha_n_observations':raw['corners_common_alpha_n_observations'],
            'nb2_joint_mixture_weight':raw['corners_nb2_weight'],
            'side':{'calibrator_candidate':groups['CORNERS_SIDE']['selected_candidate'],'calibrator_spec':groups['CORNERS_SIDE']['final_refit_spec'],'registered_lines':protocol['corners']['side_lines']},
            'total':{'calibrator_candidate':groups['CORNERS_TOTAL']['selected_candidate'],'calibrator_spec':groups['CORNERS_TOTAL']['final_refit_spec'],'registered_lines':protocol['corners']['total_lines']},
        },
        'prediction_support':{
            'reference_thresholds':raw['reference_thresholds'],'probability_bins':protocol['prediction_support_metadata']['probability_bins'],
            'unsupported_raw_probability_bins':unsupported,'ood_policy':protocol['prediction_support_metadata']['ood_policy'],
            'reliability_band_contract':protocol['prediction_support_metadata']['reliability_band'],
        },
        'selection_evidence':{
            g:{'identity_select_metrics':groups[g]['identity_select_metrics'],'selected_candidate':groups[g]['selected_candidate'],'selected_candidate_select_metrics':next(x['select_metrics'] for x in groups[g]['candidate_results'] if x['candidate']==groups[g]['selected_candidate'])}
            for g in ('GOALS_TOTAL','CORNERS_SIDE','CORNERS_TOTAL')
        },
        'code_fingerprints':{f:_sha(repo_root/f) for f in code_files},
        'boundaries':{
            'market_odds_used':False,'protected_outcomes_scored':0,'commercial_claim_allowed':False,
            'next_step':'Freeze Layer5 market-surface and disagreement/line-selection policy before any protected outcome is opened.',
        },
    }
    d['model_freeze_hash']=sha256_json(d); return d


def render_markdown(d):
    s=d['selection_evidence']
    return '\n'.join([
        '# QFE V2 Layer 4 — Standalone p_model Freeze','',f"Model freeze hash: `{d['model_freeze_hash']}`",'',
        '> Odds-blind standalone model only. PROTECTED remains unopened. No market or commercial claim is authorized.','',
        '## Frozen stack','',
        f"- Goals O2.5: dynamic + similar-context weight **{d['goals_total_2_5']['similar_context_weight']:.2f}**, calibrated by **{d['goals_total_2_5']['calibrator_candidate']}**.",
        f"- Corner sides: Poisson/NB2 mixture weight **{d['corners']['nb2_joint_mixture_weight']:.2f}**, calibrated by **{d['corners']['side']['calibrator_candidate']}**.",
        f"- Corner totals: same coherent mixture, calibrated by **{d['corners']['total']['calibrator_candidate']}**.",
        f"- Common pre-calibration corner alpha: **{d['corners']['common_nb2_alpha']:.6f}**.",'',
        '## SELECT evidence versus identity','',
        f"- Goals: identity LL {s['GOALS_TOTAL']['identity_select_metrics']['log_loss']:.6f} → selected LL {s['GOALS_TOTAL']['selected_candidate_select_metrics']['log_loss']:.6f}.",
        f"- Corner sides: identity LL {s['CORNERS_SIDE']['identity_select_metrics']['log_loss']:.6f} → selected LL {s['CORNERS_SIDE']['selected_candidate_select_metrics']['log_loss']:.6f}.",
        f"- Corner totals: identity LL {s['CORNERS_TOTAL']['identity_select_metrics']['log_loss']:.6f} → selected LL {s['CORNERS_TOTAL']['selected_candidate_select_metrics']['log_loss']:.6f}.",'',
        '## Support boundary','',
        'Unsupported raw-probability bins remain explicit metadata and must not be treated as equally credible by Layer 5.','',
        'Next: freeze the Layer 5 market-surface/disagreement policy before opening protected outcomes.',''
    ])


def write_model_freeze(json_path:Path,md_path:Path,d):
    for path,payload in ((Path(json_path),canonical_json(d)+'\n'),(Path(md_path),render_markdown(d))):
        if path.exists():
            if path.read_text()!=payload: raise FileExistsError(path)
        else: path.parent.mkdir(parents=True,exist_ok=True); path.write_text(payload)
