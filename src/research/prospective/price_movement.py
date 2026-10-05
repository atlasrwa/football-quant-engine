"""Passive Goals O/U 2.5 price-movement scanner for Prospective V1."""
from __future__ import annotations

import fcntl
import hashlib
import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.layer5.market_surface import TwoWayQuote, build_market_point, select_benchmark_bundle
from src.research.prospective.api_contract import Endpoint
from src.research.prospective.capture import CaptureRecord, ProspectiveApiClient
from src.research.prospective.odds_capture import OddsSemantics, extract_prices
from src.research.prospective.storage import CaptureStore

PRICE_PROTOCOL_HASH = "b28a5f2bf08476de006633e1e13ce8065f6d9e168796a3ca668d0bb7d44314ae"
PRICE_AMENDMENT_HASH = "6b1420aa9398490b4614f0cf044de296c481d1db410fd2bf4e33115b6d1831c3"
COHORT_HASH = "f3d5bb667f8849b33baf29fb9666400427a17c4cf02f47e9dc0e0a098af6f8f0"
HORIZON = 21600
GOAL_LINE = 2.5
MAX_CLOSE_AGE = 600
SCHEDULED_STATES = {"scheduled","upcoming","not_started","timed","fixture"}

class PriceMovementScientificAbort(RuntimeError):
    pass

def _read_json(path: Path) -> dict[str,Any]:
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict):
        raise ValueError(path)
    return value

def _immutable_json(path: Path, value: Any) -> None:
    payload=(canonical_json(value)+"\n").encode()
    if path.exists():
        if path.read_bytes()!=payload:
            raise FileExistsError(f"immutable price-movement artifact differs: {path}")
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(payload)

def _sha_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def _parse_ts(value: Any) -> float:
    from datetime import datetime
    text=str(value or "")
    if text.endswith("Z"):
        text=text[:-1]+"+00:00"
    dt=datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.timestamp()

def _unwrap(body: Any) -> dict[str,Any]:
    if not isinstance(body,dict):
        raise ValueError("provider payload is not an object")
    data=body.get("data",body)
    if not isinstance(data,dict):
        raise ValueError("provider data is not an object")
    return data

def _status_value(body: Mapping[str,Any]) -> str:
    value=body.get("status")
    if isinstance(value,Mapping):
        value=value.get("type") or value.get("name") or value.get("status")
    return str(value or "").lower()

def _load_bound_evidence(repo_root: Path):
    protocol=_read_json(repo_root/"evidence/prospective_v1/QFE_PRICE_MOVEMENT_PROTOCOL_V1.json")
    amendment=_read_json(repo_root/"evidence/prospective_v1/QFE_PRICE_MOVEMENT_PROTOCOL_V1_AMENDMENT_A.json")
    cohort=_read_json(repo_root/"evidence/prospective_v1/QFE_PROSPECTIVE_COHORT_V1.json")
    discovery=_read_json(repo_root/"evidence/prospective_v1/QFE_PROSPECTIVE_COHORT_DISCOVERY_V1.json")
    if protocol.get("protocol_hash")!=PRICE_PROTOCOL_HASH:
        raise PriceMovementScientificAbort("price movement protocol binding mismatch")
    if amendment.get("amendment_hash")!=PRICE_AMENDMENT_HASH:
        raise PriceMovementScientificAbort("price movement amendment binding mismatch")
    if cohort.get("cohort_hash")!=COHORT_HASH or discovery.get("cohort_hash")!=COHORT_HASH:
        raise PriceMovementScientificAbort("cohort binding mismatch")
    rows=discovery.get("fixture_identity_rows")
    if not isinstance(rows,list) or sha256_json(rows)!=discovery.get("fixture_identity_hash"):
        raise PriceMovementScientificAbort("fixture identity binding mismatch")
    identities={str(row["fixture_id"]):dict(row) for row in rows}
    return protocol,cohort,identities

def _prediction_path(cohort_root: Path, fid: str) -> Path:
    return cohort_root/"predictions"/f"{fid}.json"

def _close_path(movement_root: Path, fid: str) -> Path:
    return movement_root/"close"/f"{fid}.json"

def _movement_path(movement_root: Path, fid: str) -> Path:
    return movement_root/"movement"/f"{fid}.json"

def _verify_schedule(client: ProspectiveApiClient, identity: Mapping[str,Any], now_fn: Callable[[],float]):
    fid=str(identity["fixture_id"])
    body=client.get(Endpoint.MATCH_DETAIL,match_id=fid)
    observed=float(now_fn())
    if body is None:
        return False,"SCHEDULE_DETAIL_MISSING",observed
    row=_unwrap(body)
    if str(row.get("id") or "")!=fid:
        return False,"SCHEDULE_IDENTITY_DRIFT",observed
    try:
        kickoff=_parse_ts(row.get("utc_date"))
    except Exception:
        return False,"SCHEDULE_TIME_INVALID",observed
    if abs(kickoff-float(identity["event_time"]))>1e-6:
        return False,"SCHEDULE_CHANGED",observed
    status=_status_value(row)
    if status not in SCHEDULED_STATES:
        return False,"SCHEDULE_STATUS_"+(status.upper() if status else "UNKNOWN"),observed
    return True,None,observed

def _capture_movement_odds(*, client, movement_root, identity, cutoff, now_fn):
    fid=str(identity["fixture_id"])
    event_time=float(identity["event_time"])
    ok,reason,verified_at=_verify_schedule(client,identity,now_fn)
    if not ok:
        return {"fixture_id":fid,"status":reason or "SCHEDULE_ABSTAIN","observed_at":verified_at,"records_appended":0}
    body=client.get(Endpoint.MATCH_ODDS,match_id=fid)
    observed=float(now_fn())
    if observed<cutoff:
        return {"fixture_id":fid,"status":"BEFORE_T6","observed_at":observed,"records_appended":0}
    if observed>=event_time:
        return {"fixture_id":fid,"status":"AT_OR_AFTER_KICKOFF","observed_at":observed,"records_appended":0}
    if body is None or not isinstance(body,dict):
        return {"fixture_id":fid,"status":"MISSING","observed_at":observed,"records_appended":0}
    ph=_sha_payload(body)
    raw_path=movement_root/"raw"/fid/f"{int(observed*1_000_000):020d}_{ph}.json"
    _immutable_json(raw_path,body)
    prices=extract_prices(body,payload_hash=ph,field="last_seen",semantics=OddsSemantics.PROSPECTIVE_SNAPSHOT,
                          observed_at=observed,markets=("total_goals",),team_markets=())
    records=[]
    for p in prices:
        if p.line is None or abs(float(p.line)-GOAL_LINE)>1e-9 or p.selection not in {"over","under"}:
            continue
        records.append(CaptureRecord(
            provider="thestatsapi",provider_entity_id=fid,canonical_entity_id=fid,
            concept=f"odds:total_goals:{p.selection}:2.5:{p.bookmaker}",value=float(p.decimal_odds),
            event_time=event_time,observed_at=observed,retrieved_at=observed,forecast_cutoff=float(cutoff),
            raw_payload_hash=ph,raw_status="PROSPECTIVE_SNAPSHOT",vintage="MOVEMENT_V1"))
    appended=CaptureStore(movement_root/"captures.jsonl.gz").extend(records)
    observation={"version":"qfe-price-movement-observation-v1","protocol_hash":PRICE_PROTOCOL_HASH,
        "fixture_id":fid,"event_time":event_time,"prediction_cutoff":float(cutoff),
        "schedule_verified_at":verified_at,"schedule_verified":True,"observed_at":observed,
        "raw_payload_hash":ph,"raw_path":str(raw_path),"registered_records":len(records),"records_appended":appended}
    observation["observation_hash"]=sha256_json(observation)
    _immutable_json(movement_root/"observations"/fid/f"{int(observed*1_000_000):020d}_{ph}.json",observation)
    return {"fixture_id":fid,"status":"CAPTURED" if records else "NO_REGISTERED_GOAL_QUOTES",
            "observed_at":observed,"raw_payload_hash":ph,"registered_records":len(records),"records_appended":appended}

def _quotes_from_records(records: Iterable[CaptureRecord], fid: str) -> list[TwoWayQuote]:
    cells={}
    for rec in records:
        if rec.canonical_entity_id!=fid:
            continue
        parts=str(rec.concept).split(":")
        if len(parts)!=5 or parts[:2]!=["odds","total_goals"] or parts[2] not in {"over","under"}:
            continue
        try:
            line=float(parts[3]); odds=float(rec.value)
        except (TypeError,ValueError):
            continue
        if abs(line-GOAL_LINE)>1e-9:
            continue
        key=(parts[4],float(rec.observed_at),str(rec.raw_payload_hash))
        cells.setdefault(key,{})[parts[2]]=odds
    quotes=[]
    for (book,obs,raw_hash),sides in sorted(cells.items()):
        if set(sides)!={"over","under"}:
            continue
        quotes.append(TwoWayQuote(
            fixture_id=fid,market_key="GOALS_TOTAL",bookmaker=book,line=GOAL_LINE,
            over_odds=float(sides["over"]),under_odds=float(sides["under"]),
            observed_at=float(obs),bundle_id=f"{obs:.6f}:{raw_hash}"))
    return quotes

def _selected_surface(records: Iterable[CaptureRecord], fid: str, selection_time: float, max_age: float, *, strict_before: bool):
    quotes=[q for q in _quotes_from_records(records,fid)
            if (q.observed_at<float(selection_time) if strict_before else q.observed_at<=float(selection_time))
            and float(selection_time)-q.observed_at<=float(max_age)]
    selected=select_benchmark_bundle(quotes,prediction_cutoff=float(selection_time),
                                     market_key="GOALS_TOTAL",minimum_adjacent_lines=1)
    if not selected:
        return None,None
    if len(selected)!=1:
        raise PriceMovementScientificAbort("single-line goals bundle selection returned multiple quotes")
    surface=build_market_point(selected[0],prediction_cutoff=float(selection_time))
    if not surface.is_ok:
        return selected[0],None
    return selected[0],surface

def _observation_verified(movement_root: Path, fid: str, quote: TwoWayQuote) -> bool:
    raw_hash=quote.bundle_id.split(":",1)[1]
    path=movement_root/"observations"/fid/f"{int(quote.observed_at*1_000_000):020d}_{raw_hash}.json"
    if not path.exists():
        return False
    value=_read_json(path)
    return value.get("schedule_verified") is True and value.get("raw_payload_hash")==raw_hash

def _abstain_close(movement_root: Path, fid: str, reason: str, event_time: float, now: float, detail: str|None=None):
    value={"version":"qfe-prospective-operational-close-v1","protocol_hash":PRICE_PROTOCOL_HASH,
           "amendment_hash":PRICE_AMENDMENT_HASH,"cohort_hash":COHORT_HASH,"fixture_id":fid,
           "event_time":float(event_time),"status":"ABSTAIN","reason":reason,
           "finalized_at":float(now),"detail":detail}
    value["close_hash"]=sha256_json(value)
    _immutable_json(_close_path(movement_root,fid),value)
    return value

def _finalize_movement(*, movement_root: Path, cohort_root: Path, identity: Mapping[str,Any],
                       close: dict[str,Any], now: float) -> dict[str,Any]:
    fid=str(identity["fixture_id"])
    path=_movement_path(movement_root,fid)
    if path.exists():
        return _read_json(path)
    cutoff=float(identity["event_time"])-HORIZON
    entry_store=CaptureStore(cohort_root/"market"/"captures.jsonl.gz")
    entry_quote,entry_surface=_selected_surface(entry_store.read_all(),fid,cutoff,1800,strict_before=False)
    if entry_quote is None or entry_surface is None:
        value={"version":"qfe-prospective-market-movement-v1","protocol_hash":PRICE_PROTOCOL_HASH,
               "fixture_id":fid,"status":"ABSTAIN","reason":"ENTRY_MARKET_MISSING_OR_INVALID",
               "finalized_at":float(now),"close_hash":close["close_hash"]}
    else:
        ep=entry_surface.points[0]
        value={"version":"qfe-prospective-market-movement-v1","protocol_hash":PRICE_PROTOCOL_HASH,
               "fixture_id":fid,"status":"OK","finalized_at":float(now),
               "entry":{"bookmaker":entry_surface.bookmaker,"bundle_id":entry_surface.bundle_id,
                        "observed_at":entry_surface.observed_at_max,"over_odds":ep.over_odds,
                        "under_odds":ep.under_odds,"overround":ep.overround,"no_vig_p_over":ep.p_over_clean},
               "close":{"close_hash":close["close_hash"],"bookmaker":close["bookmaker"],
                        "bundle_id":close["bundle_id"],"observed_at":close["observed_at"],
                        "over_odds":close["over_odds"],"under_odds":close["under_odds"],
                        "overround":close["overround"],"no_vig_p_over":close["no_vig_p_over"]},
               "movement":{"delta_no_vig_p_over":float(close["no_vig_p_over"])-float(ep.p_over_clean),
                           "delta_over_decimal_odds":float(close["over_odds"])-float(ep.over_odds),
                           "delta_under_decimal_odds":float(close["under_odds"])-float(ep.under_odds)}}
    value["movement_hash"]=sha256_json(value)
    _immutable_json(path,value)
    return value

def _finalize_close(*, movement_root: Path, cohort_root: Path, identity: Mapping[str,Any], now: float):
    fid=str(identity["fixture_id"]); event_time=float(identity["event_time"])
    existing=_close_path(movement_root,fid)
    if existing.exists():
        return _read_json(existing)
    schedule_abstain=movement_root/"status"/fid/"SCHEDULE_ABSTAIN.json"
    if schedule_abstain.exists():
        val=_read_json(schedule_abstain)
        return _abstain_close(movement_root,fid,val["reason"],event_time,now,val.get("detail"))
    movement_store=CaptureStore(movement_root/"captures.jsonl.gz")
    close_quote,close_surface=_selected_surface(movement_store.read_all(),fid,event_time,MAX_CLOSE_AGE,strict_before=True)
    if close_quote is None:
        return _abstain_close(movement_root,fid,"CLOSE_MARKET_MISSING",event_time,now)
    if not _observation_verified(movement_root,fid,close_quote):
        return _abstain_close(movement_root,fid,"CLOSE_SCHEDULE_VERIFICATION_MISSING",event_time,now)
    if close_surface is None:
        return _abstain_close(movement_root,fid,"CLOSE_MARKET_INVALID",event_time,now)
    point=close_surface.points[0]
    close={"version":"qfe-prospective-operational-close-v1","protocol_hash":PRICE_PROTOCOL_HASH,
           "amendment_hash":PRICE_AMENDMENT_HASH,"cohort_hash":COHORT_HASH,"fixture_id":fid,
           "event_time":event_time,"status":"OK","finalized_at":float(now),
           "bookmaker":close_surface.bookmaker,"bundle_id":close_surface.bundle_id,
           "observed_at":close_surface.observed_at_max,
           "age_to_kickoff_seconds":event_time-close_surface.observed_at_max,
           "over_odds":point.over_odds,"under_odds":point.under_odds,
           "overround":point.overround,"no_vig_p_over":point.p_over_clean,"shin_p_over":point.p_over_shin}
    close["close_hash"]=sha256_json(close)
    _immutable_json(existing,close)
    _finalize_movement(movement_root=movement_root,cohort_root=cohort_root,identity=identity,close=close,now=now)
    return close

def _write_schedule_abstain(movement_root: Path, fid: str, reason: str, now: float):
    path=movement_root/"status"/fid/"SCHEDULE_ABSTAIN.json"
    value={"fixture_id":fid,"reason":reason,"observed_at":float(now),"protocol_hash":PRICE_PROTOCOL_HASH}
    value["status_hash"]=sha256_json(value)
    _immutable_json(path,value)

def run_price_movement_cycle(
    *,
    repo_root: Path,
    cohort_root: Path,
    movement_root: Path,
    client: ProspectiveApiClient,
    now_fn: Callable[[],float]=time.time,
) -> dict[str,Any]:
    repo_root=Path(repo_root); cohort_root=Path(cohort_root); movement_root=Path(movement_root)
    protocol,cohort,identities=_load_bound_evidence(repo_root)
    expected=Path(protocol["artifacts"]["root"])
    if movement_root!=expected:
        raise PriceMovementScientificAbort(f"movement root mismatch: {movement_root} != {expected}")
    now=float(now_fn())
    captured=[]; finalized=[]; schedule_abstained=[]
    for row in cohort["fixtures"]:
        fid=str(row["fixture_id"])
        identity=identities[fid]
        event_time=float(row["event_time"])
        cutoff=event_time-HORIZON
        if not _prediction_path(cohort_root,fid).exists():
            continue
        if _close_path(movement_root,fid).exists():
            continue
        if now<cutoff:
            continue
        if now>=event_time:
            finalized.append(_finalize_close(
                movement_root=movement_root,cohort_root=cohort_root,identity=identity,now=now))
            continue
        if (movement_root/"status"/fid/"SCHEDULE_ABSTAIN.json").exists():
            continue
        try:
            result=_capture_movement_odds(
                client=client,movement_root=movement_root,identity=identity,cutoff=cutoff,now_fn=now_fn)
        except Exception as exc:
            captured.append({"fixture_id":fid,"status":"CAPTURE_ERROR","detail":f"{type(exc).__name__}: {exc}"})
            continue
        captured.append(result)
        if str(result.get("status","")).startswith("SCHEDULE_"):
            _write_schedule_abstain(movement_root,fid,str(result["status"]),float(now_fn()))
            schedule_abstained.append(fid)
    value={"version":"qfe-prospective-price-movement-cycle-v1","protocol_hash":PRICE_PROTOCOL_HASH,
           "amendment_hash":PRICE_AMENDMENT_HASH,"cohort_hash":COHORT_HASH,"started_at":now,
           "captured":captured,"finalized":finalized,"schedule_abstained_fixture_ids":schedule_abstained}
    value["cycle_hash"]=sha256_json(value)
    _immutable_json(movement_root/"cycles"/f"{int(now*1_000_000):020d}_{value['cycle_hash']}.json",value)
    return value

@contextmanager
def scanner_lock(path: Path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fh=open(path,"a+")
    try:
        fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise RuntimeError("price movement scanner lock already held")
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(),fcntl.LOCK_UN)
        fh.close()
