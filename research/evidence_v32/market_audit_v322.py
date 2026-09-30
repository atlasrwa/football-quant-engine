"""Read-only V3.2.2 timestamped Bet365 market audit. No bet selection."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
PROTOCOL=ROOT/"MARKET_AUDIT_PROTOCOL_V32_2.json"
EVIDENCE=ROOT/"out/evidence_v2/evidence.jsonl"
PREDICTIONS=ROOT/"out/model_comparison_v3/predictions.jsonl"
OUTPUT=ROOT/"out/market_audit_v322"
ODDS_ROOT=Path("/home/ubuntu/data/thestatsapi/championship")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def parse_observed(path):
    match=re.search(r"_bet365_(\d{8}T\d{12}Z)-",path.name)
    if not match:
        return None
    return dt.datetime.strptime(match.group(1),"%Y%m%dT%H%M%S%fZ").replace(
        tzinfo=dt.timezone.utc).timestamp()
def load_kickoffs():
    out={}
    for line in EVIDENCE.read_text().splitlines():
        if not line.strip():
            continue
        row=json.loads(line)
        out[str(row["match_id"])]=float(row["kickoff_ts"])
    return out

def load_snapshots():
    out=defaultdict(list)
    for path in sorted(ODDS_ROOT.glob("research_odds_*_bet365_*.json")):
        observed=parse_observed(path)
        if observed is None:
            continue
        try:
            obj=json.loads(path.read_text())
        except (OSError,json.JSONDecodeError):
            continue
        data=(obj or {}).get("data") or {}
        mid=str(data.get("match_id") or "")
        books=data.get("bookmakers") or []
        book=next((b for b in books if str(b.get("bookmaker"))=="Bet365"),None)
        if not mid or not book:
            continue
        out[mid].append({
            "observed_at":observed,"markets":book.get("markets") or {},
            "source_path":str(path),"source_sha256":sha(path),
        })
    for rows in out.values():
        rows.sort(key=lambda r:r["observed_at"])
    return out

def decimal(value):
    try:
        x=float(value)
    except (TypeError,ValueError):
        return None
    return x if math.isfinite(x) and x>1 else None
def quote_for(snapshot,target):
    markets=snapshot["markets"]
    if target=="BTTS":
        node=markets.get("btts") or {}
        yes=decimal((node.get("yes") or {}).get("last_seen"))
        no=decimal((node.get("no") or {}).get("last_seen"))
        if yes is None or no is None:
            return None
        py=(1/yes)/((1/yes)+(1/no))
        return {"p_market":py,"yes_odds":yes,"no_odds":no}
    if target in {"total>2.5","total>3.5"}:
        line=target.split(">",1)[1]
        node=((markets.get("total_goals") or {}).get(line) or {})
        over=decimal((node.get("over") or {}).get("last_seen"))
        under=decimal((node.get("under") or {}).get("last_seen"))
        if over is None or under is None:
            return None
        po=(1/over)/((1/over)+(1/under))
        return {"p_market":po,"over_odds":over,"under_odds":under}
    return None

def choose_snapshot(rows,kickoff,window,target):
    lo=float(window["seconds_before_kickoff_min"])
    hi=float(window["seconds_before_kickoff_max"])
    eligible=[]
    for row in rows:
        seconds=kickoff-row["observed_at"]
        if lo<=seconds<=hi:
            quote=quote_for(row,target)
            if quote:
                eligible.append((row,quote))
    return max(eligible,key=lambda x:x[0]["observed_at"]) if eligible else None

def loss(p,y):
    p=min(max(float(p),1e-8),1-1e-8)
    return -(y*math.log(p)+(1-y)*math.log1p(-p))
def summarize(rows):
    if not rows:
        return {"n":0}
    model=np.array([r["p_model"] for r in rows],float)
    market=np.array([r["p_market"] for r in rows],float)
    y=np.array([r["event"] for r in rows],float)
    mll=np.mean([loss(p,t) for p,t in zip(model,y)])
    kll=np.mean([loss(p,t) for p,t in zip(market,y)])
    diffs=np.array([loss(k,t)-loss(m,t) for m,k,t in zip(model,market,y)])
    blocks=defaultdict(list)
    for row,diff in zip(rows,diffs):
        day=dt.date.fromisoformat(row["date"])
        iso=day.isocalendar()
        blocks[(iso.year,iso.week)].append(float(diff))
    interval=None
    if blocks:
        values=list(blocks.values()); rng=np.random.default_rng(3222); samples=[]
        for _ in range(2000):
            pick=rng.integers(0,len(values),len(values))
            samples.append(np.mean([v for i in pick for v in values[i]]))
        interval=[float(x) for x in np.quantile(samples,[.025,.975])]
    return {
        "n":len(rows),"model_log_loss":float(mll),"market_log_loss":float(kll),
        "market_minus_model_log_loss":float(kll-mll),
        "model_brier":float(np.mean((model-y)**2)),
        "market_brier":float(np.mean((market-y)**2)),
        "mean_model_minus_market_probability":float(np.mean(model-market)),
        "week_blocks":len(blocks),"week_block_95_interval":interval,
    }

def main():
    protocol=json.loads(PROTOCOL.read_text())
    if OUTPUT.exists():
        raise RuntimeError("immutable market audit output already exists")
    kickoffs=load_kickoffs(); snapshots=load_snapshots()
    predictions=[json.loads(x) for x in PREDICTIONS.read_text().splitlines() if x.strip()]
    allowed={
        "goals":set(protocol["model_arms"]["goals"]),
        "btts":set(protocol["model_arms"]["btts"]),
    }
    matched=[]
    for pred in predictions:
        section=str(pred.get("section") or "")
        if section not in allowed:
            continue
        arm=str(pred.get("arm") or "")
        target=str(pred.get("target") or "")
        if arm not in allowed[section]:
            continue
        if section=="goals" and target not in {"total>2.5","total>3.5"}:
            continue
        if section=="btts" and target!="BTTS":
            continue
        mid=str(pred.get("match_id") or "")
        kickoff=kickoffs.get(mid)
        if kickoff is None:
            continue
        for window in protocol["windows"]:
            chosen=choose_snapshot(snapshots.get(mid,[]),kickoff,window,target)
            if chosen is None:
                continue
            snap,quote=chosen
            matched.append({
                "section":section,"arm":arm,"target":target,
                "window":window["id"],"match_id":mid,
                "competition_id":pred.get("competition_id"),
                "date":pred["date"],"fold":pred["fold"],
                "event":int(pred["event"]),"p_model":float(pred["p"]),
                "p_market":float(quote["p_market"]),
                "kickoff_ts":kickoff,"quote_observed_at":snap["observed_at"],
                "seconds_before_kickoff":kickoff-snap["observed_at"],
                "quote":quote,"source_path":snap["source_path"],
                "source_sha256":snap["source_sha256"],
            })
    grouped=defaultdict(list)
    for row in matched:
        grouped[(row["section"],row["arm"],row["target"],row["window"])].append(row)
    results={}
    for (section,arm,target,window),rows in sorted(grouped.items()):
        results.setdefault(section,{}).setdefault(target,{}).setdefault(window,{})[arm]=summarize(rows)

    OUTPUT.mkdir(parents=True)
    with open(OUTPUT/"matches.jsonl","w",encoding="utf-8") as fh:
        for row in sorted(matched,key=lambda r:(
            r["section"],r["target"],r["window"],r["arm"],r["kickoff_ts"],r["match_id"])):
            fh.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
    (OUTPUT/"results.json").write_text(
        json.dumps(results,indent=2,sort_keys=True,allow_nan=False)+"\n")
    coverage={
        "timestamped_bet365_files":sum(len(v) for v in snapshots.values()),
        "matches_with_bet365_snapshots":len(snapshots),
        "matched_rows":len(matched),
        "matched_fixture_ids":len({r["match_id"] for r in matched}),
        "cards_market_state":"SEMANTICS_UNVERIFIED_EXCLUDED",
        "state":"DEVELOPMENT_ONLY",
    }
    (OUTPUT/"coverage.json").write_text(
        json.dumps(coverage,indent=2,sort_keys=True)+"\n")
    manifest={
        "version":protocol["version"],"state":"DEVELOPMENT_ONLY",
        "promotion":"FORBIDDEN","live_calls":0,
        "protocol_sha256":sha(PROTOCOL),
        "evidence_sha256":sha(EVIDENCE),
        "predictions_sha256":sha(PREDICTIONS),
        "runner_sha256":sha(Path(__file__)),
        "cards_included":False,
    }
    for path in sorted(OUTPUT.iterdir()):
        manifest.setdefault("files",{})[path.name]=sha(path)
    (OUTPUT/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"coverage":coverage,"groups":{
        section:{target:{window:{arm:m["n"] for arm,m in arms.items()}
        for window,arms in windows.items()} for target,windows in targets.items()}
        for section,targets in results.items()}},indent=2))

if __name__=="__main__":
    main()
