"""Layer 5 V1.2 future-prospective market manifest.

Outcome-blind. The input cohort is a strict future-fixture whitelist frozen
before every fixture's T-6h decision cutoff. Only registered market metadata is
read. Corner bookmaker comparison fails closed until settlement semantics are
certified.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import Any, Iterable

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.layer5.market_manifest import CapturePrefix
from src.research.layer5.market_surface import (
    TwoWayQuote,
    build_market_point,
    select_benchmark_bundle,
)
from src.research.layer5.protocol import active_protocol_hash, protocol_active

MANIFEST_VERSION = "qfe-layer5-prospective-market-manifest-v1.2"
COHORT_VERSION = "qfe-prospective-cohort-v1"
COHORT_STATUS = "FROZEN_OUTCOME_BLIND"
GOAL_LINE = 2.5


@dataclass(frozen=True, slots=True)
class ProspectiveFixture:
    fixture_id: str
    event_time: float


@dataclass(frozen=True, slots=True)
class GoalPair:
    fixture_id: str
    bookmaker: str
    observed_at: float
    raw_payload_hash: str
    event_time: float
    over_odds: float
    under_odds: float

    @property
    def bundle_id(self) -> str:
        return f"{self.observed_at:.6f}:{self.raw_payload_hash}"

    def quote(self) -> TwoWayQuote:
        return TwoWayQuote(
            fixture_id=self.fixture_id,
            market_key="GOALS_TOTAL",
            bookmaker=self.bookmaker,
            line=GOAL_LINE,
            over_odds=self.over_odds,
            under_odds=self.under_odds,
            observed_at=self.observed_at,
            bundle_id=self.bundle_id,
        )


def _parse_iso_ts(value: str) -> float:
    text=str(value)
    if text.endswith("Z"):
        text=text[:-1]+"+00:00"
    dt=datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("cohort frozen_at must be timezone-aware")
    return dt.timestamp()


def validate_prospective_cohort_manifest(obj: dict[str, Any]) -> tuple[ProspectiveFixture, ...]:
    allowed={"version","status","frozen_at","fixtures","cohort_hash"}
    if set(obj) != allowed:
        raise ValueError("prospective cohort schema drift")
    if obj["version"] != COHORT_VERSION or obj["status"] != COHORT_STATUS:
        raise ValueError("prospective cohort version/status invalid")
    base={k:obj[k] for k in ("version","status","frozen_at","fixtures")}
    if sha256_json(base) != obj["cohort_hash"]:
        raise ValueError("prospective cohort hash mismatch")
    frozen_ts=_parse_iso_ts(obj["frozen_at"])
    horizon=float(protocol_active()["market_horizon"]["target_seconds_before_kickoff"])
    rows=obj["fixtures"]
    if not isinstance(rows,list) or not rows:
        raise ValueError("prospective cohort must be non-empty")
    fixtures=[]
    seen=set()
    expected_order=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"fixture_id","event_time"}:
            raise ValueError("prospective cohort fixture schema must be exactly fixture_id,event_time")
        fid=str(row["fixture_id"])
        ts=float(row["event_time"])
        if not fid or not isfinite(ts) or ts<=0:
            raise ValueError("invalid prospective fixture identity/time")
        if fid in seen:
            raise ValueError("duplicate prospective fixture")
        if frozen_ts > ts-horizon:
            raise ValueError("cohort frozen after fixture T-6h prediction cutoff")
        seen.add(fid)
        fixtures.append(ProspectiveFixture(fid,ts))
        expected_order.append((ts,fid))
    if expected_order != sorted(expected_order):
        raise ValueError("prospective cohort fixtures must be sorted by event_time,fixture_id")
    return tuple(fixtures)


def _iter_prefix_rows(prefix: CapturePrefix):
    with gzip.GzipFile(fileobj=io.BytesIO(prefix.data),mode="rb") as gz:
        text=io.TextIOWrapper(gz,encoding="utf-8")
        for line in text:
            if line.strip():
                value=json.loads(line)
                if isinstance(value,dict):
                    yield value


def _surface_dict(surface) -> dict[str,Any]:
    return {
        "status":surface.status,
        "reason":surface.reason,
        "bookmaker":surface.bookmaker,
        "bundle_id":surface.bundle_id,
        "prediction_cutoff":surface.prediction_cutoff,
        "observed_at_min":surface.observed_at_min,
        "observed_at_max":surface.observed_at_max,
        "max_abs_repair":surface.max_abs_repair,
        "mean_abs_repair":surface.mean_abs_repair,
        "points":[asdict(p) for p in surface.points],
    }


def build_prospective_market_manifest(
    *,
    capture_prefix: CapturePrefix,
    cohort_manifest: dict[str,Any],
) -> tuple[dict[str,Any],tuple[dict[str,Any],...]]:
    protocol=protocol_active()
    fixtures=validate_prospective_cohort_manifest(cohort_manifest)
    by_id={f.fixture_id:f for f in fixtures}
    horizon=float(protocol["market_horizon"]["target_seconds_before_kickoff"])

    source_counts={
        "json_rows_scanned":0,
        "cohort_odds_rows_seen":0,
        "registered_goal_rows_seen":0,
        "registered_goal_rows_in_t6_window":0,
        "corner_odds_rows_seen_but_ineligible":0,
        "invalid_timestamp_rows":0,
    }
    retained=[]
    cells={}

    for row in _iter_prefix_rows(capture_prefix):
        source_counts["json_rows_scanned"]+=1
        if row.get("provider")!="thestatsapi" or row.get("raw_status")!="PROSPECTIVE_SNAPSHOT":
            continue
        fid=str(row.get("canonical_entity_id") or "")
        if fid not in by_id:
            continue
        concept=str(row.get("concept") or "")
        if not concept.startswith("odds:"):
            continue
        source_counts["cohort_odds_rows_seen"]+=1
        if concept.startswith("odds:match_corners:") or concept.startswith("odds:team_corners:"):
            source_counts["corner_odds_rows_seen_but_ineligible"]+=1
            continue

        parts=concept.split(":")
        if len(parts)!=5 or parts[0]!="odds" or parts[1]!="total_goals" or parts[2] not in {"over","under"}:
            continue
        try:
            line=float(parts[3])
        except ValueError:
            continue
        if abs(line-GOAL_LINE)>1e-9:
            continue
        bookmaker=parts[4]
        source_counts["registered_goal_rows_seen"]+=1
        try:
            event_time=float(row["event_time"])
            observed_at=float(row["observed_at"])
            retrieved_at=float(row["retrieved_at"])
            odds=float(row["value"])
        except (KeyError,TypeError,ValueError):
            source_counts["invalid_timestamp_rows"]+=1
            continue
        if abs(event_time-by_id[fid].event_time)>1e-6:
            raise ValueError(f"prospective capture kickoff conflicts for {fid}")
        if abs(observed_at-retrieved_at)>1e-6:
            source_counts["invalid_timestamp_rows"]+=1
            continue
        cutoff=event_time-horizon
        age=cutoff-observed_at
        if age<0 or age>float(protocol["market_horizon"]["max_snapshot_age_seconds"]):
            continue
        raw_hash=str(row.get("raw_payload_hash") or "")
        if not raw_hash:
            source_counts["invalid_timestamp_rows"]+=1
            continue
        source_counts["registered_goal_rows_in_t6_window"]+=1
        frozen={
            "provider":"thestatsapi",
            "fixture_id":fid,
            "event_time":event_time,
            "observed_at":observed_at,
            "retrieved_at":retrieved_at,
            "raw_payload_hash":raw_hash,
            "market_key":"GOALS_TOTAL",
            "selection":parts[2],
            "line":GOAL_LINE,
            "bookmaker":bookmaker,
            "decimal_odds":odds,
        }
        retained.append(frozen)
        key=(fid,bookmaker,observed_at,raw_hash)
        cells.setdefault(key,{})[parts[2]]=odds

    pairs=[]
    for (fid,book,obs,raw_hash),sels in sorted(cells.items()):
        if set(sels)!={"over","under"}:
            continue
        pairs.append(GoalPair(fid,book,obs,raw_hash,by_id[fid].event_time,sels["over"],sels["under"]))

    by_fixture={}
    for pair in pairs:
        by_fixture.setdefault(pair.fixture_id,[]).append(pair.quote())

    fixture_rows=[]
    valid_goals=0
    reason_counts={}
    for fixture in fixtures:
        cutoff=fixture.event_time-horizon
        quotes=by_fixture.get(fixture.fixture_id,[])
        if not quotes:
            goal={"status":"ABSTAIN","reason":"MARKET_HORIZON_MISSING","points":[]}
        else:
            selected=select_benchmark_bundle(
                quotes,
                prediction_cutoff=cutoff,
                market_key="GOALS_TOTAL",
                minimum_adjacent_lines=1,
            )
            if not selected:
                goal={"status":"ABSTAIN","reason":"BOOKMAKER_HIERARCHY_NO_COMPLETE_MARKET","points":[]}
            else:
                if len(selected)!=1:
                    raise ValueError("prospective goal bundle must contain one registered line")
                goal=_surface_dict(build_market_point(selected[0],prediction_cutoff=cutoff))
        if goal["status"]=="OK":
            valid_goals+=1
        else:
            reason=str(goal.get("reason") or "UNKNOWN")
            reason_counts[reason]=reason_counts.get(reason,0)+1

        semantic_abstain={
            "status":"ABSTAIN",
            "reason":"SETTLEMENT_SEMANTICS_UNVERIFIED",
            "detail":"Provider-to-bookmaker corner settlement equivalence is not certified.",
            "points":[],
        }
        reason_counts["SETTLEMENT_SEMANTICS_UNVERIFIED"]=reason_counts.get("SETTLEMENT_SEMANTICS_UNVERIFIED",0)+2
        fixture_rows.append({
            "fixture_id":fixture.fixture_id,
            "event_time":fixture.event_time,
            "prediction_cutoff":cutoff,
            "markets":{
                "GOALS_TOTAL":goal,
                "CORNERS_TOTAL":dict(semantic_abstain),
                "CORNERS_SIDE":dict(semantic_abstain),
            },
        })

    retained_sorted=tuple(sorted(retained,key=lambda r:(r["fixture_id"],r["bookmaker"],r["observed_at"],r["selection"])))
    manifest={
        "version":MANIFEST_VERSION,
        "active_protocol_hash":active_protocol_hash(),
        "scientific_status":"FUTURE_PROSPECTIVE_MARKET_METADATA_ONLY_OUTCOMES_UNREAD",
        "prospective_cohort_hash":cohort_manifest["cohort_hash"],
        "prospective_fixture_count":len(fixtures),
        "legacy_317_used":False,
        "source":{
            "kind":protocol["market_source"]["primary_source"],
            "provider":protocol["market_source"]["provider"],
            "prefix_size_bytes":capture_prefix.size_bytes,
            "prefix_sha256":capture_prefix.sha256,
            "raw_status_required":protocol["market_source"]["required_raw_status"],
        },
        "source_counts":source_counts,
        "retained_source_rows_hash":sha256_json(retained_sorted),
        "retained_source_row_count":len(retained_sorted),
        "fixture_rows_hash":sha256_json(fixture_rows),
        "valid_matched_market_counts":{"GOALS_TOTAL":valid_goals,"CORNERS_TOTAL":0,"CORNERS_SIDE":0},
        "abstention_reason_counts":dict(sorted(reason_counts.items())),
        "fixture_rows":fixture_rows,
        "outcomes_read":False,
    }
    manifest["manifest_hash"]=sha256_json(manifest)
    return manifest,retained_sorted


def write_prospective_market_manifest(
    *,
    output_dir: Path,
    manifest: dict[str,Any],
    retained_rows: Iterable[dict[str,Any]],
) -> tuple[Path,Path]:
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    manifest_path=output_dir/"QFE_LAYER5_PROSPECTIVE_MARKET_MANIFEST_V1_2.json"
    rows_path=output_dir/"QFE_LAYER5_PROSPECTIVE_MARKET_SOURCE_ROWS_V1_2.jsonl.gz"
    manifest_payload=(canonical_json(manifest)+"\n").encode()
    raw="".join(canonical_json(r)+"\n" for r in retained_rows).encode()
    rows_payload=gzip.compress(raw,compresslevel=9,mtime=0)
    for path,payload in ((manifest_path,manifest_payload),(rows_path,rows_payload)):
        if path.exists():
            if path.read_bytes()!=payload:
                raise FileExistsError(f"frozen prospective-market artifact differs: {path}")
        else:
            path.write_bytes(payload)
    return manifest_path,rows_path
