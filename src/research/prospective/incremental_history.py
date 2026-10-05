"""Immutable live incremental football-history snapshot for QFE Prospective V1."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.prospective.api_contract import Endpoint
from src.research.prospective.capture import ProspectiveApiClient
from src.research.thestatsapi.adapter import TheStatsAPIDataSource

PROTOCOL_HASH = "3cb61328740d2d9bc3af93a097c2f04358fda2f9878ad1eb3da04d6c38ab663a"
SNAPSHOT_VERSION = "qfe-prospective-incremental-history-snapshot-v1"
DEFAULT_HARD_REQUEST_CAP = 500
DEFAULT_QUOTA_RESERVE = 100


@dataclass(frozen=True, slots=True)
class RawPayloadRecord:
    kind: str
    competition_id: str
    season_id: str
    request_path: str
    request_params: dict[str, Any]
    fixture_id: str | None
    retrieved_at: float
    payload_sha256: str | None
    http_semantics: str
    relative_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _parse_utc_date(value: Any) -> int:
    text=str(value or "")
    if not text:
        raise ValueError("fixture missing utc_date")
    if text.endswith("Z"):
        text=text[:-1]+"+00:00"
    dt=datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("fixture utc_date must be timezone-aware")
    return int(dt.timestamp())


def _write_immutable_json(path: Path, value: Any) -> str:
    payload=(canonical_json(value)+"\n").encode()
    if path.exists():
        if path.read_bytes()!=payload:
            raise FileExistsError(f"incremental-history raw artifact differs: {path}")
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _rate_limit_dict(client: ProspectiveApiClient) -> dict[str,Any] | None:
    r=client.last_rate_limit
    if r is None:
        return None
    names=(
        "minute_limit","minute_remaining","minute_reset",
        "monthly_limit","monthly_remaining","monthly_reset",
        "minute_uncapped","monthly_uncapped",
    )
    return {name:getattr(r,name,None) for name in names}


def _competition_rows(protocol: dict[str,Any]) -> tuple[tuple[str,dict[str,Any]],...]:
    rows=protocol.get("competition_seasons")
    if not isinstance(rows,dict) or not rows:
        raise ValueError("incremental-history protocol missing competition seasons")
    return tuple((str(k),dict(v)) for k,v in sorted(rows.items()))


def _fixture_status(fx: dict[str,Any]) -> str:
    value=fx.get("status")
    if isinstance(value,dict):
        value=value.get("type") or value.get("name") or value.get("status")
    return str(value or "").lower()


def _fixture_comp(fx: dict[str,Any]) -> str:
    value=fx.get("competition_id")
    if value:
        return str(value)
    comp=fx.get("competition")
    if isinstance(comp,dict):
        return str(comp.get("id") or "")
    return ""


def _fixture_season(fx: dict[str,Any]) -> str:
    value=fx.get("season_id")
    if value:
        return str(value)
    season=fx.get("season")
    if isinstance(season,dict):
        return str(season.get("id") or "")
    return ""


def _score_available(fx: dict[str,Any]) -> bool:
    score=fx.get("score")
    if not isinstance(score,dict):
        return False
    home=score.get("home")
    away=score.get("away")
    # Provider payloads may use nested current score representation.
    if home is None:
        home=score.get("home_score") or score.get("ft_home")
    if away is None:
        away=score.get("away_score") or score.get("ft_away")
    return home is not None and away is not None


def _request(
    client: ProspectiveApiClient,
    *,
    endpoint: Endpoint,
    params: dict[str,Any] | None,
    path_args: dict[str,str] | None,
    now_fn: Callable[[],float],
) -> tuple[Any,float,dict[str,Any] | None]:
    body=client.get(endpoint,params=params or {},**(path_args or {}))
    retrieved=float(now_fn())
    return body,retrieved,_rate_limit_dict(client)


def build_incremental_history_snapshot(
    *,
    repo_root: Path,
    output_root: Path,
    client: ProspectiveApiClient,
    now_fn: Callable[[],float]=time.time,
    hard_request_cap: int=DEFAULT_HARD_REQUEST_CAP,
    quota_reserve: int=DEFAULT_QUOTA_RESERVE,
) -> tuple[dict[str,Any], tuple[ResearchMatch,...]]:
    repo_root=Path(repo_root)
    protocol=json.loads((repo_root/"evidence/prospective_v1/QFE_INCREMENTAL_HISTORY_PROTOCOL_V1.json").read_text())
    if protocol.get("protocol_hash")!=PROTOCOL_HASH:
        raise ValueError("incremental-history protocol binding mismatch")
    if not client.is_configured and client.transport is None:
        raise ValueError("TheStatsAPI client is not configured")

    started_at=float(now_fn())
    snapshot_id=datetime.fromtimestamp(started_at,timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root=Path(output_root)/snapshot_id
    if root.exists():
        raise FileExistsError(f"snapshot id already exists: {snapshot_id}")
    raw_root=root/"raw"
    raw_root.mkdir(parents=True,exist_ok=False)

    request_count=0
    payload_records: list[RawPayloadRecord]=[]
    discovery: dict[str,dict[str,Any]]={}
    retained_by_id: dict[str,dict[str,Any]]={}
    first_quota=None

    for comp,spec in _competition_rows(protocol):
        season=str(spec["season_id"])
        page=1
        comp_rows: dict[str,dict[str,Any]]={}
        page_records=[]
        while True:
            if request_count>=hard_request_cap:
                raise RuntimeError("incremental-history hard request cap reached during discovery")
            params={
                "competition_id":comp,
                "season_id":season,
                "stage":"regular",
                "status":"finished",
                "per_page":100,
                "page":page,
            }
            body,retrieved,quota=_request(
                client,endpoint=Endpoint.MATCHES,params=params,path_args=None,now_fn=now_fn
            )
            request_count+=1
            if first_quota is None:
                first_quota=quota
            if body is None or not isinstance(body,dict):
                raise RuntimeError(f"finished-fixture discovery failed for {comp} page {page}")
            rel=f"raw/discovery_{comp}_{season}_p{page}.json"
            payload_sha=_sha_payload(body)
            _write_immutable_json(root/rel,body)
            payload_records.append(RawPayloadRecord(
                "MATCHES",comp,season,Endpoint.MATCHES.value,params,None,retrieved,
                payload_sha,"HTTP_200_JSON",rel,
            ))
            rows=body.get("data") or []
            if not isinstance(rows,list):
                raise RuntimeError(f"invalid matches data for {comp} page {page}")
            for fx in rows:
                if not isinstance(fx,dict) or not fx.get("id"):
                    raise RuntimeError(f"invalid fixture row for {comp} page {page}")
                mid=str(fx["id"])
                prior=comp_rows.get(mid)
                if prior is not None and prior!=fx:
                    raise RuntimeError(f"conflicting duplicate fixture {mid}")
                comp_rows[mid]=fx
            meta=(body.get("metadata") or body.get("meta") or {})
            total_pages=int(meta.get("total_pages") or meta.get("last_page") or 1)
            if total_pages<page:
                raise RuntimeError(f"invalid total_pages for {comp}")
            page_records.append({"page":page,"rows":len(rows),"payload_sha256":payload_sha})
            if page>=total_pages:
                break
            page+=1

        base_last=int(spec["base_last_kickoff_ts"])
        retained=[]
        for mid,fx in sorted(comp_rows.items()):
            if _fixture_comp(fx) and _fixture_comp(fx)!=comp:
                raise RuntimeError(f"fixture {mid} competition drift")
            if _fixture_season(fx) and _fixture_season(fx)!=season:
                raise RuntimeError(f"fixture {mid} season drift")
            status=_fixture_status(fx)
            if status and status not in {"finished","complete","completed"}:
                raise RuntimeError(f"non-finished row returned by finished query: {mid} {status}")
            kickoff=_parse_utc_date(fx.get("utc_date"))
            if kickoff<=base_last or kickoff>started_at:
                continue
            if not _score_available(fx):
                raise RuntimeError(f"retained finished fixture lacks final score: {mid}")
            if mid in retained_by_id and retained_by_id[mid]!=fx:
                raise RuntimeError(f"fixture {mid} appears inconsistently across competitions")
            retained_by_id[mid]=fx
            retained.append(mid)
        discovery[comp]={
            "season_id":season,
            "base_last_kickoff_ts":base_last,
            "pages":page_records,
            "returned_unique_fixtures":len(comp_rows),
            "retained_incremental_fixture_ids":retained,
            "retained_incremental_fixture_count":len(retained),
        }

    planned_stats=len(retained_by_id)
    current_quota=_rate_limit_dict(client)
    if current_quota is None or current_quota.get("monthly_remaining") is None:
        raise RuntimeError("monthly quota remaining unavailable after discovery")
    if int(current_quota["monthly_remaining"]) < planned_stats + int(quota_reserve):
        raise RuntimeError(
            f"insufficient monthly quota for complete snapshot: "
            f"{current_quota['monthly_remaining']} < {planned_stats}+{quota_reserve}"
        )
    if request_count+planned_stats>hard_request_cap:
        raise RuntimeError("complete incremental snapshot would exceed hard request cap")

    stats_by_match={}
    stats_attempts=[]
    for mid in sorted(retained_by_id):
        fx=retained_by_id[mid]
        comp=_fixture_comp(fx)
        season=_fixture_season(fx)
        if request_count>=hard_request_cap:
            raise RuntimeError("incremental-history hard request cap reached during stats")
        body,retrieved,quota=_request(
            client,endpoint=Endpoint.MATCH_STATS,params=None,
            path_args={"match_id":mid},now_fn=now_fn,
        )
        request_count+=1
        if body is None:
            stats_attempts.append({
                "fixture_id":mid,"status":"HTTP_404_OR_MISSING","retrieved_at":retrieved
            })
            continue
        if not isinstance(body,dict):
            raise RuntimeError(f"invalid stats payload for {mid}")
        rel=f"raw/stats_{mid}.json"
        payload_sha=_sha_payload(body)
        _write_immutable_json(root/rel,body)
        payload_records.append(RawPayloadRecord(
            "MATCH_STATS",comp,season,Endpoint.MATCH_STATS.value,{},mid,retrieved,
            payload_sha,"HTTP_200_JSON",rel,
        ))
        stats_attempts.append({
            "fixture_id":mid,"status":"HTTP_200_JSON","retrieved_at":retrieved,
            "payload_sha256":payload_sha,"relative_path":rel,
        })
        stats_by_match[mid]=body

    missing_stats=sorted(set(retained_by_id)-set(stats_by_match))
    complete=not missing_stats and len(stats_by_match)==len(retained_by_id)

    normalized: tuple[ResearchMatch,...]=()
    normalization_error=None
    if complete:
        try:
            source=TheStatsAPIDataSource(
                fixtures=list(retained_by_id.values()),
                stats_by_match_ref=stats_by_match,
            )
            normalized=tuple(source.get_matches())
            normalized_by_ref={m.source_match_ref:m for m in normalized}
            if set(normalized_by_ref)!=set(retained_by_id):
                missing=sorted(set(retained_by_id)-set(normalized_by_ref))
                raise RuntimeError(f"normalizer did not emit every retained fixture: {missing[:10]}")
            normalized=tuple(sorted(normalized,key=lambda m:(m.date_unix,m.stable_fixture_key or "")))
        except Exception as exc:
            complete=False
            normalization_error=f"{type(exc).__name__}: {exc}"
            normalized=()

    completed_at=float(now_fn())
    quota_final=_rate_limit_dict(client)
    normalized_dicts=[m.to_dict() for m in normalized]
    manifest={
        "version":SNAPSHOT_VERSION,
        "protocol_hash":PROTOCOL_HASH,
        "snapshot_id":snapshot_id,
        "started_at":started_at,
        "completed_at":completed_at,
        "prediction_eligible":bool(complete),
        "competition_universe":[c for c,_ in _competition_rows(protocol)],
        "discovery":discovery,
        "discovery_payload_count":sum(1 for x in payload_records if x.kind=="MATCHES"),
        "incremental_fixture_count":len(retained_by_id),
        "stats_success_count":len(stats_by_match),
        "stats_missing_fixture_ids":missing_stats,
        "stats_attempts":stats_attempts,
        "request_count":request_count,
        "hard_request_cap":hard_request_cap,
        "quota_reserve":quota_reserve,
        "first_rate_limit":first_quota,
        "final_rate_limit":quota_final,
        "payload_records":[x.to_dict() for x in payload_records],
        "payload_records_hash":sha256_json([x.to_dict() for x in payload_records]),
        "normalized_match_count":len(normalized),
        "normalized_matches_hash":sha256_json(normalized_dicts) if normalized else None,
        "normalization_error":normalization_error,
        "market_data_used":False,
        "cohort_selected":False,
        "future_outcomes_read":False,
    }
    manifest["snapshot_hash"]=sha256_json(manifest)
    _write_immutable_json(root/"manifest.json",manifest)
    if normalized:
        _write_immutable_json(root/"normalized_matches.json",normalized_dicts)
    return manifest,normalized


def load_incremental_history_snapshot(snapshot_dir: Path) -> tuple[dict[str,Any],tuple[ResearchMatch,...]]:
    root=Path(snapshot_dir)
    manifest=json.loads((root/"manifest.json").read_text())
    expected=manifest.pop("snapshot_hash",None)
    if sha256_json(manifest)!=expected:
        raise ValueError("incremental snapshot manifest hash mismatch")
    manifest={**manifest,"snapshot_hash":expected}
    if not manifest.get("prediction_eligible"):
        raise ValueError("incremental snapshot is not prediction-eligible")
    rows=json.loads((root/"normalized_matches.json").read_text())
    if sha256_json(rows)!=manifest["normalized_matches_hash"]:
        raise ValueError("incremental normalized matches hash mismatch")
    matches=tuple(ResearchMatch(**row) for row in rows)
    if len(matches)!=manifest["normalized_match_count"]:
        raise ValueError("incremental normalized match count mismatch")
    for record in manifest["payload_records"]:
        rel=record.get("relative_path")
        if not rel:
            continue
        body=json.loads((root/rel).read_text())
        if _sha_payload(body)!=record["payload_sha256"]:
            raise ValueError(f"incremental raw payload hash mismatch: {rel}")
    return manifest,matches
