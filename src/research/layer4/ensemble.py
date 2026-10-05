"""QFE V2 Layer 4 DEVELOPMENT-only ensemble selection.

This module implements the preregistered Layer 4 ensemble rules without reading
CALIBRATION or PROTECTED outcomes. Inputs are immutable Layer 3/3.1 OOF
artifacts only.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from scipy.stats import poisson

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.evaluation.paired_uncertainty import paired_block_bootstrap
from src.research.models.structured_distributions import binary_log_loss, brier_score
from src.research.layer4.protocol import protocol_v2

ENSEMBLE_SELECTION_VERSION = "qfe-layer4-ensemble-selection-v2-pit-horizon"

STRUCTURED_PATH = Path("evidence/layer3/STRUCTURED_DEVELOPMENT_OOF_V3_PIT.json")
SIMILAR_PATH = Path("evidence/layer3/SIMILAR_CONTEXT_DEVELOPMENT_OOF.json")
L31_SUMMARY_PATH = Path("evidence/layer31/QFE_LAYER31_CORNERS_MULTILINE_OOF_V2_PIT.json")
L31_ROWS_PATH = Path("evidence/layer31/QFE_LAYER31_CORNERS_MULTILINE_OOF_ROWS_V2_PIT.jsonl.gz")


@dataclass(frozen=True, slots=True)
class WeightResult:
    weight: float
    n_fixtures: int
    mean_log_loss: float
    mean_brier: float
    improvement_vs_anchor_log_loss: dict[str, Any] | None
    improvement_vs_anchor_brier: dict[str, Any] | None
    home_role_log_loss_guard: dict[str, Any] | None = None
    away_role_log_loss_guard: dict[str, Any] | None = None
    eligible: bool = False
    diagnostic_only: bool = False

    def to_dict(self) -> dict[str, Any]: return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    d=json.loads(path.read_text())
    if not isinstance(d,dict): raise ValueError(f"expected object: {path}")
    return d


def _file_sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def _poisson_over(mu: float, line: float) -> float:
    return float(poisson.sf(int(line),mu))


def _goals_rows(repo_root: Path) -> tuple[list[dict[str,Any]], list[dict[str,Any]]]:
    structured=_read_json(repo_root/STRUCTURED_PATH)
    similar=_read_json(repo_root/SIMILAR_PATH)
    dynamic={r['fixture_key']:r for r in structured['rows'] if r['target']=='goals' and r['candidate']=='dynamic_poisson'}
    sim={r['fixture_key']:r for r in similar['rows'] if r['target']=='goals'}
    keys=sorted(set(dynamic)&set(sim), key=lambda k:(dynamic[k]['kickoff_ts'],k))
    if not keys: raise ValueError('no paired goals OOF rows')
    return [dynamic[k] for k in keys],[sim[k] for k in keys]


def _goal_weight_eval(dynamic_rows,similar_rows,weight:float):
    vals=[]
    for d,s in zip(dynamic_rows,similar_rows,strict=True):
        if d['fixture_key']!=s['fixture_key']: raise ValueError('goals pairing mismatch')
        mu=(1.0-weight)*float(d['expected_total'])+weight*float(s['expected_total'])
        p=_poisson_over(mu,2.5)
        outcome=int(d['observed_total'])>2.5
        vals.append((int(d['kickoff_ts']),binary_log_loss(p,outcome),brier_score(p,outcome)))
    return vals


def _paired_interval(base,cand,index:int,metric:str,protocol):
    return paired_block_bootstrap(
        [(b[0],b[index],c[index]) for b,c in zip(base,cand,strict=True)],
        metric=metric,
        bootstrap_replicates=protocol['bootstrap']['replicates'],
        seed=protocol['bootstrap']['seed'],
    ).to_dict()


def select_goals_weight(repo_root:Path, protocol:dict[str,Any]) -> dict[str,Any]:
    dynamic,similar=_goals_rows(repo_root)
    weights=[float(x) for x in protocol['goals']['diversifier_weight_grid']]
    diagnostic=float(protocol['goals']['equal_weight_0_5'].split('_')[2]) if False else 0.5
    all_weights=weights+([diagnostic] if diagnostic not in weights else [])
    evals={w:_goal_weight_eval(dynamic,similar,w) for w in all_weights}
    base=evals[0.0]
    results=[]
    for w in all_weights:
        rows=evals[w]
        ll=mean(r[1] for r in rows); br=mean(r[2] for r in rows)
        if w==0.0:
            ll_i=br_i=None; eligible=True
        else:
            ll_i=_paired_interval(base,rows,1,'goals_binary_log_loss',protocol)
            br_i=_paired_interval(base,rows,2,'goals_brier',protocol)
            eligible=(w in weights and ll_i['ci_low']>0 and br_i['ci_low']>0)
        results.append(WeightResult(w,len(rows),ll,br,ll_i,br_i,eligible=eligible,diagnostic_only=w not in weights))
    eligible=[r for r in results if r.eligible]
    if not eligible: raise ValueError('goals ensemble has no eligible anchor')
    best=min(eligible,key=lambda r:(r.mean_log_loss,r.weight))
    # Protocol requires ties within no explicit ensemble tolerance to choose smaller weight.
    # Exact deterministic mean LL ordering is used here; calibration has its own tie tolerance.
    return {'selected_weight':best.weight,'results':[r.to_dict() for r in results],'n_paired_fixtures':len(dynamic)}


def _load_l31_rows(repo_root:Path) -> tuple[dict[str,Any],list[dict[str,Any]]]:
    summary=_read_json(repo_root/L31_SUMMARY_PATH)
    compressed=(repo_root/L31_ROWS_PATH).read_bytes()
    raw=gzip.decompress(compressed).decode('utf-8')
    rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows)!=summary['row_count']: raise ValueError('Layer3.1 row count mismatch')
    if sha256_json(rows)!=summary['rows_hash']: raise ValueError('Layer3.1 rows hash mismatch')
    return summary,rows


def _corner_fixture_map(rows:list[dict[str,Any]]) -> dict[str,dict[str,Any]]:
    out={}
    for r in rows:
        key=r['fixture_key']; f=out.setdefault(key,{'kickoff_ts':int(r['kickoff_ts']),'HOME':{},'AWAY':{},'TOTAL':{}})
        if int(r['kickoff_ts'])!=f['kickoff_ts']: raise ValueError('fixture kickoff drift')
        scope=r['market_scope']; role=(r.get('role') or '').upper()
        bucket=role if scope=='SIDE' else 'TOTAL'
        line=float(r['line'])
        f[bucket].setdefault(line,{})[r['candidate']]={'p':float(r['probability_over']),'y':bool(r['outcome_over'])}
    return out


def _corner_weight_eval(fixture_map,weight:float,protocol:dict[str,Any]):
    rows=[]
    for key in sorted(fixture_map,key=lambda k:(fixture_map[k]['kickoff_ts'],k)):
        f=fixture_map[key]; role_ll={}; role_br={}
        for role in ('HOME','AWAY'):
            lls=[]; brs=[]
            for line in protocol['corners']['side_lines']:
                c=f[role].get(float(line),{})
                if set(c)!={'dynamic_poisson','dynamic_side_nb2'}: raise ValueError(f'missing corner side pair {key}/{role}/{line}')
                y=c['dynamic_poisson']['y']
                if c['dynamic_side_nb2']['y']!=y: raise ValueError('corner outcome mismatch')
                p=(1-weight)*c['dynamic_poisson']['p']+weight*c['dynamic_side_nb2']['p']
                lls.append(binary_log_loss(p,y)); brs.append(brier_score(p,y))
            role_ll[role]=mean(lls); role_br[role]=mean(brs)
        total_ll=[]; total_br=[]
        for line in protocol['corners']['total_lines']:
            c=f['TOTAL'].get(float(line),{})
            if set(c)!={'dynamic_poisson','dynamic_side_nb2'}: raise ValueError(f'missing corner total pair {key}/{line}')
            y=c['dynamic_poisson']['y']
            if c['dynamic_side_nb2']['y']!=y: raise ValueError('corner total outcome mismatch')
            p=(1-weight)*c['dynamic_poisson']['p']+weight*c['dynamic_side_nb2']['p']
            total_ll.append(binary_log_loss(p,y)); total_br.append(brier_score(p,y))
        side_ll=0.5*(role_ll['HOME']+role_ll['AWAY']); side_br=0.5*(role_br['HOME']+role_br['AWAY'])
        composite_ll=0.5*side_ll+0.5*mean(total_ll); composite_br=0.5*side_br+0.5*mean(total_br)
        rows.append((f['kickoff_ts'],composite_ll,composite_br,role_ll['HOME'],role_ll['AWAY']))
    return rows


def select_corners_weight(repo_root:Path,protocol:dict[str,Any]) -> dict[str,Any]:
    summary,rows=_load_l31_rows(repo_root)
    fixture_map=_corner_fixture_map(rows)
    weights=[float(x) for x in protocol['corners']['nb2_weight_grid']]
    evals={w:_corner_weight_eval(fixture_map,w,protocol) for w in weights}; base=evals[0.0]
    results=[]
    for w in weights:
        vals=evals[w]; ll=mean(r[1] for r in vals); br=mean(r[2] for r in vals)
        if w==0.0:
            lli=bri=home=away=None; eligible=True
        else:
            lli=_paired_interval(base,vals,1,'corners_composite_log_loss',protocol)
            bri=_paired_interval(base,vals,2,'corners_composite_brier',protocol)
            home=_paired_interval(base,vals,3,'corners_home_role_log_loss',protocol)
            away=_paired_interval(base,vals,4,'corners_away_role_log_loss',protocol)
            eligible=(lli['ci_low']>0 and bri['ci_low']>0 and home['ci_high']>=0 and away['ci_high']>=0)
        results.append(WeightResult(w,len(vals),ll,br,lli,bri,home,away,eligible,False))
    eligible=[r for r in results if r.eligible]
    if not eligible: raise ValueError('corners ensemble has no eligible anchor')
    best=min(eligible,key=lambda r:(r.mean_log_loss,r.weight))
    return {'selected_weight':best.weight,'results':[r.to_dict() for r in results],'n_paired_fixtures':len(fixture_map),'layer31_artifact_hash':summary['artifact_hash']}


def build_ensemble_selection(repo_root:Path) -> dict[str,Any]:
    repo_root=Path(repo_root); protocol=protocol_v2().to_dict()
    if protocol['scientific_boundary']['protected_outcomes_allowed'] or protocol['scientific_boundary']['market_odds_allowed']:
        raise ValueError('Layer4 protocol boundary violated')
    result={
        'version':ENSEMBLE_SELECTION_VERSION,
        'protocol_hash':protocol_v2().protocol_hash,
        'scientific_status':'DEVELOPMENT_ONLY_ENSEMBLE_SELECTION_NO_CALIBRATION_NO_PROTECTED_NO_MARKET',
        'source_artifacts':{
            'structured_semantic_hash':sha256_json(_read_json(repo_root/STRUCTURED_PATH)),
            'similar_semantic_hash':sha256_json(_read_json(repo_root/SIMILAR_PATH)),
            'layer31_summary_sha256':_file_sha(repo_root/L31_SUMMARY_PATH),
            'layer31_rows_sha256':_file_sha(repo_root/L31_ROWS_PATH),
        },
        'goals':select_goals_weight(repo_root,protocol),
        'corners':select_corners_weight(repo_root,protocol),
        'calibration_rows_scored':0,
        'protected_rows_scored':0,
        'market_odds_used':False,
    }
    result['selection_hash']=sha256_json(result)
    return result


def render_markdown(d:dict[str,Any])->str:
    lines=['# QFE V2 Layer 4 — DEVELOPMENT Ensemble Selection','',f"Selection hash: `{d['selection_hash']}`",f"Protocol hash: `{d['protocol_hash']}`",'', '> DEVELOPMENT ONLY. Calibration/protected outcomes and market odds were not used.','']
    for family in ('goals','corners'):
        x=d[family]; lines += [f"## {family.title()}",'',f"Selected non-anchor component weight: **{x['selected_weight']:.2f}**",f"Paired fixtures: **{x['n_paired_fixtures']}**",'', '| Weight | Mean LL | Mean Brier | Eligible | Diagnostic only |','|---:|---:|---:|:---:|:---:|']
        for r in x['results']:
            lines.append(f"| {r['weight']:.2f} | {r['mean_log_loss']:.6f} | {r['mean_brier']:.6f} | {r['eligible']} | {r['diagnostic_only']} |")
        lines.append('')
    return '\n'.join(lines)


def write_ensemble_selection(json_path:Path,md_path:Path,d:dict[str,Any])->None:
    payloads=((Path(json_path),canonical_json(d)+'\n'),(Path(md_path),render_markdown(d)))
    for path,payload in payloads:
        if path.exists():
            if path.read_text()!=payload: raise FileExistsError(f'ensemble selection differs: {path}')
        else:
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(payload)
