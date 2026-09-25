"""Frozen predictive-stage helpers for Target-Aware Market Panel V1.2.2.

Feature construction is outcome-blind. Labels are constructed only by the later gated
prediction phase. M0 and M1 share rows, raw history, preprocessing and fitter.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

from src.research.dual_provider_llm import packet as P
from src.research.target_aware_market_panel import cohort_packets as CP
from src.research.target_aware_market_panel import panel as PN
from src.research.target_aware_market_panel import policy as POL
from research.target_aware_market_panel import v1_2_freeze_prehistory as RF

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research/target_aware_market_panel"
CACHE = "/home/ubuntu/data/thestatsapi/championship"
RAW_MANIFEST = OUT / "V1_2_PREHISTORY_RAW_MANIFEST_V1.json"
RAW_MANIFEST_SHA256 = "9d5bcdf37f2adf4d857e0f5a28a56579638d386eb45b08dc1195557cbcc08fc0"
FOLDS = OUT / "TARGET_AWARE_FOLD_MANIFEST_V1.json"
REGISTRY = OUT / "SOL_CLASS_C_TEMPLATE_REGISTRY_V1.json"
TARGETS = OUT / "TARGET_UNIVERSE_V1.json"
PANEL_END_UNIX = 1789412400

def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_prehistory() -> Dict[str, Any]:
    if fsha(RAW_MANIFEST) != RAW_MANIFEST_SHA256:
        raise RuntimeError("RAW_PREHISTORY_MANIFEST_HASH_MISMATCH")
    man=json.loads(RAW_MANIFEST.read_text())
    discovery=json.loads(RF.DISCOVERY.read_text())
    exact=RF.exact_fixture_index(discovery)
    fixtures=RF.load_fixtures(discovery, exact)
    payloads=[]
    for mid in sorted(exact):
        w=RF.load_terminal(mid); rec=man["raw_files"][mid]
        if fsha(RF.RAW_ROOT / f"{mid}.json") != rec["sha256"]:
            raise RuntimeError(f"RAW_FILE_HASH_MISMATCH:{mid}")
        if int(w["http_status"]) == 200:
            payloads.append((f"{mid}.json", w["payload"]))
    ok,conf=P.build_stats_map(payloads)
    if conf:
        raise RuntimeError("PREHISTORY_STATS_CONFLICT")
    h=P.normalize_history(fixtures,ok,conf)
    if len(h) != 4994:
        raise RuntimeError(f"PREHISTORY_COUNT_MISMATCH:{len(h)}")
    return h

def load_histories() -> Tuple[Dict[str,Any], Dict[str,Any], PN.PanelHistory]:
    base,_=CP.load_history(CACHE, include_gap_fetches=False)
    pre=load_prehistory()
    overlap=set(base)&set(pre)
    if overlap:
        raise RuntimeError(f"PREHISTORY_BASE_OVERLAP:{sorted(overlap)[:5]}")
    allh=dict(pre); allh.update(base)
    ph=PN.PanelHistory(PN.rows_from_history(allh), PANEL_END_UNIX)
    return base,pre,ph

def fixtures_from_folds(base: Mapping[str,Any]) -> List[Dict[str,Any]]:
    folds=json.loads(FOLDS.read_text())
    out=[]
    for fr in folds["rows"]:
        hm=base.get(fr["match_id"])
        if hm is None or not hm.stats:
            raise RuntimeError(f"PANEL_FIXTURE_MISSING:{fr['match_id']}")
        home=hm.fixture.get("home_team") or {}; away=hm.fixture.get("away_team") or {}
        out.append({"match_id":fr["match_id"],"kickoff":int(hm.kickoff_unix),
                    "competition_id":str(hm.fixture.get("competition_id")),
                    "season_id":str(hm.fixture.get("season_id")),
                    "home_team_id":str(home.get("id")),"away_team_id":str(away.get("id")),
                    "fold":fr["fold"],"involves_cohort_team":bool(fr["involves_cohort_team"])})
    if len(out) != 5620:
        raise RuntimeError(f"PANEL_ROW_COUNT_MISMATCH:{len(out)}")
    return out

def m0_feature_specs(family: str, competitions: Sequence[str]) -> List[Dict[str,Any]]:
    specs=[]
    for side in ("HOME","AWAY"):
        for metric in POL.FAMILY_CONTEXT[family]:
            for perspective in ("FOR","AGAINST"):
                for window in POL.M0_WINDOWS:
                    specs.append({"kind":"ROLLING","side":side,"metric":metric,
                                  "perspective":perspective,"period":"FULL_MATCH","window":window})
        for metric in POL.HALF_CONTEXT.get(family,[]):
            for period in ("FIRST_HALF","SECOND_HALF"):
                for perspective in ("FOR","AGAINST"):
                    for window in POL.M0_WINDOWS:
                        specs.append({"kind":"ROLLING","side":side,"metric":metric,
                                      "perspective":perspective,"period":period,"window":window})
    specs += [{"kind":"STRENGTH","side":"HOME"},{"kind":"STRENGTH","side":"AWAY"}]
    specs += [{"kind":"COMPETITION","competition_id":c} for c in sorted(competitions)]
    return specs

def feature_name(s: Mapping[str,Any]) -> str:
    if s["kind"]=="ROLLING":
        return f"M0.{s['side']}.{s['metric']}.{s['perspective']}.{s['period']}.{s['window']}"
    if s["kind"]=="STRENGTH":
        return f"M0.{s['side']}.STRENGTH"
    return f"M0.COMPETITION.{s['competition_id']}"

def _team(fx: Mapping[str,Any], side: str) -> str:
    return fx["home_team_id"] if side=="HOME" else fx["away_team_id"]

def _venue(side: str) -> str:
    return "HOME" if side=="HOME" else "AWAY"

def m0_value(h: PN.PanelHistory, fx: Mapping[str,Any], s: Mapping[str,Any]) -> float:
    if s["kind"]=="COMPETITION":
        return 1.0 if fx["competition_id"] == s["competition_id"] else 0.0
    if s["kind"]=="STRENGTH":
        v=h.strength(_team(fx,s["side"]),fx["competition_id"],fx["kickoff"])
        return np.nan if v is None else float(v)
    c={"metric":s["metric"],"perspective":s["perspective"],"period":s["period"],
       "window":s["window"]}
    v=PN.rolling(h,_team(fx,s["side"]),_venue(s["side"]),c,fx["kickoff"])
    return np.nan if v is None else float(v)

def class_c_by_family() -> Dict[str,List[Dict[str,Any]]]:
    reg=json.loads(REGISTRY.read_text())
    out={f:[] for f in POL.FAMILY_CONTEXT}
    for item in reg.get("templates",[]):
        if item.get("family") in out:
            out[item["family"]].append(item)
    for f in out:
        out[f].sort(key=lambda x:x["canonical_signature_sha256"])
    if sum(map(len,out.values())) != 124:
        raise RuntimeError("CLASS_C_COUNT_MISMATCH")
    return out

def memoize_history(h: PN.PanelHistory) -> None:
    orig=h.prior; cache={}
    def prior(team,before,venue=None):
        k=(str(team),int(before),venue)
        if k not in cache: cache[k]=orig(team,before,venue)
        return cache[k]
    h.prior=prior
    orig_s=h.strength; sc={}
    def strength(team,comp,before):
        k=(str(team),str(comp),int(before))
        if k not in sc: sc[k]=orig_s(team,comp,before)
        return sc[k]
    h.strength=strength

def build_family_matrix(h: PN.PanelHistory, fixtures: Sequence[Mapping[str,Any]],
                        family: str, templates: Sequence[Mapping[str,Any]]
                        ) -> Tuple[List[str],np.ndarray,List[str],np.ndarray]:
    comps=sorted({f["competition_id"] for f in fixtures})
    specs=m0_feature_specs(family,comps)
    m0_names=[feature_name(s) for s in specs]
    m0=np.empty((len(fixtures),len(specs)),dtype=np.float64)
    for i,fx in enumerate(fixtures):
        for j,s in enumerate(specs):
            m0[i,j]=m0_value(h,fx,s)
    llm_names=[f"M1.{x['canonical_signature_sha256']}" for x in templates]
    llm=np.empty((len(fixtures),len(templates)),dtype=np.float64)
    for j,item in enumerate(templates):
        tpl=item["feature_template"]
        for i,fx in enumerate(fixtures):
            v=PN.instantiate(tpl,h,fx)
            llm[i,j]=np.nan if v is None else float(v)
    return m0_names,m0,llm_names,llm

def primary_targets() -> List[Dict[str,Any]]:
    d=json.loads(TARGETS.read_text())
    return [t for t in d["targets"] if t["line_role"]=="PRIMARY"]

def all_targets() -> List[Dict[str,Any]]:
    return json.loads(TARGETS.read_text())["targets"]

def label_for_target(hm: Any, target: Mapping[str,Any]) -> Any:
    """Used only after prediction apparatus freeze. Returns 0/1 or None."""
    mid=target["market_id"]; line=target["line"]
    vals=hm.values
    def side(metric,which):
        try: v=vals[metric][which]
        except (KeyError,TypeError): return None
        return None if v is None else float(v)
    hg,ag=side("goals","home"),side("goals","away")
    if mid=="BTTS":
        return None if hg is None or ag is None else int(hg>=1 and ag>=1)
    if mid=="TOTAL_GOALS":
        return None if hg is None or ag is None else int(hg+ag>float(line))
    if mid=="HOME_GOALS":
        return None if hg is None else int(hg>float(line))
    if mid=="AWAY_GOALS":
        return None if ag is None else int(ag>float(line))
    hc,ac=side("corners","home"),side("corners","away")
    if mid=="TOTAL_CORNERS":
        return None if hc is None or ac is None else int(hc+ac>float(line))
    if mid=="HOME_CORNERS":
        return None if hc is None else int(hc>float(line))
    if mid=="AWAY_CORNERS":
        return None if ac is None else int(ac>float(line))
    hy,ay=side("yellow_cards","home"),side("yellow_cards","away")
    if mid=="TOTAL_YELLOW_CARDS":
        return None if hy is None or ay is None else int(hy+ay>float(line))
    raise ValueError(f"UNKNOWN_TARGET:{mid}")
