"""Deterministic future-cohort freezer for QFE Prospective V1."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.layer5.prospective_manifest import (
    COHORT_STATUS,
    COHORT_VERSION,
    validate_prospective_cohort_manifest,
)
from src.research.prospective.api_contract import Endpoint
from src.research.prospective.capture import ProspectiveApiClient

COHORT_PROTOCOL_HASH="8bb6425442713834990b4419f4bcfd799ef75db61d8129b59bd2d635c4c6893e"
DISCOVERY_VERSION="qfe-prospective-cohort-discovery-v1"
SCHEDULED_STATES={"scheduled","upcoming","not_started","timed","fixture"}


@dataclass(frozen=True,slots=True)
class FrozenFixtureIdentity:
    fixture_id:str
    event_time:float
    competition_ref:str
    season_ref:str
    home_team_ref:str
    away_team_ref:str
    home_team_name:str
    away_team_name:str

    def to_dict(self)->dict[str,Any]:
        return asdict(self)


def _parse_ts(value:Any)->float:
    text=str(value or "")
    if text.endswith("Z"): text=text[:-1]+"+00:00"
    dt=datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("fixture utc_date must be timezone-aware")
    return dt.timestamp()


def _iso(ts:float)->str:
    return datetime.fromtimestamp(float(ts),timezone.utc).isoformat()


def _sha_payload(value:Any)->str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _immutable_json(path:Path,value:Any)->None:
    payload=(canonical_json(value)+"\n").encode()
    if path.exists():
        if path.read_bytes()!=payload:
            raise FileExistsError(f"frozen cohort artifact differs: {path}")
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(payload)


def _status(fx:dict[str,Any])->str:
    value=fx.get("status")
    if isinstance(value,dict):
        value=value.get("type") or value.get("name") or value.get("status")
    return str(value or "").lower()


def _identity(fx:dict[str,Any],expected_comp:str,expected_season:str)->FrozenFixtureIdentity:
    fid=str(fx.get("id") or "")
    if not fid:
        raise ValueError("scheduled fixture missing id")
    comp=str(fx.get("competition_id") or (fx.get("competition") or {}).get("id") or "")
    season=str(fx.get("season_id") or (fx.get("season") or {}).get("id") or "")
    if comp!=expected_comp or season!=expected_season:
        raise ValueError(f"fixture competition/season drift: {fid}")
    h=fx.get("home_team") or {}; a=fx.get("away_team") or {}
    href=str(h.get("id") or ""); aref=str(a.get("id") or "")
    hname=str(h.get("name") or ""); aname=str(a.get("name") or "")
    if not href or not aref or not hname or not aname:
        raise ValueError(f"scheduled fixture team identity incomplete: {fid}")
    return FrozenFixtureIdentity(
        fid,_parse_ts(fx.get("utc_date")),comp,season,href,aref,hname,aname
    )


def build_future_cohort(
    *,
    repo_root:Path,
    output_root:Path,
    client:ProspectiveApiClient,
    now_fn:Callable[[],float]=time.time,
)->tuple[dict[str,Any],dict[str,Any],tuple[FrozenFixtureIdentity,...]]:
    repo_root=Path(repo_root)
    protocol=json.loads((repo_root/"evidence/prospective_v1/QFE_PROSPECTIVE_COHORT_PROTOCOL_V1.json").read_text())
    if protocol.get("protocol_hash")!=COHORT_PROTOCOL_HASH:
        raise ValueError("cohort protocol binding mismatch")
    if not client.is_configured and client.transport is None:
        raise ValueError("TheStatsAPI client is not configured")

    start=datetime.fromisoformat(protocol["window"]["kickoff_start_utc"]).timestamp()
    end=datetime.fromisoformat(protocol["window"]["kickoff_end_utc_exclusive"]).timestamp()
    discovery_started=float(now_fn())
    discovery_id=datetime.fromtimestamp(discovery_started,timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root=Path(output_root)/discovery_id
    root.mkdir(parents=True,exist_ok=False)

    raw_records=[]; identities={}
    request_count=0
    for comp,season in sorted(protocol["competition_seasons"].items()):
        page=1
        while True:
            params={
                "competition_id":comp,
                "season_id":season,
                "status":"scheduled",
                "per_page":100,
                "page":page,
            }
            body=client.get(Endpoint.MATCHES,params=params)
            retrieved=float(now_fn())
            request_count+=1
            if not isinstance(body,dict):
                raise RuntimeError(f"scheduled discovery failed for {comp} page {page}")
            rel=f"raw/discovery_{comp}_{season}_p{page}.json"
            _immutable_json(root/rel,body)
            ph=_sha_payload(body)
            raw_records.append({
                "competition_id":comp,"season_id":season,"page":page,
                "retrieved_at":retrieved,"payload_sha256":ph,"relative_path":rel,
                "request_params":params,
            })
            rows=body.get("data") or []
            if not isinstance(rows,list):
                raise RuntimeError(f"scheduled discovery rows invalid for {comp} page {page}")
            for fx in rows:
                if not isinstance(fx,dict):
                    raise RuntimeError("non-object scheduled fixture row")
                status=_status(fx)
                if status and status not in SCHEDULED_STATES:
                    raise RuntimeError(f"non-scheduled row returned from scheduled query: {fx.get('id')} {status}")
                ident=_identity(fx,comp,season)
                if not (start<=ident.event_time<end):
                    continue
                old=identities.get(ident.fixture_id)
                if old is not None and old!=ident:
                    raise RuntimeError(f"conflicting duplicate scheduled fixture {ident.fixture_id}")
                identities[ident.fixture_id]=ident
            meta=body.get("metadata") or body.get("meta") or {}
            total_pages=int(meta.get("total_pages") or meta.get("last_page") or 1)
            if total_pages<page:
                raise RuntimeError("scheduled discovery invalid page metadata")
            if page>=total_pages:
                break
            page+=1

    frozen_at=float(now_fn())
    ordered=tuple(sorted(identities.values(),key=lambda x:(x.event_time,x.fixture_id)))
    if not ordered:
        raise RuntimeError("Prospective Cohort V1 window contains no scheduled fixtures")
    violating=[x.fixture_id for x in ordered if frozen_at>x.event_time-21600]
    if violating:
        raise RuntimeError("cohort freeze occurred inside T-6h for included fixture(s): "+",".join(violating[:10]))

    base={
        "version":COHORT_VERSION,
        "status":COHORT_STATUS,
        "frozen_at":_iso(frozen_at),
        "fixtures":[{"fixture_id":x.fixture_id,"event_time":x.event_time} for x in ordered],
    }
    cohort={**base,"cohort_hash":sha256_json(base)}
    validate_prospective_cohort_manifest(cohort)

    identity_rows=[x.to_dict() for x in ordered]
    discovery={
        "version":DISCOVERY_VERSION,
        "protocol_hash":COHORT_PROTOCOL_HASH,
        "discovery_id":discovery_id,
        "discovery_started_at":discovery_started,
        "frozen_at":frozen_at,
        "window_start":start,
        "window_end_exclusive":end,
        "request_count":request_count,
        "raw_records":raw_records,
        "raw_records_hash":sha256_json(raw_records),
        "fixture_identity_rows":identity_rows,
        "fixture_identity_hash":sha256_json(identity_rows),
        "cohort_size":len(ordered),
        "cohort_hash":cohort["cohort_hash"],
        "market_data_used":False,
        "model_predictions_used":False,
        "outcomes_used":False,
    }
    discovery["discovery_hash"]=sha256_json(discovery)
    _immutable_json(root/"cohort.json",cohort)
    _immutable_json(root/"fixture_identities.json",identity_rows)
    _immutable_json(root/"discovery_manifest.json",discovery)
    return cohort,discovery,ordered


def load_frozen_cohort(root:Path)->tuple[dict[str,Any],dict[str,Any],tuple[FrozenFixtureIdentity,...]]:
    root=Path(root)
    cohort=json.loads((root/"cohort.json").read_text())
    validate_prospective_cohort_manifest(cohort)
    discovery=json.loads((root/"discovery_manifest.json").read_text())
    expected=discovery.pop("discovery_hash",None)
    if sha256_json(discovery)!=expected:
        raise ValueError("cohort discovery manifest hash mismatch")
    discovery={**discovery,"discovery_hash":expected}
    if discovery["cohort_hash"]!=cohort["cohort_hash"]:
        raise ValueError("cohort/discovery hash binding mismatch")
    rows=json.loads((root/"fixture_identities.json").read_text())
    if sha256_json(rows)!=discovery["fixture_identity_hash"]:
        raise ValueError("fixture identity hash mismatch")
    identities=tuple(FrozenFixtureIdentity(**x) for x in rows)
    if [(x.fixture_id,x.event_time) for x in identities] != [
        (x["fixture_id"],float(x["event_time"])) for x in cohort["fixtures"]
    ]:
        raise ValueError("identity rows do not match frozen cohort membership/order")
    for rec in discovery["raw_records"]:
        body=json.loads((root/rec["relative_path"]).read_text())
        if _sha_payload(body)!=rec["payload_sha256"]:
            raise ValueError("raw scheduled-discovery payload hash mismatch")
    return cohort,discovery,identities
