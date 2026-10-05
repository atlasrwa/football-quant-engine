"""QFE Prospective V1 T-6h execution runner."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import build_multiseason_pit_corpus
from src.research.dataset.pit import PITDatasetSpec
from src.research.prospective.api_contract import Endpoint
from src.research.prospective.capture import CaptureRecord, ProspectiveApiClient
from src.research.prospective.incremental_history import build_incremental_history_snapshot
from src.research.prospective.odds_capture import OddsSemantics, extract_prices
from src.research.prospective.prediction_freeze import (
    COMPETITION_UNIVERSE,
    build_prospective_prediction_bundle,
)
from src.research.prospective.storage import CaptureStore

RUNNER_PROTOCOL_HASH = "08e87b0a7ca4922a67f699c0ae57336a377548438066fd7fa3ecf6eb78e1fdc0"
RUNNER_AMENDMENT_HASH = "e43ff668c756b35c35970a16f0d11c311798d43bea11c9bac50b1c2c4bc4a575"
COHORT_HASH = "f3d5bb667f8849b33baf29fb9666400427a17c4cf02f47e9dc0e0a098af6f8f0"
BASE_CORPUS_MANIFEST_HASH = "bde8a51688674f0ca5d7b17426327cc55d5d44ce4106443eb1a2f5b780419e22"
PREDICTION_LEAD_MIN = 1200
PREDICTION_LEAD_MAX = 1800
MARKET_WINDOW = 1800
HORIZON = 21600
SCHEDULED_STATES = {"scheduled","upcoming","not_started","timed","fixture"}

class RunnerScientificAbort(RuntimeError):
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
            raise FileExistsError(f"immutable runner artifact differs: {path}")
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(payload)

def _sha_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def _parse_ts(value: Any) -> float:
    text=str(value or "")
    if text.endswith("Z"):
        text=text[:-1]+"+00:00"
    dt=datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.timestamp()

def _status_value(body: Mapping[str,Any]) -> str:
    value=body.get("status")
    if isinstance(value,Mapping):
        value=value.get("type") or value.get("name") or value.get("status")
    return str(value or "").lower()

def _unwrap(body: Any) -> dict[str,Any]:
    if not isinstance(body,dict):
        raise ValueError("provider detail payload is not an object")
    data=body.get("data",body)
    if not isinstance(data,dict):
        raise ValueError("provider detail data is not an object")
    return data

def _load_bound_evidence(repo_root: Path):
    protocol=_read_json(repo_root/"evidence/prospective_v1/QFE_T6_RUNNER_PROTOCOL_V1.json")
    amendment=_read_json(repo_root/"evidence/prospective_v1/QFE_T6_RUNNER_PROTOCOL_V1_AMENDMENT_A.json")
    if protocol.get("protocol_hash")!=RUNNER_PROTOCOL_HASH:
        raise RunnerScientificAbort("runner protocol binding mismatch")
    if amendment.get("amendment_hash")!=RUNNER_AMENDMENT_HASH:
        raise RunnerScientificAbort("runner amendment binding mismatch")
    cohort=_read_json(repo_root/"evidence/prospective_v1/QFE_PROSPECTIVE_COHORT_V1.json")
    if cohort.get("cohort_hash")!=COHORT_HASH:
        raise RunnerScientificAbort("cohort binding mismatch")
    discovery=_read_json(repo_root/"evidence/prospective_v1/QFE_PROSPECTIVE_COHORT_DISCOVERY_V1.json")
    if discovery.get("cohort_hash")!=COHORT_HASH:
        raise RunnerScientificAbort("cohort discovery binding mismatch")
    rows=discovery.get("fixture_identity_rows")
    if not isinstance(rows,list) or sha256_json(rows)!=discovery.get("fixture_identity_hash"):
        raise RunnerScientificAbort("cohort fixture identity binding mismatch")
    identities={str(x["fixture_id"]):dict(x) for x in rows}
    if set(identities)!={str(x["fixture_id"]) for x in cohort["fixtures"]}:
        raise RunnerScientificAbort("cohort identity membership mismatch")
    return protocol,cohort,identities

def _target_from_identity(x: Mapping[str,Any]) -> ResearchMatch:
    return ResearchMatch(
        match_id=str(x["fixture_id"]),
        date_unix=int(float(x["event_time"])),
        league_id=str(x["competition_ref"]),
        season=str(x["season_ref"]),
        home_team=str(x["home_team_name"]),
        away_team=str(x["away_team_name"]),
        source_provider="THESTATSAPI",
        source_match_ref=str(x["fixture_id"]),
        competition_ref=str(x["competition_ref"]),
        season_ref=str(x["season_ref"]),
        home_team_ref=str(x["home_team_ref"]),
        away_team_ref=str(x["away_team_ref"]),
    )

def _attempt_path(root: Path, fid: str) -> Path:
    return root/"status"/fid/"ATTEMPT_STARTED.json"

def _prediction_path(root: Path, fid: str) -> Path:
    return root/"predictions"/f"{fid}.json"

def _terminal_path(root: Path, fid: str, code: str) -> Path:
    return root/"status"/fid/f"{code}.json"

def _event_status(root: Path, fid: str, code: str, now: float, detail: str|None=None) -> None:
    payload={"fixture_id":fid,"code":code,"observed_at":float(now),"detail":detail}
    payload["event_hash"]=sha256_json(payload)
    stamp=f"{int(now*1_000_000):020d}"
    _immutable_json(root/"status"/fid/f"{stamp}_{code}.json",payload)

def _terminal_status(root: Path, fid: str, code: str, now: float, detail: str|None=None) -> None:
    marker=root/"status"/fid/"TERMINAL.json"
    if marker.exists():
        return
    payload={"fixture_id":fid,"code":code,"observed_at":float(now),"detail":detail}
    payload["event_hash"]=sha256_json(payload)
    _immutable_json(_terminal_path(root,fid,code),payload)
    _immutable_json(marker,payload)

def _load_base_history(base_dir: Path) -> tuple[ResearchMatch,...]:
    corpus=build_multiseason_pit_corpus(
        base_dir=Path(base_dir),
        pit_spec=PITDatasetSpec(decision_horizon_seconds=HORIZON),
    )
    if corpus.manifest.manifest_hash!=BASE_CORPUS_MANIFEST_HASH:
        raise RunnerScientificAbort("canonical base corpus manifest mismatch")
    return tuple(corpus.matches)

def _combine_history(base: Iterable[ResearchMatch], incremental: Iterable[ResearchMatch]) -> tuple[ResearchMatch,...]:
    a=tuple(base); b=tuple(incremental)
    ka={m.stable_fixture_key for m in a}
    kb={m.stable_fixture_key for m in b}
    overlap=ka & kb
    if overlap:
        raise RunnerScientificAbort(f"base/incremental history overlap: {sorted(overlap)[:3]}")
    out=tuple(sorted(a+b,key=lambda m:(int(m.date_unix),m.stable_fixture_key or "")))
    return out

def _verify_schedule(client: ProspectiveApiClient, identity: Mapping[str,Any], cutoff: float, now_fn: Callable[[],float]):
    fid=str(identity["fixture_id"])
    body=client.get(Endpoint.MATCH_DETAIL,match_id=fid)
    observed=float(now_fn())
    if observed>cutoff:
        return False,"SCHEDULE_CHECK_AFTER_CUTOFF",observed
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

def _prediction_envelope(
    *,
    fid: str,
    cutoff: float,
    generated_at: float,
    history_snapshot_hash: str,
    prediction_bundle: dict[str,Any],
) -> dict[str,Any]:
    value={
        "version":"qfe-prospective-t6-prediction-envelope-v1",
        "runner_protocol_hash":RUNNER_PROTOCOL_HASH,
        "runner_amendment_hash":RUNNER_AMENDMENT_HASH,
        "cohort_hash":COHORT_HASH,
        "fixture_id":fid,
        "prediction_cutoff":float(cutoff),
        "prediction_generated_at":float(generated_at),
        "history_snapshot_hash":history_snapshot_hash,
        "prediction_bundle_hash":prediction_bundle["bundle_hash"],
        "prediction_bundle":prediction_bundle,
    }
    value["envelope_hash"]=sha256_json(value)
    return value

def _capture_goal_odds(
    *,
    client: ProspectiveApiClient,
    root: Path,
    identity: Mapping[str,Any],
    cutoff: float,
    now_fn: Callable[[],float],
) -> dict[str,Any]:
    fid=str(identity["fixture_id"])
    body=client.get(Endpoint.MATCH_ODDS,match_id=fid)
    observed=float(now_fn())
    if observed>cutoff:
        return {"fixture_id":fid,"status":"LATE","observed_at":observed,"records_appended":0}
    if cutoff-observed>MARKET_WINDOW:
        return {"fixture_id":fid,"status":"TOO_EARLY","observed_at":observed,"records_appended":0}
    if body is None or not isinstance(body,dict):
        return {"fixture_id":fid,"status":"MISSING","observed_at":observed,"records_appended":0}
    ph=_sha_payload(body)
    raw_path=root/"market"/"raw"/fid/f"{int(observed*1_000_000):020d}_{ph}.json"
    _immutable_json(raw_path,body)
    prices=extract_prices(
        body,
        payload_hash=ph,
        field="last_seen",
        semantics=OddsSemantics.PROSPECTIVE_SNAPSHOT,
        observed_at=observed,
        markets=("total_goals",),
        team_markets=(),
    )
    store=CaptureStore(root/"market"/"captures.jsonl.gz")
    records=[]
    for p in prices:
        if p.line is None or abs(float(p.line)-2.5)>1e-9:
            continue
        if p.selection not in {"over","under"}:
            continue
        concept=f"odds:total_goals:{p.selection}:2.5:{p.bookmaker}"
        records.append(CaptureRecord(
            provider="thestatsapi",
            provider_entity_id=fid,
            canonical_entity_id=fid,
            concept=concept,
            value=float(p.decimal_odds),
            event_time=float(identity["event_time"]),
            observed_at=observed,
            retrieved_at=observed,
            forecast_cutoff=float(cutoff),
            raw_payload_hash=ph,
            raw_status="PROSPECTIVE_SNAPSHOT",
            vintage="T6",
        ))
    appended=store.extend(records)
    return {
        "fixture_id":fid,
        "status":"CAPTURED" if records else "NO_REGISTERED_GOAL_QUOTES",
        "observed_at":observed,
        "raw_payload_hash":ph,
        "raw_path":str(raw_path),
        "registered_records":len(records),
        "records_appended":appended,
    }

def run_t6_cycle(
    *,
    repo_root: Path,
    output_root: Path,
    history_snapshot_root: Path,
    base_data_dir: Path,
    client: ProspectiveApiClient,
    now_fn: Callable[[],float]=time.time,
    history_builder: Callable[...,Any]=build_incremental_history_snapshot,
    base_loader: Callable[[Path],tuple[ResearchMatch,...]]=_load_base_history,
    prediction_builder: Callable[...,dict[str,Any]]=build_prospective_prediction_bundle,
) -> dict[str,Any]:
    repo_root=Path(repo_root); root=Path(output_root)
    protocol,cohort,identities=_load_bound_evidence(repo_root)
    expected_root=Path(protocol["operational_artifacts"]["root"])
    if root!=expected_root:
        raise RunnerScientificAbort(f"output root mismatch: {root} != {expected_root}")
    root.mkdir(parents=True,exist_ok=True)
    now=float(now_fn())
    due=[]
    missed=[]
    for row in cohort["fixtures"]:
        fid=str(row["fixture_id"]); cutoff=float(row["event_time"])-HORIZON
        pp=_prediction_path(root,fid)
        if pp.exists():
            continue
        if (root/"status"/fid/"TERMINAL.json").exists():
            continue
        delta=cutoff-now
        attempted=_attempt_path(root,fid).exists()
        if delta<0:
            _terminal_status(root,fid,"MISSED_T6",now)
            missed.append(fid); continue
        if delta<PREDICTION_LEAD_MIN and not attempted:
            _terminal_status(root,fid,"MISSED_EXECUTION_WINDOW",now)
            missed.append(fid); continue
        if PREDICTION_LEAD_MIN<=delta<=PREDICTION_LEAD_MAX or (attempted and delta>=0):
            if not attempted:
                _immutable_json(_attempt_path(root,fid),{
                    "fixture_id":fid,"attempt_started_at":now,"prediction_cutoff":cutoff,
                    "runner_protocol_hash":RUNNER_PROTOCOL_HASH,
                })
            due.append((cutoff,fid))
    due.sort()

    history_manifest=None
    history=()
    predicted=[]
    schedule_abstained=[]
    if due:
        base=base_loader(Path(base_data_dir))
        try:
            history_manifest,incremental=history_builder(
                repo_root=repo_root,
                output_root=Path(history_snapshot_root),
                client=client,
                now_fn=now_fn,
            )
        except Exception as exc:
            for cutoff,fid in due:
                _event_status(root,fid,"HISTORY_REFRESH_ERROR",float(now_fn()),f"{type(exc).__name__}: {exc}")
            return _write_cycle_summary(root,now,due,missed,[],[],history_manifest,["HISTORY_REFRESH_ERROR"])
        if not history_manifest.get("prediction_eligible"):
            for cutoff,fid in due:
                _event_status(root,fid,"HISTORY_INCOMPLETE",float(now_fn()))
            return _write_cycle_summary(root,now,due,missed,[],[],history_manifest,["HISTORY_INCOMPLETE"])
        min_cutoff=min(x[0] for x in due)
        if float(history_manifest["completed_at"])>min_cutoff:
            for cutoff,fid in due:
                _terminal_status(root,fid,"HISTORY_COMPLETED_AFTER_CUTOFF",float(now_fn()))
            return _write_cycle_summary(root,now,due,missed,[],[],history_manifest,["HISTORY_LATE"])
        history=_combine_history(base,incremental)

        # Phase 1: schedule verification and ALL predictions. No odds requests occur here.
        for cutoff,fid in due:
            current=float(now_fn())
            if current>cutoff:
                _terminal_status(root,fid,"MISSED_T6",current)
                continue
            ok,reason,_=_verify_schedule(client,identities[fid],cutoff,now_fn)
            if not ok:
                _terminal_status(root,fid,reason or "SCHEDULE_ABSTAIN",float(now_fn()))
                schedule_abstained.append(fid)
                continue
            target=_target_from_identity(identities[fid])
            try:
                bundle=prediction_builder(
                    repo_root=repo_root,
                    history_matches=history,
                    target_match=target,
                    cohort_manifest=cohort,
                    history_snapshot_hash=str(history_manifest["snapshot_hash"]),
                    history_snapshot_captured_at=float(history_manifest["completed_at"]),
                    history_snapshot_competitions=history_manifest["competition_universe"],
                )
            except Exception as exc:
                msg=f"{type(exc).__name__}: {exc}"
                fatal_tokens=("binding mismatch","protocol binding","forbidden","outside frozen competition",
                              "target leaked","duplicate history","provider mismatch","history snapshot does not cover")
                if any(x in str(exc).lower() for x in fatal_tokens):
                    raise RunnerScientificAbort(msg) from exc
                _event_status(root,fid,"PREDICTION_ERROR",float(now_fn()),msg)
                continue
            generated=float(now_fn())
            if generated>cutoff:
                _terminal_status(root,fid,"PREDICTION_FINISHED_AFTER_CUTOFF",generated)
                continue
            envelope=_prediction_envelope(
                fid=fid,cutoff=cutoff,generated_at=generated,
                history_snapshot_hash=str(history_manifest["snapshot_hash"]),
                prediction_bundle=bundle,
            )
            _immutable_json(_prediction_path(root,fid),envelope)
            predicted.append(fid)

    # Phase 2: odds capture. Only fixtures with a frozen prediction can enter.
    market=[]
    market_now=float(now_fn())
    for row in cohort["fixtures"]:
        fid=str(row["fixture_id"]); cutoff=float(row["event_time"])-HORIZON
        if not _prediction_path(root,fid).exists():
            continue
        delta=cutoff-market_now
        if 0<=delta<=MARKET_WINDOW:
            try:
                result=_capture_goal_odds(
                    client=client,root=root,identity=identities[fid],
                    cutoff=cutoff,now_fn=now_fn,
                )
                market.append(result)
                if result["status"]!="CAPTURED":
                    _event_status(root,fid,"MARKET_"+result["status"],float(now_fn()))
            except Exception as exc:
                _event_status(root,fid,"MARKET_CAPTURE_ERROR",float(now_fn()),f"{type(exc).__name__}: {exc}")

    return _write_cycle_summary(root,now,due,missed,predicted,market,history_manifest,schedule_abstained)

def _write_cycle_summary(root,started,due,missed,predicted,market,history_manifest,notes):
    finished=time.time()
    value={
        "version":"qfe-prospective-t6-cycle-v1",
        "runner_protocol_hash":RUNNER_PROTOCOL_HASH,
        "runner_amendment_hash":RUNNER_AMENDMENT_HASH,
        "cohort_hash":COHORT_HASH,
        "started_at":float(started),
        "finished_at":float(finished),
        "due_fixture_ids":[x[1] for x in due],
        "missed_fixture_ids":list(missed),
        "predicted_fixture_ids":list(predicted),
        "market_results":list(market),
        "history_snapshot_hash":history_manifest.get("snapshot_hash") if history_manifest else None,
        "notes":list(notes),
    }
    value["cycle_hash"]=sha256_json(value)
    path=root/"cycles"/f"{int(started*1_000_000):020d}_{value['cycle_hash']}.json"
    _immutable_json(path,value)
    return value

@contextmanager
def runner_lock(lock_path: Path):
    lock_path=Path(lock_path)
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    fh=open(lock_path,"a+")
    try:
        fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise RuntimeError("T6 runner lock already held")
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(),fcntl.LOCK_UN)
        fh.close()
