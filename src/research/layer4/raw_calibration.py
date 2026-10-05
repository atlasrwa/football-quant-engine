"""Build the immutable raw CALIBRATION prediction substrate for QFE V2 Layer 4."""
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from scipy.stats import poisson

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import MultiSeasonPITCorpus
from src.research.evaluation.chronology import CALIBRATION_START_TS, PROTECTED_START_TS
from src.research.evaluation.similar_oof import (
    GOALS_FEATURES,
    SimilarContextConfig,
    _fit_scaler,
    _predict_one,
    _raw_matrix,
)
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    DEFAULT_AVAILABILITY_EMBARGO_SECONDS,
    DEFAULT_DECISION_HORIZON_SECONDS,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)
from src.research.models.structured_distributions import (
    fit_nb2_dispersion,
    nb2_cdf,
    nb2_total_under_probability_from_sides,
)
from src.research.layer4.protocol import (
    CALIBRATION_FIT_END_TS,
    CORNERS_SIDE_LINES,
    CORNERS_TOTAL_LINES,
    OOD_QUANTILES,
    COMPONENT_GAP_OOD_QUANTILE,
    protocol_v2,
)

RAW_CALIBRATION_VERSION="qfe-layer4-raw-calibration-v3-pit-replay"


@dataclass(frozen=True,slots=True)
class RawCalibrationRow:
    fixture_key: str
    kickoff_ts: int
    phase: str
    competition_ref: str
    group: str
    role: str | None
    line: float
    outcome_over: bool
    raw_probability: float
    component_0_probability: float
    component_1_probability: float
    component_dispersion: float
    expected_count: float
    dynamic_effective_team_support: float
    prior_competition_match_count: int
    sample_weight: float
    model_space_intensity_percentile: float
    component_gap_percentile: float
    ood_flags: tuple[str,...]
    neighbor_count: int | None = None

    def to_dict(self)->dict[str,Any]:
        d=asdict(self); d['ood_flags']=list(self.ood_flags); return d


def _read_json(path:Path)->dict[str,Any]:
    d=json.loads(path.read_text())
    if not isinstance(d,dict): raise ValueError(path)
    return d


def _file_sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()


def _poisson_over(mu:float,line:float)->float: return float(poisson.sf(int(line),mu))

def _nb2_over(mu:float,line:float,alpha:float)->float: return float(1.0-nb2_cdf(int(line),mu,alpha))


def _percentile(sorted_values:np.ndarray,value:float)->float:
    if len(sorted_values)==0: return 0.5
    return float(np.searchsorted(sorted_values,value,side='right')/len(sorted_values))


def _reference_thresholds(values:list[float])->dict[str,float]:
    arr=np.asarray(values,float)
    if len(arr)==0: raise ValueError('empty OOD reference')
    return {
        'low':float(np.quantile(arr,OOD_QUANTILES[0])),
        'high':float(np.quantile(arr,OOD_QUANTILES[1])),
    }


def _load_development_references(repo_root:Path,goals_weight:float)->dict[str,Any]:
    structured=_read_json(repo_root/'evidence/layer3/STRUCTURED_DEVELOPMENT_OOF_V3_PIT.json')
    similar=_read_json(repo_root/'evidence/layer3/SIMILAR_CONTEXT_DEVELOPMENT_OOF.json')
    gd={r['fixture_key']:r for r in structured['rows'] if r['target']=='goals' and r['candidate']=='dynamic_poisson'}
    gs={r['fixture_key']:r for r in similar['rows'] if r['target']=='goals'}
    goals_int=[]; goals_gap=[]
    for k in set(gd)&set(gs):
        d,s=gd[k],gs[k]
        mu=(1-goals_weight)*float(d['expected_total'])+goals_weight*float(s['expected_total'])
        goals_int.append(mu); goals_gap.append(abs(float(d['probability_over'])-float(s['probability_over'])))

    summary=_read_json(repo_root/'evidence/layer31/QFE_LAYER31_CORNERS_MULTILINE_OOF_V2_PIT.json')
    raw=gzip.decompress((repo_root/'evidence/layer31/QFE_LAYER31_CORNERS_MULTILINE_OOF_ROWS_V2_PIT.jsonl.gz').read_bytes()).decode()
    rows=[json.loads(x) for x in raw.splitlines() if x.strip()]
    if len(rows)!=summary['row_count'] or sha256_json(rows)!=summary['rows_hash']:
        raise ValueError('Layer3.1 reference artifact mismatch')
    pairs={}
    for r in rows:
        key=(r['fixture_key'],r['market_scope'],r.get('role'),float(r['line']))
        pairs.setdefault(key,{})[r['candidate']]=r
    side_int=[];side_gap=[];total_int=[];total_gap=[]
    for (fixture,scope,role,line),c in pairs.items():
        if set(c)!={'dynamic_poisson','dynamic_side_nb2'}: continue
        a=c['dynamic_poisson']; b=c['dynamic_side_nb2']
        gap=abs(float(a['probability_over'])-float(b['probability_over']))
        if scope=='SIDE':
            side_int.append(float(a['lambda_home'] if role=='home' else a['lambda_away'])); side_gap.append(gap)
        else:
            total_int.append(float(a['lambda_home'])+float(a['lambda_away'])); total_gap.append(gap)
    return {
        'GOALS_TOTAL':(np.sort(np.asarray(goals_int)),np.sort(np.asarray(goals_gap))),
        'CORNERS_SIDE':(np.sort(np.asarray(side_int)),np.sort(np.asarray(side_gap))),
        'CORNERS_TOTAL':(np.sort(np.asarray(total_int)),np.sort(np.asarray(total_gap))),
    }


def _similar_goal_predictions(corpus:MultiSeasonPITCorpus,config:SimilarContextConfig)->dict[str,tuple[float,int]]:
    rows=[r for r in corpus.pit.rows if int(r.kickoff_ts)<PROTECTED_START_TS]
    by_comp={}
    for r in rows: by_comp.setdefault(r.competition_ref,[]).append(r)
    out={}
    for comp,comp_rows in by_comp.items():
        comp_rows.sort(key=lambda r:(int(r.kickoff_ts),r.fixture_key))
        raw_x=_raw_matrix(comp_rows,GOALS_FEATURES)
        y=np.asarray([np.nan if r.targets.get('goals_total_regulation') is None else float(r.targets['goals_total_regulation']) for r in comp_rows])
        for i,row in enumerate(comp_rows):
            ts=int(row.kickoff_ts)
            if ts<CALIBRATION_START_TS or ts>=PROTECTED_START_TS: continue
            cutoff = ts - DEFAULT_DECISION_HORIZON_SECONDS
            source_kickoffs = np.asarray(
                [int(r.kickoff_ts) for r in comp_rows[:i]],
                dtype=np.int64,
            )
            eligible=np.where(
                np.isfinite(y[:i])
                & (
                    source_kickoffs + DEFAULT_AVAILABILITY_EMBARGO_SECONDS
                    <= cutoff
                )
            )[0]
            if len(eligible)==0: continue
            tx=raw_x[eligible]; ty=y[:i][eligible]; mu,sd=_fit_scaler(tx); prior=float(np.mean(ty))
            pred,k,_=_predict_one(tx,ty,raw_x[i],mu,sd,config,prior)
            out[row.fixture_key]=(float(pred),int(k))
    return out


def _assert_monotone(rows:list[RawCalibrationRow])->None:
    groups={}
    for r in rows:
        groups.setdefault((r.fixture_key,r.group,r.role),[]).append(r)
    for key,vals in groups.items():
        vals=sorted(vals,key=lambda r:r.line); ps=[r.raw_probability for r in vals]
        if any(ps[i+1]>ps[i]+1e-12 for i in range(len(ps)-1)):
            raise ValueError(f'non-monotone raw ladder: {key}')


def build_raw_calibration(*,corpus:MultiSeasonPITCorpus,repo_root:Path)->tuple[dict[str,Any],tuple[RawCalibrationRow,...]]:
    repo_root=Path(repo_root); protocol=protocol_v2().to_dict()
    selection=_read_json(repo_root/'evidence/layer4/QFE_LAYER4_ENSEMBLE_SELECTION_V2_PIT.json')
    contract=_read_json(repo_root/'evidence/layer4/QFE_LAYER4_EXECUTION_CONTRACT_V2_PIT.json')
    if selection['selection_hash']!=contract['ensemble_selection_hash']: raise ValueError('ensemble binding mismatch')
    gw=float(selection['goals']['selected_weight']); cw=float(selection['corners']['selected_weight'])
    structured=_read_json(repo_root/'evidence/layer3/STRUCTURED_DEVELOPMENT_OOF_V3_PIT.json')
    goal_cfg=DynamicCountConfig(**structured['goal_dynamic_config']); corner_cfg=DynamicCountConfig(**structured['corner_dynamic_config'])
    similar_source=_read_json(repo_root/'evidence/layer3/SIMILAR_CONTEXT_DEVELOPMENT_OOF.json')
    similar_cfg=SimilarContextConfig(**similar_source['config'])

    matches=tuple(m for m in corpus.matches if m.date_unix<PROTECTED_START_TS)
    goals_fc={f.fixture_key:f for f in DynamicHierarchicalCountBaseline(GOALS_TARGET,goal_cfg).walk_forward(matches)}
    corners_fc={f.fixture_key:f for f in DynamicHierarchicalCountBaseline(CORNERS_TARGET,corner_cfg).walk_forward(matches)}
    alpha_rows=[]
    for m in matches:
        if m.date_unix>=CALIBRATION_START_TS: continue
        obs=CORNERS_TARGET.observed_counts(m); f=corners_fc.get(m.stable_fixture_key)
        if obs is None or f is None: continue
        alpha_rows.extend(((f.lambda_home,obs[0]),(f.lambda_away,obs[1])))
    alpha_fit=fit_nb2_dispersion(alpha_rows)
    similar_pred=_similar_goal_predictions(corpus,similar_cfg)
    pit={r.fixture_key:r for r in corpus.pit.rows if int(r.kickoff_ts)<PROTECTED_START_TS}
    refs=_load_development_references(repo_root,gw)
    thresholds={g:{'intensity':_reference_thresholds(list(v[0])),'gap_high':float(np.quantile(v[1],COMPONENT_GAP_OOD_QUANTILE))} for g,v in refs.items()}

    out=[]
    for m in matches:
        if not (CALIBRATION_START_TS<=m.date_unix<PROTECTED_START_TS): continue
        if not m.stable_fixture_key or not m.competition_ref: raise ValueError('stable identity required')
        phase='CALIBRATION_FIT' if m.date_unix<CALIBRATION_FIT_END_TS else 'CALIBRATION_SELECT'
        pr=pit[m.stable_fixture_key]; comp_n=int(pr.features.get('competition_history_matches') or 0)
        gf=goals_fc[m.stable_fixture_key]; gobs=GOALS_TARGET.observed_counts(m)
        sim=similar_pred.get(m.stable_fixture_key)
        if gobs is not None and sim is not None:
            sim_mu,k=sim; dyn_p=_poisson_over(gf.lambda_total,2.5); sim_p=_poisson_over(sim_mu,2.5)
            raw_p=(1-gw)*dyn_p+gw*sim_p
            # probability blend is used for calibration substrate; selected goals contract
            # blends expected total. Recompute exact contract probability below.
            blend_mu=(1-gw)*gf.lambda_total+gw*sim_mu; raw_p=_poisson_over(blend_mu,2.5)
            gap=abs(dyn_p-sim_p); ints,gaps=refs['GOALS_TOTAL']; flags=[]
            if blend_mu<thresholds['GOALS_TOTAL']['intensity']['low'] or blend_mu>thresholds['GOALS_TOTAL']['intensity']['high']: flags.append('INTENSITY_OOD')
            if gap>thresholds['GOALS_TOTAL']['gap_high']: flags.append('COMPONENT_GAP_OOD')
            out.append(RawCalibrationRow(m.stable_fixture_key,m.date_unix,phase,m.competition_ref,'GOALS_TOTAL',None,2.5,(gobs[0]+gobs[1])>2.5,raw_p,dyn_p,sim_p,gap,blend_mu,gf.effective_support,comp_n,1.0,_percentile(ints,blend_mu),_percentile(gaps,gap),tuple(flags),k))
        cf=corners_fc[m.stable_fixture_key]; cobs=CORNERS_TARGET.observed_counts(m)
        if cobs is None: continue
        for role,count,mu in (('HOME',cobs[0],cf.lambda_home),('AWAY',cobs[1],cf.lambda_away)):
            for line in CORNERS_SIDE_LINES:
                p0=_poisson_over(mu,line); p1=_nb2_over(mu,line,alpha_fit.alpha); p=(1-cw)*p0+cw*p1; gap=abs(p0-p1); ints,gaps=refs['CORNERS_SIDE']; flags=[]
                if mu<thresholds['CORNERS_SIDE']['intensity']['low'] or mu>thresholds['CORNERS_SIDE']['intensity']['high']: flags.append('INTENSITY_OOD')
                if gap>thresholds['CORNERS_SIDE']['gap_high']: flags.append('COMPONENT_GAP_OOD')
                out.append(RawCalibrationRow(m.stable_fixture_key,m.date_unix,phase,m.competition_ref,'CORNERS_SIDE',role,float(line),count>line,p,p0,p1,gap,mu,cf.effective_support,comp_n,1/12,_percentile(ints,mu),_percentile(gaps,gap),tuple(flags),None))
        total=cobs[0]+cobs[1]; mu=cf.lambda_total
        for line in CORNERS_TOTAL_LINES:
            p0=_poisson_over(mu,line); p1=1.0-nb2_total_under_probability_from_sides(line,cf.lambda_home,cf.lambda_away,alpha_fit.alpha); p=(1-cw)*p0+cw*p1; gap=abs(p0-p1); ints,gaps=refs['CORNERS_TOTAL']; flags=[]
            if mu<thresholds['CORNERS_TOTAL']['intensity']['low'] or mu>thresholds['CORNERS_TOTAL']['intensity']['high']: flags.append('INTENSITY_OOD')
            if gap>thresholds['CORNERS_TOTAL']['gap_high']: flags.append('COMPONENT_GAP_OOD')
            out.append(RawCalibrationRow(m.stable_fixture_key,m.date_unix,phase,m.competition_ref,'CORNERS_TOTAL',None,float(line),total>line,p,p0,p1,gap,mu,cf.effective_support,comp_n,1/6,_percentile(ints,mu),_percentile(gaps,gap),tuple(flags),None))
    _assert_monotone(out)
    if any(r.kickoff_ts>=PROTECTED_START_TS for r in out): raise ValueError('protected row leaked')
    if any('market' in k.lower() for r in out for k in r.to_dict()): raise ValueError('market field leaked')
    summary={
        'version':RAW_CALIBRATION_VERSION,'protocol_hash':protocol_v2().protocol_hash,'ensemble_selection_hash':selection['selection_hash'],'execution_contract_hash':contract['contract_hash'],
        'corpus_manifest_hash':corpus.manifest.manifest_hash,'goal_dynamic_config_hash':goal_cfg.identity_hash,'corner_dynamic_config_hash':corner_cfg.identity_hash,'similar_config_hash':similar_cfg.identity_hash,
        'goals_similar_weight':gw,'corners_nb2_weight':cw,'corners_common_alpha':alpha_fit.alpha,'corners_common_alpha_n_observations':alpha_fit.n_observations,
        'reference_thresholds':thresholds,
        'row_count':len(out),'fit_row_count':sum(r.phase=='CALIBRATION_FIT' for r in out),'select_row_count':sum(r.phase=='CALIBRATION_SELECT' for r in out),
        'fixture_count':len({r.fixture_key for r in out}),'fit_fixture_count':len({r.fixture_key for r in out if r.phase=='CALIBRATION_FIT'}),'select_fixture_count':len({r.fixture_key for r in out if r.phase=='CALIBRATION_SELECT'}),
        'group_counts':{g:sum(r.group==g for r in out) for g in ('GOALS_TOTAL','CORNERS_SIDE','CORNERS_TOTAL')},
        'protected_rows':0,'market_odds_used':False,'rows_hash':sha256_json([r.to_dict() for r in out]),
        'source_hashes':{'structured':sha256_json(structured),'similar':sha256_json(similar_source),'ensemble_file':_file_sha(repo_root/'evidence/layer4/QFE_LAYER4_ENSEMBLE_SELECTION_V2_PIT.json')},
    }
    summary['raw_calibration_hash']=sha256_json(summary)
    return summary,tuple(out)


def write_raw_calibration(*,summary_path:Path,rows_path:Path,summary:dict[str,Any],rows:tuple[RawCalibrationRow,...])->None:
    raw=''.join(canonical_json(r.to_dict())+'\n' for r in rows).encode(); gz=gzip.compress(raw,compresslevel=9,mtime=0)
    s={**summary,'rows_file':Path(rows_path).name,'rows_file_sha256':hashlib.sha256(gz).hexdigest(),'rows_encoding':'canonical-jsonl+gzip(mtime=0)'}
    sp=Path(summary_path); rp=Path(rows_path); payload=canonical_json(s)+'\n'
    if sp.exists():
        if sp.read_text()!=payload: raise FileExistsError(sp)
    else: sp.parent.mkdir(parents=True,exist_ok=True); sp.write_text(payload)
    if rp.exists():
        if rp.read_bytes()!=gz: raise FileExistsError(rp)
    else: rp.parent.mkdir(parents=True,exist_ok=True); rp.write_bytes(gz)
